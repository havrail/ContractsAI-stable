import os
import io
import base64
import time
import traceback
import hashlib
import re
import json
import platform
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Callable

# Suppress poppler/PyPDF2 warnings
warnings.filterwarnings("ignore", category=UserWarning, module="PyPDF2")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from pdf2image import convert_from_path, pdfinfo_from_path
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session
import cv2
import numpy as np

from database import SessionLocal, get_db
from models import AnalysisJob, Contract
from image_processing import ImageProcessor
from llm_client import LLMClient
from pdf_quality_checker import PDFQualityChecker
from prompt_templates import build_contract_extraction_messages, parse_json_response, generate_adaptive_hints
from model_provider import ModelProvider
from feedback_service import FeedbackService
from utils import (
    determine_telenity_entity, 
    extract_date_from_filename, 
    clean_turkish_chars, 
    filter_telenity_address,
    normalize_country,
    find_best_company_match,
    extract_company_from_filename,
    extract_contract_name_from_filename,
    clean_contract_name,
    infer_country_from_address
)
from web_enrichment import enrich_missing_data
from validation import validate_contract
from logger import logger
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

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
TESSERACT_CONFIG = "--oem 1 --psm 6"
SCAN_DPI = 100  
FINAL_DPI = 200 

class PipelineManager:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log_callback = log_callback
        self.llm_client = LLMClient()
        self.quality_checker = PDFQualityChecker()
        self.provider = ModelProvider()
        try:
            self.feedback_service = FeedbackService()
        except Exception:
            self.feedback_service = None  # Feedback system optional
        
        # Track corrupt PDFs for summary report
        self.corrupt_pdfs = []
    
    @staticmethod
    def _suppress_poppler_stderr(func, *args, **kwargs):
        """Suppress poppler stderr output (syntax errors, warnings)"""
        import sys
        import contextlib
        
        # Redirect stderr to devnull
        with contextlib.redirect_stderr(open(os.devnull, 'w')):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Re-raise the exception, but stderr is suppressed
                raise e

    # --- YENİ: WINDOWS GÜVENLİ YOL DÜZELTİCİ ---
    def _get_safe_path(self, path: str) -> str:
        """
        Windows'ta uzun yolları ve özel karakterleri işlemek için
        yolun başına '\\?\' ekler. Errno 22 hatasını çözer.
        """
        if platform.system() == "Windows":
            # Zaten prefix varsa ekleme
            if path.startswith("\\\\?\\"):
                return path
            # Absolute path yap ve prefix ekle
            abs_path = os.path.abspath(path)
            if not abs_path.startswith("\\\\?\\"):
                return f"\\\\?\\{abs_path}"
            return abs_path
        return path

    def calculate_file_hash(self, filepath: str) -> Optional[str]:
        hash_md5 = hashlib.md5()
        try:
            # Safe path kullanıyoruz
            safe_path = self._get_safe_path(filepath)
            with open(safe_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            # Fallback: Try original path if safe path fails
            try:
                with open(filepath, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                return hash_md5.hexdigest()
            except Exception as e2:
                logger.error(f"Hash calculation error: {e} | Fallback error: {e2}")
                return None

    def _images_to_base64(self, images: List[Any]) -> List[str]:
        b64_list = []
        for img in images:
            try:
                img_resized = img.copy()
                img_resized.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img_resized.save(buf, format="JPEG", quality=60)
                b64_list.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
            except Exception: pass
        return b64_list

    def identify_key_pages(self, full_path: str, num_pages: int) -> List[int]:
        """Smart page selection - only convert pages that likely contain signatures/addresses"""
        key_pages = set()
        key_pages.add(0)  # Always include first page
        
        safe_path = self._get_safe_path(full_path)

        try:
            # Phase 1: Text-based keyword scan (NO IMAGE CONVERSION - fast)
            try:
                reader = PdfReader(safe_path)
                keywords = ["notices", "tebligat", "adres:", "address:", "registered office", "signature", "imza"]
                
                # Check strategic pages: first, last, and middle samples
                strategic_indices = [0, num_pages - 1]
                if num_pages > 5:
                    strategic_indices.extend([num_pages // 3, 2 * num_pages // 3])
                
                for i in strategic_indices:
                    if i < len(reader.pages):
                        txt = (reader.pages[i].extract_text() or "").lower()
                        if any(kw in txt for kw in keywords):
                            key_pages.add(i)
            except: pass

            # Phase 2: Selective signature scan (only if < 10 pages OR last 3 pages)
            scan_pages = []
            if num_pages <= 10:
                scan_pages = list(range(num_pages))
            else:
                # For large documents, only scan last 3 pages for signatures
                scan_pages = list(range(max(0, num_pages - 3), num_pages))
            
            if scan_pages:
                logger.info(f"Scanning {len(scan_pages)} pages at {SCAN_DPI} DPI for signatures...")
                low_res_images = self._suppress_poppler_stderr(
                    convert_from_path,
                    full_path, 
                    dpi=SCAN_DPI, 
                    poppler_path=POPPLER_PATH,
                    first_page=scan_pages[0] + 1,
                    last_page=scan_pages[-1] + 1
                )
                for i, img in enumerate(low_res_images):
                    actual_page = scan_pages[i]
                    if ImageProcessor.detect_visual_signature(img):
                        key_pages.add(actual_page)
            
            # Always include last page if we have more than 1 page
            if num_pages > 1:
                key_pages.add(num_pages - 1)
                
        except Exception as e:
            logger.error(f"Scan signature error: {e}.")
            if num_pages > 1: key_pages.add(num_pages - 1)

        sorted_pages = sorted(list(key_pages))
        if len(sorted_pages) > 5:
            optimized = {0, sorted_pages[-1]}
            mid = sorted_pages[1:-1]
            if mid: optimized.update(mid[:3])
            return sorted(list(optimized))
        return sorted_pages

    def get_optimized_images_for_llm(self, full_path: str, key_indices: List[int]) -> List[Any]:
        final_images = []
        for idx in key_indices:
            page_num = idx + 1
            try:
                imgs = self._suppress_poppler_stderr(
                    convert_from_path,
                    full_path, 
                    dpi=FINAL_DPI, 
                    poppler_path=POPPLER_PATH, 
                    first_page=page_num, 
                    last_page=page_num
                )
                if imgs: final_images.append(imgs[0])
            except Exception as e: logger.error(f"Error fetching page {page_num}: {e}")
        return final_images

    def _clean_signing_party(self, party_name):
        if not party_name: return ""
        party_name = str(party_name)
        if party_name.lower().strip().replace(" ", "") in ["telenity", "telenityfze", "telenityinc"]: return ""
        if " and " in party_name.lower():
            parts = re.split(r' and | & ', party_name, flags=re.IGNORECASE)
            for part in parts:
                if "telenity" not in part.lower(): return part.strip()
        party_name = re.sub(r'(?i)^Telenity.*?(and|&)\s*', '', party_name)
        return party_name.strip()

    def _clean_contract_name(self, name):
        if not name: return "Belirtilmemiş"
        name = str(name)
        name = name.replace("<InsertDate>", "").strip()
        if len(name) > 100: name = name[:100]
        if any(x in name.lower() for x in ["agreement is made", "hereinafter", "entered into"]): return ""
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
        if visual_count == 1: return "Fully Signed" 
        if "telenity" in sig: return "Telenity Signed"
        return "Telenity Signed"

    def _safe_str(self, data):
        if data is None: return ""
        if isinstance(data, (dict, list)): return "" 
        return str(data).strip()

    def process_single_file(self, filename: str, folder_path: str, job_root: str = None) -> Dict[str, Any]:
        full_path = os.path.join(folder_path, filename)
        
        # GÜVENLİ YOL (HASH İÇİN)
        safe_full_path = self._get_safe_path(full_path)
        
        db = None
        try:
            file_hash = self.calculate_file_hash(full_path) # İçinde safe_path kullanıyor
            if not file_hash: return {"error": "Hash error - File access failed", "dosya_adi": filename}

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
                    "confidence_score": cached.confidence_score,
                    "durum_notu": "Önbellekten"
                }
                db.close()
                return result

            folder_company_name = ""
            if job_root:
                abs_folder = os.path.abspath(folder_path)
                abs_root = os.path.abspath(job_root)
                if abs_folder.startswith(abs_root):
                    rel_path = os.path.relpath(abs_folder, abs_root)
                    top_subfolder = rel_path.split(os.sep)[0]
                    if top_subfolder and top_subfolder != ".":
                        folder_company_name = top_subfolder
                        logger.info(f"📁 Folder-based Company Detected: '{folder_company_name}'")

            text = ""
            is_scanned = False
            num_pages = 0
            pdf_corruption_type = None
            
            try:
                reader = PdfReader(safe_full_path) # Safe path ile oku
                num_pages = len(reader.pages)
                for page in reader.pages: txt = page.extract_text(); text += (txt or "") + "\n"
            except Exception as e:
                # Classify corruption type for statistics
                error_msg = str(e).lower()
                if "command token too long" in error_msg:
                    pdf_corruption_type = "Token Overflow"
                elif "eof marker not found" in error_msg:
                    pdf_corruption_type = "Missing EOF"
                elif "xref" in error_msg or "trailer" in error_msg:
                    pdf_corruption_type = "Broken XRef Table"
                elif "startxref not found" in error_msg:
                    pdf_corruption_type = "Missing startxref"
                elif "invalid elementary object" in error_msg:
                    pdf_corruption_type = "Corrupt Objects"
                else:
                    pdf_corruption_type = "Unknown"
                
                # Silent fallback - only log once at INFO level
                logger.info(f"📄 {filename}: Corrupt PDF detected ({pdf_corruption_type}), using OCR fallback")
                
                # Track for summary report
                self.corrupt_pdfs.append({
                    'filename': filename,
                    'error_type': pdf_corruption_type,
                    'folder': folder_company_name or os.path.basename(folder_path)
                })
                
                is_scanned = True
                try:
                    info = self._suppress_poppler_stderr(
                        pdfinfo_from_path,
                        full_path, 
                        poppler_path=POPPLER_PATH
                    )
                    num_pages = info["Pages"]
                except: num_pages = 1

            if not text or len(text.strip()) < 100:
                is_scanned = True
                logger.info(f"Detected SCANNED document: {filename}")

            # --- Quality Analysis ---
            quality_report = None
            if filename.lower().endswith('.pdf'):
                try:
                    quality_report = self.quality_checker.analyze(full_path)
                except Exception as qe:
                    logger.warning(f"Quality analysis failed: {qe}")

            target_page_indices = self.identify_key_pages(full_path, num_pages)
            llm_images = self.get_optimized_images_for_llm(full_path, target_page_indices)

            if is_scanned and llm_images: 
                if not text.strip():
                    logger.info("Running Parallel OCR...")
                    # Parallel OCR processing (4x faster)
                    def ocr_single(img):
                        try:
                            quality = getattr(quality_report, 'score', 50) if quality_report else 50
                            processed = ImageProcessor.preprocess_image(img, quality_score=quality)
                            return pytesseract.image_to_string(processed, lang="tur+eng", config=TESSERACT_CONFIG)
                        except Exception as ocr_err:
                            logger.error(f"OCR failed for a page: {ocr_err}")
                            return ""
                    
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=min(4, len(llm_images))) as executor:
                        results = list(executor.map(ocr_single, llm_images))
                    text = "\n".join(results)

            filename_date = extract_date_from_filename(filename)
            filename_contract_name = extract_contract_name_from_filename(filename)

            use_vision = USE_VISION_MODEL
            if quality_report:
                try:
                    if getattr(quality_report, 'is_scanned', False) or getattr(quality_report, 'score', 100) < 70:
                        use_vision = True
                except Exception:
                    pass

            vision_images_b64 = []
            if use_vision and llm_images:
                vision_images_b64 = self._images_to_base64(llm_images)

            # Generate adaptive hints from feedback service
            adaptive_hint = ""
            if self.feedback_service:
                try:
                    adaptive_hint = generate_adaptive_hints(self.feedback_service)
                except Exception:
                    pass

            # Primary path: provider with engineered prompts (vision or text)
            llm_data: Dict[str, Any] = {}
            try:
                messages = build_contract_extraction_messages(
                    text=text,
                    filename=filename,
                    images_b64=vision_images_b64 if use_vision else None,
                    quality_report=quality_report,
                    adaptive_hint=adaptive_hint or None
                )
                raw_resp = self.provider.chat(messages)
                parsed = parse_json_response(raw_resp)
                if parsed: llm_data = parsed
            except Exception as pe:
                logger.info(f"Provider path failed, fallback to legacy LLMClient: {pe}")

            if not llm_data:
                llm_data = self.llm_client.get_analysis(text, filename, vision_images_b64, filename_date)

            telenity_search_text = (self._safe_str(llm_data.get("found_telenity_name", "")) or "") + " " + text[:2000]
            telenity_code, telenity_full = determine_telenity_entity(telenity_search_text)
            if USE_VISION_MODEL and (not telenity_code or telenity_code == "Bilinmiyor") and vision_images_b64:
                vision_res = self.llm_client.detect_telenity_visual(vision_images_b64[0])
                if vision_res: telenity_code, telenity_full = vision_res

            # --- CONTRACT NAME MANTIĞI (DÜZELTİLDİ) ---
            raw_llm_title = self._safe_str(llm_data.get("contract_name", ""))
            llm_contract_name = clean_contract_name(raw_llm_title)
            
            final_contract_name = "Agreement"
            
            # Kural 1: LLM spesifik bir şey bulduysa (Agreement/Contract hariç) -> KULLAN
            if llm_contract_name and len(llm_contract_name) > 3 and llm_contract_name.lower() not in ["agreement", "contract", "sözleşme"]:
                final_contract_name = llm_contract_name
            # Kural 2: LLM genel konuştuysa, dosya ismine bak
            elif filename_contract_name and len(filename_contract_name) > 3 and filename_contract_name.lower() not in ["agreement", "contract"]:
                final_contract_name = filename_contract_name
                logger.info(f"LLM title weak. Using filename title: '{final_contract_name}'")
            elif llm_contract_name:
                final_contract_name = llm_contract_name
            
            contract_name = final_contract_name
            # ------------------------------------------

            raw_party = self._safe_str(llm_data.get("signing_party", ""))
            final_party = ""
            confidence = 0
            try: confidence = int(llm_data.get("confidence_score", 0))
            except: confidence = 0

            if folder_company_name:
                final_party = self._clean_signing_party(folder_company_name)
                confidence = 100 
                logger.info(f"Using Folder Name as Party: '{final_party}'")
            else:
                final_party = self._clean_signing_party(raw_party)
                if not final_party:
                    fn_comp = extract_company_from_filename(filename)
                    if fn_comp:
                        logger.info(f"Recovered party from filename: '{fn_comp}'")
                        final_party = fn_comp

            raw_address = self._safe_str(llm_data.get("address", ""))
            address = filter_telenity_address(clean_turkish_chars(raw_address))
            raw_country = self._safe_str(llm_data.get("country", ""))
            inferred = infer_country_from_address(address)
            final_country = inferred if inferred else normalize_country(raw_country)
            
            # TARİH: Dosya ismi öncelikli, yoksa LLM'den
            final_date = filename_date if filename_date else self._safe_str(llm_data.get("signed_date", ""))
            
            # FALLBACK: Eğer tarih hala boşsa, dosya isminden agresif çıkarım
            if not final_date:
                date_from_name = extract_date_from_filename(filename, aggressive=True)
                if date_from_name:
                    final_date = date_from_name
                    logger.info(f"📅 Forced date from filename: {final_date}")

            import json
            kb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "known_companies.json")
            known_db = {}
            try:
                if os.path.exists(kb_path):
                    with open(kb_path, "r", encoding="utf-8") as f: known_db = json.load(f)
            except: pass

            if final_party:
                match = find_best_company_match(final_party, known_db, threshold=80)
                if match:
                    logger.info(f"🧠 Fuzzy Match: '{final_party}' found in DB")
                    if not address: address = match.get("address", "")
                    if not final_country: final_country = match.get("country", "")
                    confidence = 100

            should_verify = False
            if confidence < 90: should_verify = True
            if not address or len(address) < 5: should_verify = True
            if not final_country: should_verify = True
            if final_country == "Turkey" and inferred and inferred != "Turkey": should_verify = True

            if should_verify:
                logger.info(f"🔍 Verifying '{filename}'...")
                current_data = {"signing_party": final_party, "address": address, "country": final_country, "signed_date": final_date, "contract_name": contract_name}
                verified = self.llm_client.verify_extraction(current_data, text, filename)
                if verified:
                    np = self._clean_signing_party(self._safe_str(verified.get("signing_party")))
                    if np: final_party = np
                    na = filter_telenity_address(clean_turkish_chars(self._safe_str(verified.get("address"))))
                    if na: address = na
                    nc = self._safe_str(verified.get("country"))
                    ic = infer_country_from_address(address)
                    final_country = ic if ic else normalize_country(nc)
                    nd = self._safe_str(verified.get("signed_date"))
                    if nd and not filename_date: final_date = nd
                    
                    # Contract name düzeltme
                    vt = clean_contract_name(self._safe_str(verified.get("contract_name")))
                    if vt and vt != "Agreement": contract_name = vt

                    if address and final_country: confidence = 95

            final_score = confidence
            if not final_party: final_score -= 50
            if not address or len(address) < 5: final_score -= 15
            if not final_country: final_score -= 10
            if not final_date: final_score -= 10
            final_score = max(0, min(100, final_score))
            
            # --- MULTI-STAGE VALIDATION ---
            logger.info("🔍 Running multi-stage validation...")
            validation_result = validate_contract(
                party=final_party,
                contract_type=contract_name,
                signed_date=final_date,
                start_date=llm_data.get("start_date", ""),
                end_date=llm_data.get("end_date", ""),
                address=address,
                country=final_country,
                initial_confidence=final_score,
                ocr_quality=llm_data.get("ocr_quality", 50.0),
                llm_confidence=confidence
            )
            
            # Update confidence with validation score
            final_score = validation_result.overall_confidence
            needs_review = validation_result.needs_review
            review_reason = validation_result.review_reason if needs_review else ""
            
            if validation_result.critical_issues:
                logger.warning(f"⚠️ {len(validation_result.critical_issues)} critical issues: {validation_result.critical_issues[:2]}")
            if needs_review:
                logger.info(f"👁️ Manual review needed: {review_reason}")
            
            # --- FINAL ENRICHMENT: Web search for missing data ---
            needs_enrichment = False
            if (not address or len(address.strip()) < 10) and final_party:
                needs_enrichment = True
            if (not final_country or final_country.strip() in ["", "Unknown"]) and final_party:
                needs_enrichment = True
            
            if needs_enrichment:
                logger.info(f"🌐 Final enrichment for '{final_party}'...")
                try:
                    enriched_address, enriched_country = enrich_missing_data(final_party, address, final_country)
                    if enriched_address and len(enriched_address) > len(address):
                        address = enriched_address
                        logger.info(f"✅ Enriched address: {address[:50]}...")
                    if enriched_country and not final_country:
                        final_country = enriched_country
                        logger.info(f"✅ Enriched country: {final_country}")
                    
                    # Boost confidence if enrichment succeeded
                    if address and final_country:
                        final_score = min(100, final_score + 10)
                except Exception as enrich_err:
                    logger.warning(f"Enrichment failed: {enrich_err}")

            if final_party and address and final_country and len(address) > 10 and final_score > 80:
                p_key = final_party.lower().strip()
                if p_key not in known_db:
                    known_db[p_key] = {"full_name": final_party, "address": address, "country": final_country}
                    try:
                        with open(kb_path, "w", encoding="utf-8") as f: json.dump(known_db, f, indent=4, ensure_ascii=False)
                    except: pass

            visual_sig_count = len([p for p in target_page_indices if p != 0])
            final_sig = self._map_signature_smart(self._safe_str(llm_data.get("text_signature_status", "")), visual_sig_count)

            db.close()
            return {
                "dosya_adi": filename, "contract_name": contract_name,
                "doc_type": self._map_choice(llm_data.get("doc_type"), DOC_TYPE_CHOICES),
                "signature": final_sig,
                "company_type": self._map_choice(llm_data.get("company_type"), COMPANY_CHOICES),
                "signing_party": final_party, "country": final_country, "address": address,
                "signed_date": final_date,
                "telenity_entity": telenity_code, "telenity_fullname": telenity_full,
                "confidence_score": final_score,
                "needs_review": needs_review,
                "review_reason": review_reason,
                "validation_issues": len(validation_result.critical_issues),
                "validation_warnings": len(validation_result.warnings),
                "durum_notu": "Tamamlandı", "file_hash": file_hash,
            }

        except Exception as e:
            logger.error(f"Processing error {filename}: {e}")
            traceback.print_exc()
            if db: db.close()
            return {"error": str(e), "dosya_adi": filename}

    def run_job(self, job_id: int, folder_path: str):
        # (Aynı kalabilir, rollback mekanizması zaten eklenmişti)
        db = SessionLocal()
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if not job: db.close(); return
        except Exception as e:
            logger.error(f"Initial DB error: {e}")
            db.close(); return

        try:
            job.status = "RUNNING"; job.message = "Analiz (Smart Scan) başlıyor..."; db.commit()
            connected, _ = self.llm_client.autodetect_connection()
            if not connected: logger.warning("LM Studio bağlantısı yok.")
            
            all_files_to_process = []
            logger.info(f"Scanning folder recursively: {folder_path}")
            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith(".pdf"): all_files_to_process.append((f, root))
            
            total = len(all_files_to_process)
            if total == 0: job.status = "COMPLETED"; job.message = "Dosya bulunamadı"; db.commit(); return

            processed = 0
            batches = [all_files_to_process[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
            all_contracts = []

            for batch in batches:
                try:
                    db.refresh(job)
                    if job.status == "CANCELLED": break
                except Exception:
                    db.rollback()
                    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                    if not job: break

                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(self.process_single_file, f, root, folder_path): f 
                        for f, root in batch
                    }
                    for future in as_completed(futures):
                        res = future.result()
                        if "error" not in res: all_contracts.append(Contract(job_id=job_id, **res))
                        processed += 1
                        
                        if processed % 2 == 0:
                            try:
                                job.progress = int((processed / total) * 100)
                                job.message = f"İşleniyor: {processed}/{total}"
                                db.commit()
                            except Exception as e:
                                logger.warning(f"Progress update error (ignoring): {e}")
                                db.rollback()
                                job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            
            if all_contracts:
                try:
                    db.bulk_save_objects(all_contracts)
                    db.commit()
                except Exception as e:
                    logger.error(f"Bulk save failed: {e}")
                    db.rollback()

            try:
                job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                if job:
                    # Generate corruption summary
                    summary_msg = f"Tamamlandı ({processed} dosya)"
                    if self.corrupt_pdfs:
                        summary_msg += f"\n⚠️ {len(self.corrupt_pdfs)} bozuk PDF (OCR kullanıldı)"
                        
                        # Log corruption summary
                        logger.info(f"\n{'='*60}")
                        logger.info(f"📊 CORRUPTION SUMMARY ({len(self.corrupt_pdfs)} files)")
                        logger.info(f"{'='*60}")
                        
                        # Group by error type
                        error_counts = {}
                        for item in self.corrupt_pdfs:
                            error_type = item['error_type']
                            error_counts[error_type] = error_counts.get(error_type, 0) + 1
                        
                        for error_type, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
                            logger.info(f"  {error_type}: {count} files")
                        
                        logger.info(f"{'='*60}\n")
                    
                    job.status = "COMPLETED"
                    job.message = summary_msg
                    job.progress = 100
                    db.commit()
            except: db.rollback()
            
            self.export_to_excel(job_id, folder_path)

        except Exception as e:
            logger.error(f"Job failed: {e}")
            try:
                job.status = "FAILED"; job.message = str(e); db.commit()
            except: pass
        finally: db.close()

    def export_to_excel(self, job_id, output_path):
        import pandas as pd; from datetime import datetime
        db = SessionLocal()
        try:
            contracts = db.query(Contract).filter(Contract.job_id == job_id).all()
            if not contracts: return "Veri yok"
            data = []
            for c in contracts:
                data.append({
                    "Dosya Adı": c.dosya_adi, "Contract Name": c.contract_name, "Doc. Type": c.doc_type,
                    "Signature": c.signature, "Company Type": c.company_type, "Signing Party": c.signing_party,
                    "Country": c.country, "Address": c.address, "Signed Date": c.signed_date,
                    "Telenity Entity": c.telenity_entity, "Telenity Entity Full Name": c.telenity_fullname, 
                    "Güven Skoru (%)": c.confidence_score,
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
        except Exception as e: logger.error(f"Excel export failed: {e}"); return ""
        finally: db.close()
