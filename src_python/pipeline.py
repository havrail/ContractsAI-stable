import os
import io
import base64
import time
import traceback
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Callable

# 3. Party Libs
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session
import cv2
import numpy as np

# Local Modules
from database import SessionLocal, get_db
from models import AnalysisJob, Contract
from image_processing import ImageProcessor
from llm_client import LLMClient
from utils import (
    determine_telenity_entity, 
    extract_date_from_filename, 
    clean_turkish_chars, 
    filter_telenity_address,
    normalize_country,
    find_best_company_match  # <--- YENİ: Fuzzy Match fonksiyonunu import ettik
)
from logger import logger
from cache import cache
from config import (
    POPPLER_PATH,
    TESSERACT_CMD,
    USE_VISION_MODEL,
    MAX_WORKERS,
    BATCH_SIZE,
    DPI,
    DOC_TYPE_CHOICES,
    COMPANY_CHOICES
)

# Tesseract Configuration
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
TESSERACT_CONFIG = "--oem 1 --psm 6"

# DPI Ayarları
SCAN_DPI = 100  # İmza aramak için hızlı tarama kalitesi
FINAL_DPI = 200 # LLM'e gidecek okunaklı kalite

class PipelineManager:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log_callback = log_callback
        self.llm_client = LLMClient()

    def calculate_file_hash(self, filepath: str) -> Optional[str]:
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Hash calculation error: {e}")
            return None

    def _images_to_base64(self, images: List[Any]) -> List[str]:
        """Convert PIL images to Base64 for LLM with Resizing."""
        b64_list = []
        for img in images:
            # Resmi Küçült (Max 1024px) - LLM performans optimizasyonu
            img_resized = img.copy()
            img_resized.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            img_resized.save(buf, format="JPEG", quality=60)
            b64_list.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
        return b64_list

    def identify_key_pages(self, full_path: str, num_pages: int) -> List[int]:
        """Hızlı Ön Tarama: İmzalı sayfaları bulur."""
        signature_pages = set()
        signature_pages.add(0) # İlk sayfa her zaman lazım

        try:
            logger.info(f"Scanning {num_pages} pages at {SCAN_DPI} DPI for signatures...")
            low_res_images = convert_from_path(full_path, dpi=SCAN_DPI, poppler_path=POPPLER_PATH)
            
            for i, img in enumerate(low_res_images):
                if i == 0: continue
                if ImageProcessor.detect_visual_signature(img):
                    signature_pages.add(i)
            
            if len(signature_pages) == 1: 
                signature_pages.add(num_pages - 1)
                
        except Exception as e:
            logger.error(f"Scan signature error: {e}. Falling back to First/Last.")
            if num_pages > 1:
                signature_pages.add(num_pages - 1)

        sorted_pages = sorted(list(signature_pages))
        
        # Çok fazla sayfa varsa (False Positive) sadece kritik olanları al
        if len(sorted_pages) > 4:
            logger.warning(f"Too many signature pages ({len(sorted_pages)}). Limiting to essential pages.")
            limited_set = {0}
            limited_set.add(sorted_pages[-1])
            if len(sorted_pages) > 2:
                limited_set.add(sorted_pages[-2])
            return sorted(list(limited_set))

        return sorted_pages

    def get_optimized_images_for_llm(self, full_path: str, key_indices: List[int]) -> List[Any]:
        final_images = []
        for idx in key_indices:
            page_num = idx + 1
            try:
                imgs = convert_from_path(
                    full_path, 
                    dpi=FINAL_DPI, 
                    poppler_path=POPPLER_PATH, 
                    first_page=page_num, 
                    last_page=page_num
                )
                if imgs:
                    final_images.append(imgs[0])
            except Exception as e:
                logger.error(f"Error fetching high-res page {page_num}: {e}")
        return final_images

    def _clean_signing_party(self, party_name):
        """Signing Party ismini temizler (Telenity'yi çıkarır)."""
        if not party_name: return ""
        
        # Sadece Telenity yazıyorsa boşalt
        if party_name.lower().strip().replace(" ", "") in ["telenity", "telenityfze", "telenityinc"]:
            return ""

        # " and " ile ayrılmışsa Telenity olmayanı al
        if " and " in party_name.lower():
            parts = re.split(r' and | & ', party_name, flags=re.IGNORECASE)
            for part in parts:
                if "telenity" not in part.lower():
                    return part.strip()
        
        # Telenity ile başlıyorsa kes (Örn: "Telenity and X")
        party_name = re.sub(r'(?i)^Telenity.*?(and|&)\s*', '', party_name)
        
        return party_name.strip()

    def _clean_contract_name(self, name):
        if not name: return "Belirtilmemiş"
        name = name.replace("<InsertDate>", "").strip()
        if len(name) > 100: name = name[:100]
        if any(x in name.lower() for x in ["agreement is made", "hereinafter", "entered into"]):
            return ""
        return name

    def _map_choice(self, value, options, default="Other"):
        if not value: return default
        val = str(value).lower().strip()
        for opt in options:
            if val == opt.lower(): return opt
        for opt in options:
            if opt.lower() in val: return opt
        return default

    def _map_signature_smart(self, text_sig, visual_count):
        sig = str(text_sig).lower()
        if visual_count >= 2: return "Fully Signed"
        if "fully" in sig or "both" in sig: return "Fully Signed"
        if "counter" in sig or "customer" in sig: return "Counterparty Signed"
        if visual_count == 1: return "Fully Signed" # Görsel imza varsa güven
        if "telenity" in sig: return "Telenity Signed"
        return "Telenity Signed"

    def process_single_file(self, filename: str, folder_path: str) -> Dict[str, Any]:
        full_path = os.path.join(folder_path, filename)
        db = None
        try:
            # 1. Metadata Check
            file_hash = self.calculate_file_hash(full_path)
            if not file_hash: return {"error": "Hash error", "dosya_adi": filename}

            db = next(get_db())
            cached = db.query(Contract).filter(Contract.file_hash == file_hash).first()
            if cached:
                logger.info(f"DB Cache HIT: {filename}")
                result = {
                    "dosya_adi": filename, "contract_name": cached.contract_name,
                    "doc_type": cached.doc_type, "company_type": cached.company_type,
                    "signing_party": cached.signing_party, "country": cached.country,
                    "address": cached.address, "signed_date": str(cached.signed_date) if cached.signed_date else "",
                    "signature": cached.signature, "telenity_entity": cached.telenity_entity,
                    "telenity_fullname": cached.telenity_fullname, "file_hash": file_hash,
                    "durum_notu": "Önbellekten"
                }
                db.close()
                return result

            # 2. Text Extraction (Native)
            text = ""
            is_scanned = False
            reader = PdfReader(full_path)
            num_pages = len(reader.pages)

            try:
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt: text += txt + "\n"
            except Exception as e:
                logger.warning(f"Native read failed: {e}")

            if not text or len(text.strip()) < 100:
                is_scanned = True
                logger.info(f"Detected SCANNED document: {filename}")

            # 3. Smart Image Strategy
            target_page_indices = self.identify_key_pages(full_path, num_pages)
            llm_images = self.get_optimized_images_for_llm(full_path, target_page_indices)

            # 4. OCR (Fallback)
            if is_scanned and not text.strip() and llm_images:
                logger.info("Running Partial OCR on key pages...")
                for img in llm_images:
                    processed = ImageProcessor.preprocess_image(img)
                    text += pytesseract.image_to_string(processed, lang="tur+eng", config=TESSERACT_CONFIG) + "\n"

            # 5. LLM Analysis
            filename_date = extract_date_from_filename(filename)
            vision_images_b64 = []
            
            if USE_VISION_MODEL and llm_images:
                vision_images_b64 = self._images_to_base64(llm_images)

            llm_data = self.llm_client.get_analysis(
                text=text, 
                filename=filename, 
                images=vision_images_b64, 
                filename_date=filename_date
            )

            # 6. Post-Processing
            telenity_search_text = (llm_data.get("found_telenity_name", "") or "") + " " + text[:2000]
            telenity_code, telenity_full = determine_telenity_entity(telenity_search_text)
            
            if USE_VISION_MODEL and (not telenity_code or telenity_code == "Bilinmiyor") and vision_images_b64:
                vision_res = self.llm_client.detect_telenity_visual(vision_images_b64[0])
                if vision_res:
                    telenity_code, telenity_full = vision_res

            # Cleaning Steps
            contract_name = self._clean_contract_name(llm_data.get("contract_name", ""))
            
            # Party Cleaning
            raw_party = llm_data.get("signing_party", "")
            final_party = self._clean_signing_party(raw_party)
            
            # Address Filtering
            address = filter_telenity_address(clean_turkish_chars(llm_data.get("address", "")))
            
            # Country Normalization
            raw_country = llm_data.get("country", "")
            final_country = normalize_country(raw_country)

            # ---------------------------------------------------------
            # YENİ: FUZZY MATCHING İLE HAFIZADAN TAMAMLAMA
            # ---------------------------------------------------------
            import json
            kb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "known_companies.json")
            
            # 1. HAFIZAYI YÜKLE
            known_db = {}
            if os.path.exists(kb_path):
                try:
                    with open(kb_path, "r", encoding="utf-8") as f:
                        known_db = json.load(f)
                except: pass

            # 2. EKSİKLERİ TAMAMLA (FUZZY LOGIC)
            # Eğer adres veya ülke boşsa, fuzzy match ile bulmaya çalış
            if final_party and (not address or not final_country):
                # Yeni Fuzzy fonksiyonunu kullan
                match = find_best_company_match(final_party, known_db, threshold=80)
                
                if match:
                    logger.info(f"🧠 Fuzzy Match: '{final_party}' found in DB")
                    if not address: address = match.get("address", "")
                    if not final_country: final_country = match.get("country", "")

            # 3. HAFIZAYA KAYDET (Otomatik Öğrenme)
            if final_party and address and final_country and len(address) > 10:
                party_key = final_party.lower().strip()
                
                should_update = False
                if party_key not in known_db:
                    should_update = True
                elif len(address) > len(known_db[party_key].get("address", "")):
                    should_update = True
                
                if should_update:
                    known_db[party_key] = {
                        "full_name": final_party,
                        "address": address,
                        "country": final_country
                    }
                    try:
                        with open(kb_path, "w", encoding="utf-8") as f:
                            json.dump(known_db, f, indent=4, ensure_ascii=False)
                        logger.info(f"🧠 Learned: '{final_party}'")
                    except Exception as e:
                        logger.warning(f"Could not update memory: {e}")
            # ---------------------------------------------------------

            # Signature Logic
            visual_sig_count = len([p for p in target_page_indices if p != 0])
            final_sig = self._map_signature_smart(llm_data.get("text_signature_status", ""), visual_sig_count)

            db.close()
            return {
                "dosya_adi": filename,
                "contract_name": contract_name,
                "doc_type": self._map_choice(llm_data.get("doc_type"), DOC_TYPE_CHOICES),
                "signature": final_sig,
                "company_type": self._map_choice(llm_data.get("company_type"), COMPANY_CHOICES),
                "signing_party": final_party,
                "country": final_country,
                "address": address,
                "signed_date": filename_date or llm_data.get("signed_date", ""),
                "telenity_entity": telenity_code,
                "telenity_fullname": telenity_full,
                "durum_notu": "Tamamlandı",
                "file_hash": file_hash,
            }

        except Exception as e:
            logger.error(f"Processing error {filename}: {e}")
            traceback.print_exc()
            if db: db.close()
            return {"error": str(e), "dosya_adi": filename}

    def run_job(self, job_id: int, folder_path: str):
        db = SessionLocal()
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job: 
            db.close()
            return

        try:
            job.status = "RUNNING"
            job.message = "Analiz (Smart Scan) başlıyor..."
            db.commit()

            connected, _ = self.llm_client.autodetect_connection()
            if not connected:
                logger.warning("LM Studio bağlantısı yok, analiz sınırlı olacak.")

            files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
            if not files:
                job.status = "COMPLETED"
                job.message = "Dosya bulunamadı"
                db.commit()
                return

            total = len(files)
            processed = 0
            batches = [files[i:i + BATCH_SIZE] for i in range(0, len(files), BATCH_SIZE)]
            all_contracts = []

            for batch in batches:
                db.refresh(job)
                if job.status == "CANCELLED": break

                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {executor.submit(self.process_single_file, f, folder_path): f for f in batch}
                    for future in as_completed(futures):
                        res = future.result()
                        if "error" not in res:
                            all_contracts.append(Contract(job_id=job_id, **res))
                        processed += 1
                        
                        if processed % 2 == 0:
                            job.progress = int((processed / total) * 100)
                            job.message = f"İşleniyor: {processed}/{total}"
                            db.commit()
            
            if all_contracts:
                db.bulk_save_objects(all_contracts)
                db.commit()

            job.status = "COMPLETED"
            job.message = f"Tamamlandı ({processed} dosya)"
            job.progress = 100
            db.commit()
            
            self.export_to_excel(job_id, folder_path)

        except Exception as e:
            logger.error(f"Job failed: {e}")
            job.status = "FAILED"
            job.message = str(e)
            db.commit()
        finally:
            db.close()

    def export_to_excel(self, job_id, output_path):
        import pandas as pd
        from datetime import datetime
        
        db = SessionLocal()
        try:
            contracts = db.query(Contract).filter(Contract.job_id == job_id).all()
            if not contracts: return "Veri yok"
            
            data = []
            for c in contracts:
                data.append({
                    "Dosya Adı": c.dosya_adi,
                    "Contract Name": c.contract_name,
                    "Doc. Type": c.doc_type,
                    "Signature": c.signature,
                    "Company Type": c.company_type,
                    "Signing Party": c.signing_party,
                    "Country": c.country,
                    "Address": c.address,
                    "Signed Date": c.signed_date,
                    "Telenity Entity": c.telenity_entity,
                    "Telenity Entity Full Name": c.telenity_fullname,
                    "Durum": c.durum_notu
                })
            
            df = pd.DataFrame(data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            full_path = os.path.join(output_path, f"Telenity_Rapor_{timestamp}.xlsx")
            
            with pd.ExcelWriter(full_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, sheet_name="Analiz", index=False)
                worksheet = writer.sheets["Analiz"]
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, max_len)
            return full_path
        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            return ""
        finally:
            db.close()
