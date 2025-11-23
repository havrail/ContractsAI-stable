# src/pipeline.py
import os
import io
import base64
import time
import traceback
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Callable

# 3. Party Libs
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session

# Local Modules
from database import SessionLocal, get_db
from models import AnalysisJob, Contract
from image_processing import ImageProcessor
from llm_client import LLMClient
from utils import (
    determine_telenity_entity, 
    extract_date_from_filename, 
    clean_turkish_chars, 
    filter_telenity_address
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
        """Convert PIL images to Base64 for LLM."""
        b64_list = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            b64_list.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
        return b64_list

    def identify_key_pages(self, full_path: str, num_pages: int) -> List[int]:
        """
        STRATEJI: Hızlı Ön Tarama (Low-Res Scan)
        Tüm sayfaları düşük kalitede çevirip görsel imza (mürekkep) arar.
        İmzalı sayfaların indekslerini döndürür.
        """
        signature_pages = set()
        
        # İlk sayfa her zaman bağlam (context) için gereklidir
        signature_pages.add(0)

        # Eğer dosya çok büyükse (örn: 50+ sayfa) ve native PDF ise, 
        # sadece sona bakmak isteyebiliriz ama kullanıcı isteği üzerine
        # "başa alıp tarama" yapıyoruz.
        
        try:
            # 1. Hızlı Tarama (100 DPI)
            logger.info(f"Scanning {num_pages} pages at {SCAN_DPI} DPI for signatures...")
            low_res_images = convert_from_path(full_path, dpi=SCAN_DPI, poppler_path=POPPLER_PATH)
            
            # 2. Görsel İmza Arama
            for i, img in enumerate(low_res_images):
                if ImageProcessor.detect_visual_signature(img):
                    logger.info(f"Signature detected visually on page {i+1}")
                    signature_pages.add(i)
            
            # Eğer hiç imza bulunamadıysa, en azından son sayfayı ekle (Fallback)
            if len(signature_pages) == 1: # Sadece sayfa 0 varsa
                signature_pages.add(num_pages - 1)
                
        except Exception as e:
            logger.error(f"Scan signature error: {e}. Falling back to First/Last.")
            signature_pages.add(num_pages - 1)

        return sorted(list(signature_pages))

    def get_optimized_images_for_llm(self, full_path: str, key_indices: List[int]) -> List[Any]:
        """
        Sadece belirlenen önemli sayfaları Yüksek Kalite (200 DPI) ile çevirir.
        """
        final_images = []
        # pdf2image tek tek sayfa çekmeyi destekler ama batch daha hızlı olabilir.
        # Yine de sayfa numaraları dağınık olabileceği için döngü kuralım.
        for idx in key_indices:
            # pdf2image 1-based index kullanır, biz 0-based index tutuyoruz
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

            # 3. Smart Image Strategy (Hibrid Yaklaşım)
            # İmza aramak için hızlı tarama yap, bulunanları yüksek kalite al
            target_page_indices = self.identify_key_pages(full_path, num_pages)
            
            # LLM'e gidecek yüksek kaliteli görselleri hazırla
            llm_images = self.get_optimized_images_for_llm(full_path, target_page_indices)

            # 4. OCR (Sadece Scanned ve Metin Yoksa)
            # Eğer taranmış belgeyse ve metin yoksa, elimizdeki görsellerden (önemli sayfalardan) metin çıkarmayı deneyelim.
            # Not: Tam metin araması için tüm sayfaları OCR yapmak gerekebilir ama bu çok yavaş.
            # Şimdilik LLM'in Vision yeteneğine güveniyoruz, sadece çok kötüyse seçili sayfalara OCR atalım.
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
            
            # Vision Fallback for Telenity Logo (Using First Page)
            if USE_VISION_MODEL and (not telenity_code or telenity_code == "Bilinmiyor") and vision_images_b64:
                vision_res = self.llm_client.detect_telenity_visual(vision_images_b64[0])
                if vision_res:
                    telenity_code, telenity_full = vision_res

            contract_name = self._clean_contract_name(llm_data.get("contract_name", ""))
            address = filter_telenity_address(clean_turkish_chars(llm_data.get("address", "")))
            
            # İmza Durumu: Görsel olarak imza tespit ettiysek bunu LLM'e bildirmiştik.
            # LLM'in metin analizini görsel analizle birleştirelim.
            visual_sig_count = len(target_page_indices) - 1 # Sayfa 0 hariç kaç sayfada imza bulundu?
            final_sig = self._map_signature_smart(llm_data.get("text_signature_status", ""), visual_sig_count)

            db.close()
            return {
                "dosya_adi": filename,
                "contract_name": contract_name,
                "doc_type": self._map_choice(llm_data.get("doc_type"), DOC_TYPE_CHOICES),
                "signature": final_sig,
                "company_type": self._map_choice(llm_data.get("company_type"), COMPANY_CHOICES),
                "signing_party": llm_data.get("signing_party", ""),
                "country": llm_data.get("country", ""),
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
        # LLM metin analizi + Görsel Dedektör sonucu
        sig = str(text_sig).lower()
        
        # Eğer görsel olarak 2 veya daha fazla sayfada imza bulduysak, muhtemelen Fully Signed'dır
        if visual_count >= 2:
            return "Fully Signed"
        
        if "fully" in sig or "both" in sig: return "Fully Signed"
        if "counter" in sig or "partner" in sig or "customer" in sig: return "Counterparty Signed"
        if "telenity" in sig: return "Telenity Signed"
        
        # Hiçbir şey bulamadıysak ama görselde 1 imza varsa
        if visual_count == 1:
            return "Counterparty Signed" # Varsayım
            
        return "Telenity Signed" # En kötü ihtimal

    def run_job(self, job_id: int, folder_path: str):
        # (Bu kısım öncekiyle aynı, sadece hata yönetimi için koruyoruz)
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
                raise Exception("LM Studio bağlantısı yok.")

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
        # Excel export kodu buraya (değişmedi)
        pass
