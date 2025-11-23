# src/pipeline.py
import os
import io
import base64
import threading
import traceback
import time
import re
# OCR and LLM work are parallelized with threads for stability on Windows
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any, Callable
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import AnalysisJob, Contract
from image_processing import ImageProcessor
from llm_client import LLMClient
from utils import determine_telenity_entity, extract_date_from_filename, clean_turkish_chars, filter_telenity_address
from logger import logger
from cache import cache  # Redis cache layer
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

# DB configuration is handled in config.py; removed duplicate setup

import easyocr
import hashlib

# OCR settings
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
TESSERACT_CONFIG = "--oem 1 --psm 6"
DPI = 300

# Global worker state (initialized per process for OCR)
_worker_easyocr_reader = None

def init_ocr_worker():
    """Initialize EasyOCR reader for each OCR worker process."""
    global _worker_easyocr_reader
    _worker_easyocr_reader = easyocr.Reader(['en', 'tr'], gpu=False)
    logger.info("OCR Worker initialized with EasyOCR reader")


def ocr_worker_process_page(page_index: int, image_bytes: bytes) -> str:
    """
    Process a single page for OCR in a worker-safe function.
    This stays picklable in case we switch back to process pools.
    """
    global _worker_easyocr_reader
    
    try:
        from PIL import Image
        import numpy as np

        # Lazily initialize EasyOCR reader to avoid None access in worker threads
        if _worker_easyocr_reader is None:
            _worker_easyocr_reader = easyocr.Reader(['en', 'tr'], gpu=False)
        
        # Reconstruct image from bytes
        image = Image.open(io.BytesIO(image_bytes))
        
        # Preprocess
        processed = ImageProcessor.preprocess_image(image)
        
        # Try Tesseract first (faster)
        page_text = pytesseract.image_to_string(
            processed, lang="tur+eng", config=TESSERACT_CONFIG
        )
        
        # Fallback to EasyOCR if Tesseract yields little text
        if len(page_text.strip()) < 50:
            logger.info(f"Tesseract low text for page {page_index+1}, trying EasyOCR...")
            try:
                img_np = np.array(processed)
                easy_result = _worker_easyocr_reader.readtext(img_np, detail=0, paragraph=True)
                easy_text = "\n".join(easy_result)
                if len(easy_text) > len(page_text):
                    page_text = easy_text
                    logger.info(f"EasyOCR success: {len(page_text)} chars")
            except Exception as e:
                logger.error(f"EasyOCR failed: {e}")
        
        return page_text
    except Exception as e:
        logger.error(f"OCR worker error on page {page_index}: {e}")
        return ""


class PipelineManager:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        # Optional UI logger callback (desktop app compatibility)
        self.log_callback = log_callback
        # For backward compatibility and non-OCR tasks
        self.llm_client = LLMClient()
        # Keep reader for fallback/compatibility
        self.reader = easyocr.Reader(['en', 'tr'], gpu=False)

    def _log(self, level: str, message: str):
        """Send log both to standard logger and optional UI callback."""
        logger_fn = getattr(logger, level, logger.info)
        logger_fn(message)
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                # UI callback failures should not crash processing
                logger.debug("UI log callback failed", exc_info=True)

    def calculate_file_hash(self, filepath: str) -> Optional[str]:
        """Calculates MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Hash calculation error: {e}")
            return None

    def extract_text_native(self, full_path: str) -> str:
        try:
            reader = PdfReader(full_path)
            texts = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    texts.append(txt)
            return "\n".join(texts)
        except Exception as e:
            logger.error(f"Text extract error: {e}")
            return ""

    def ocr_sampled_pages(self, images: List[Any]) -> str:
        """
        Perform OCR on sampled pages using a ThreadPool for stability on Windows.
        Tesseract runs out-of-process so threads still give parallelism without worker crashes.
        """
        if not images: return ""
        
        page_count = len(images)
        sample_indices = set()
        sample_indices.update(range(min(3, page_count)))
        if page_count > 6:
            mid_start = max(3, page_count // 2 - 1)
            sample_indices.update(range(mid_start, min(mid_start + 3, page_count)))
        if page_count > 3:
            sample_indices.update(range(max(0, page_count - 3), page_count))

        # Convert images to bytes for pickling
        image_data = []
        for i in sorted(sample_indices):
            buf = io.BytesIO()
            images[i].save(buf, format="PNG")
            image_data.append((i, buf.getvalue()))
        
        # Use ThreadPoolExecutor for OCR stability (ProcessPoolExecutor caused crashes)
        # Tesseract is an external process, so it releases GIL anyway
        ocr_results = {}
        try:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(image_data))) as executor:
                futures = {executor.submit(ocr_worker_process_page, idx, img_bytes): idx 
                          for idx, img_bytes in image_data}
                
                for future in as_completed(futures):
                    page_idx = futures[future]
                    try:
                        page_text = future.result()
                        ocr_results[page_idx] = page_text
                    except Exception as e:
                        logger.error(f"OCR future error for page {page_idx}: {e}")
                        ocr_results[page_idx] = ""
        except Exception as e:
            logger.error(f"ThreadPoolExecutor error in OCR: {e}")
            # Fallback to sequential processing
            for idx, img_bytes in image_data:
                try:
                    from PIL import Image
                    image = Image.open(io.BytesIO(img_bytes))
                    processed = ImageProcessor.preprocess_image(image)
                    page_text = pytesseract.image_to_string(processed, lang="tur+eng", config=TESSERACT_CONFIG)
                    ocr_results[idx] = page_text
                except Exception as inner_e:
                    logger.error(f"Fallback OCR error for page {idx}: {inner_e}")
                    ocr_results[idx] = ""
        
        # Combine results in order
        ocr_text = ""
        for idx in sorted(ocr_results.keys()):
            ocr_text += ocr_results[idx] + "\n"
        
        return ocr_text

    def _images_to_base64(self, images: List[Any]) -> List[str]:
        b64_list = []
        if not images: return b64_list
        page_count = len(images)
        sample_indices = set()
        sample_indices.update(range(min(2, page_count)))
        if page_count > 3:
            sample_indices.add(page_count - 1)
        for i in sorted(sample_indices):
            buf = io.BytesIO()
            images[i].save(buf, format="JPEG", quality=80)
            b64_list.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
        return b64_list

    def process_single_file(self, filename: str, folder_path: str) -> Dict[str, Any]:
        full_path = os.path.join(folder_path, filename)
        db = None
        try:
            # 1. Calculate File Hash
            file_hash = self.calculate_file_hash(full_path)
            if not file_hash:
                return {"error": "Could not calculate file hash", "dosya_adi": filename}
            ocr_cache_key = file_hash or full_path

            # 2. Check Cache (Database)
            db = next(get_db())
            cached = db.query(Contract).filter(Contract.file_hash == file_hash).first()
            if cached:
                logger.info(f"DB Cache HIT: {filename}")
                db.close()
                return {
                    "dosya_adi": filename,
                    "contract_name": cached.contract_name,
                    "doc_type": cached.doc_type,
                    "company_type": cached.company_type,
                    "signing_party": cached.signing_party,
                    "country": cached.country,
                    "address": cached.address,
                    "signed_date": str(cached.signed_date) if cached.signed_date else "",
                    "signature": cached.signature,
                    "telenity_entity": cached.telenity_entity,
                    "telenity_fullname": cached.telenity_fullname,
                    "file_hash": file_hash,
                    "durum_notu": "Önbellekten Alındı"
                }

            # 3. Check Redis Cache for OCR result
            cached_ocr = cache.get_ocr_result(ocr_cache_key)
            text = ""
            images = [] # Initialize images here for scope
            visual_count = 0 # Initialize visual_count

            if cached_ocr:
                text = cached_ocr
                logger.info(f"Redis OCR cache HIT: {filename}")
            else:
                # 3. Extract Text (PyPDF2)
                try:
                    reader = PdfReader(full_path)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                except Exception as e:
                    logger.warning(f"PyPDF2 failed for {filename}: {e}")

                # Convert images for OCR and visual signature count
                try:
                    images = convert_from_path(full_path, dpi=DPI, poppler_path=POPPLER_PATH)
                    visual_count = ImageProcessor.count_visual_signatures(images)
                except Exception as e:
                    logger.error(f"PDF to image conversion failed for {filename}: {e}")
                    if db:
                        db.close()
                    return {"error": f"OCR convert failed: {e}", "dosya_adi": filename}

                # 4. OCR Fallback (if text is empty or too short)
                if not text or len(text.strip()) < 50:
                    logger.info(f"Native text too short for {filename}, performing OCR...")
                    if not images:
                        try:
                            images = convert_from_path(full_path, dpi=DPI, poppler_path=POPPLER_PATH)
                        except Exception as e:
                            logger.error(f"PDF to image conversion failed for {filename}: {e}")
                            if db:
                                db.close()
                            return {"error": f"OCR convert failed: {e}", "dosya_adi": filename}
                    ocr_text = self.ocr_sampled_pages(images)
                    text += "\n" + ocr_text
                    
                # Cache OCR result in Redis
                cache.set_ocr_result(ocr_cache_key, text)
            
            # If images were not loaded from cache, load them now for LLM vision or visual count
            if not images:
                try:
                    images = convert_from_path(full_path, dpi=DPI, poppler_path=POPPLER_PATH)
                    visual_count = ImageProcessor.count_visual_signatures(images)
                except Exception as e:
                    logger.error(f"PDF to image conversion failed for {filename}: {e}")
                    if db:
                        db.close()
                    return {"error": f"OCR convert failed: {e}", "dosya_adi": filename}

            # 5. Extract Date from Filename
            filename_date = extract_date_from_filename(filename)

            # 6. Check Redis Cache for LLM result
            llm_cache_key = file_hash or (filename + text[:1000])
            cached_llm = cache.get_llm_result(llm_cache_key) # Use file hash as primary key
            llm_data = {}

            if cached_llm:
                logger.info(f"Redis LLM cache HIT: {filename}")
                llm_data = cached_llm
            else:
                # 6. LLM Analysis
                if USE_VISION_MODEL:
                    vision_images = self._images_to_base64(images)
                    llm_data = self.llm_client.get_analysis(text, filename=filename, images=vision_images, filename_date=filename_date)
                else:
                    llm_data = self.llm_client.get_analysis(text, filename=filename, filename_date=filename_date)
                
                # Cache LLM result in Redis
                if llm_data:
                    cache.set_llm_result(llm_cache_key, llm_data)
            
            # Combine LLM found name with full text for better detection context
            # We prioritize the specific name LLM found, but fall back to searching the whole text
            telenity_search_text = (llm_data.get("found_telenity_name", "") or "") + " " + text
            telenity_code, telenity_full = determine_telenity_entity(telenity_search_text)
            
            # Vision LLM Fallback for Telenity Detection
            if USE_VISION_MODEL and (telenity_code == "Bilinmiyor" or not telenity_code):
                logger.info(f"Text-based Telenity detection failed for {filename}. Trying Vision LLM...")
                vision_images = self._images_to_base64(images)
                if vision_images:
                    vision_result = self.llm_client.detect_telenity_visual(vision_images[0])
                    if vision_result:
                        telenity_code, telenity_full = vision_result
                        logger.info(f"Vision LLM detected: {telenity_code}")
            
            doc_type = self._map_choice(llm_data.get("doc_type", ""), DOC_TYPE_CHOICES, default="Other")
            company_type = self._map_choice(llm_data.get("company_type", ""), COMPANY_CHOICES, default="Other")
            final_sig = self._map_signature(llm_data.get("text_signature_status", ""), visual_count)
            
            # Use filename date if available, otherwise use LLM date
            final_date = filename_date or llm_data.get("signed_date", "")
            
            # Clean and filter address
            raw_address = llm_data.get("address", "")
            cleaned_address = clean_turkish_chars(raw_address) if raw_address else ""
            filtered_address = filter_telenity_address(cleaned_address)

            # Post-process LLM data
            # Clean contract_name: remove any address-like patterns or placeholders
            contract_name = llm_data.get("contract_name", "").strip()
            
            # 1. Remove placeholder tags
            if "<InsertDate>" in contract_name:
                contract_name = contract_name.replace("<InsertDate>", "").strip()
                
            # 2. Strict Length Check: If too long, it's likely a sentence or garbage
            if len(contract_name) > 80:
                logger.warning(f"Contract name too long ({len(contract_name)} chars). Truncating/Clearing.")
                # Try to split by common separators and take the first part if reasonable
                parts = re.split(r'[:;-]', contract_name)
                if parts and len(parts[0]) < 80:
                    contract_name = parts[0].strip()
                else:
                    contract_name = "" # Clear it if it's just a long mess

            # 3. Keyword Filter: Remove if it contains legal boilerplate
            boilerplate_keywords = ["hereinafter", "by and between", "entered into", "agreement is made", "service partner agreement including"]
            if any(kw in contract_name.lower() for kw in boilerplate_keywords):
                 contract_name = ""

            # 4. Address Heuristic: if contract_name looks like an address (contains digits and street keywords), clear it
            address_keywords = ["Sokak", "Cadde", "Mahallesi", "Street", "Avenue", "Blok", "No", "No.", r"\d"]
            if any(kw.lower() in contract_name.lower() for kw in address_keywords):
                contract_name = ""
            # Ensure address field does not contain placeholders
            address = filtered_address
            if "<InsertDate>" in address:
                address = address.replace("<InsertDate>", "").strip()
            # Build result dict with cleaned fields
            db.close() # Close DB session before returning
            return {
                "dosya_adi": filename,
                "contract_name": contract_name or "Belirtilmemiş",
                "doc_type": doc_type,
                "signature": final_sig,
                "company_type": company_type,
                "signing_party": llm_data.get("signing_party", ""),
                "country": llm_data.get("country", ""),
                "address": address,
                "signed_date": final_date,
                "telenity_entity": telenity_code,
                "telenity_fullname": telenity_full,
                "durum_notu": "Tamamlandı",
                "file_hash": file_hash,
            }
        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            if db:
                db.close() # Ensure DB session is closed on error
            return {"error": str(e), "dosya_adi": filename}

    def _map_choice(self, value, options, default="Other"):
        if not isinstance(value, str): value = "" if value is None else str(value)
        val = value.strip().lower()
        for opt in options:
            if val == opt.lower(): return opt
        for opt in options:
            if opt.lower() in val: return opt
        return default

    def _map_signature(self, text_sig, visual_count):
        if not isinstance(text_sig, str): text_sig = "" if text_sig is None else str(text_sig)
        sig = text_sig.lower()
        if "fully" in sig or "both" in sig: return "Fully Signed"
        if "counter" in sig or "partner" in sig or "vendor" in sig or "customer" in sig: return "Counterparty Signed"
        if "telenity" in sig: return "Telenity Signed"
        if visual_count >= 2: return "Fully Signed"
        if visual_count == 1: return "Counterparty Signed"
        return "Telenity Signed"

    def run_job(self, job_id: int, folder_path: str):
        db = SessionLocal()
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            db.close()
            return

        try:
            job.status = "RUNNING"
            job.message = "Analiz başlıyor..."
            db.commit()

            connected, conn_msg = self.llm_client.autodetect_connection()
            if not connected:
                job.status = "FAILED"
                job.message = "LM Studio bulunamadı"
                db.commit()
                logger.error(f"LM Studio connection failed: {conn_msg}")
                return
            logger.info(f"LM Studio connected: {conn_msg}")

            if not os.path.exists(TESSERACT_CMD):
                job.status = "FAILED"
                job.message = "Tesseract yolu bulunamadı"
                db.commit()
                logger.error(f"Tesseract not found at {TESSERACT_CMD}")
                return

            if POPPLER_PATH and not os.path.exists(POPPLER_PATH):
                job.status = "FAILED"
                job.message = "Poppler yolu bulunamadı"
                db.commit()
                logger.error(f"Poppler not found at {POPPLER_PATH}")
                return

            files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
            total_files = len(files)
            logger.info(f"Starting job {job_id}: {total_files} files to process")
            
            if not files:
                job.status = "COMPLETED"
                job.message = "No PDF files found"
                job.progress = 100
                db.commit()
                logger.warning(f"No PDF files found in {folder_path}")
                return

            processed_count = 0
            start_time = time.time()
            
            # Smart Batching: Split files into batches for memory efficiency
            from config import BATCH_SIZE
            batches = [files[i:i + BATCH_SIZE] for i in range(0, len(files), BATCH_SIZE)]
            total_batches = len(batches)
            
            logger.info(f"Processing {total_files} files in {total_batches} batches (batch size: {BATCH_SIZE}, workers: {MAX_WORKERS})")
            
            # Collect all contracts for bulk insert
            all_contracts = []
            
            # Process each batch
            for batch_idx, batch_files in enumerate(batches, 1):
                batch_start = time.time()
                logger.info(f"Starting batch {batch_idx}/{total_batches} with {len(batch_files)} files")
                
                # Aggressive Parallelism: Process batch with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {executor.submit(self.process_single_file, f, folder_path): f for f in batch_files}
                    
                    for future in as_completed(futures):
                        # Check for cancellation
                        db.refresh(job)
                        if job.status == "CANCELLED":
                            logger.info(f"Job {job_id} cancelled")
                            db.close()
                            return
                        
                        try:
                            result = future.result()
                            
                            if "error" not in result:
                                # Create contract object
                                contract = Contract(job_id=job_id, **result)
                                all_contracts.append(contract)
                            else:
                                logger.error(f"File error: {result.get('error')}")
                            
                            processed_count += 1
                            
                            # Update progress
                            progress = int((processed_count / total_files) * 100)
                            elapsed = time.time() - start_time
                            remaining = (elapsed / processed_count) * (total_files - processed_count) if processed_count > 0 else 0
                            
                            job.progress = progress
                            job.message = f"Batch {batch_idx}/{total_batches}: {processed_count}/{total_files} files"
                            job.estimated_remaining_seconds = int(remaining)
                            
                            # Periodic DB update (every 5 files)
                            if processed_count % 5 == 0:
                                db.commit()
                                logger.info(f"Progress: {progress}% ({processed_count}/{total_files})")
                                
                        except Exception as e:
                            logger.error(f"Error in batch processing: {e}")
                            traceback.print_exc()
                
                batch_elapsed = time.time() - batch_start
                avg_per_file = batch_elapsed / len(batch_files) if len(batch_files) > 0 else 0
                logger.info(f"Batch {batch_idx}/{total_batches} completed in {batch_elapsed:.1f}s (avg {avg_per_file:.1f}s/file)")
            
            # Bulk save all contracts at once (performance optimization)
            if all_contracts:
                logger.info(f"Bulk saving {len(all_contracts)} contracts to database...")
                db.bulk_save_objects(all_contracts)
                db.commit()
                logger.info("Bulk save completed")
            
            # Export to Excel
            try:
                excel_path = self.export_to_excel(job_id, folder_path)
                logger.info(f"Excel export completed: {excel_path}")
            except Exception as e:
                logger.error(f"Excel export error: {e}")
            
            # Final status update
            total_time = time.time() - start_time
            job.status = "COMPLETED"
            job.message = f"Tamamlandı. {processed_count} dosya işlendi ({total_time:.1f}s)"
            job.progress = 100
            db.commit()
            logger.info(f"Job {job_id} completed successfully in {total_time:.1f}s")
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            traceback.print_exc()
            job.status = "FAILED"
            job.message = f"Hata: {str(e)}"
            db.commit()
        finally:
            db.close()


    def export_to_excel(self, job_id, output_path):
        import pandas as pd
        from datetime import datetime
        
        db = SessionLocal()
        try:
            contracts = db.query(Contract).filter(Contract.job_id == job_id).all()
            if not contracts:
                return "Veri yok"
            
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
        finally:
            db.close()
