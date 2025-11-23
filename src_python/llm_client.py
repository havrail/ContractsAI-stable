import requests
import json
import time
import re
from config import LM_STUDIO_IP, DOC_TYPE_CHOICES, COMPANY_CHOICES
from logger import logger

class LLMClient:
    def __init__(self):
        self.api_url = None
        self.model_name = "local-model"
        self.is_connected = False

    def autodetect_connection(self):
        logger.info("Bağlantı aranıyor...")
        endpoints = [f"{LM_STUDIO_IP}/v1", f"{LM_STUDIO_IP}"]
        for base_url in endpoints:
            try:
                resp = requests.get(f"{base_url}/models", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data and data["data"]:
                        self.model_name = data["data"][0]["id"]
                    self.api_url = f"{base_url}/chat/completions"
                    self.is_connected = True
                    return True, f"Model: {self.model_name}"
            except Exception:
                continue
        return False, "LM Studio bulunamadı."

    def get_analysis(self, text, filename=None, images=None, filename_date=None):
        if not self.is_connected:
            return {}

        # Gelişmiş Prompt
        system_prompt = """You are a legal contract analysis AI. Extract data into specific JSON fields.
Required JSON Output format:
{
  "contract_name": "String (Title only, remove dates/addresses)",
  "doc_type": "String (One of: %s)",
  "company_type": "String (One of: %s)",
  "signing_party": "String (Name of the counterparty/customer)",
  "country": "String (Country of the signing party)",
  "address": "String (Full address of the signing party. Look at the END of the document carefully)",
  "signed_date": "YYYY-MM-DD",
  "text_signature_status": "String (Fully Signed|Telenity Signed|Counterparty Signed)",
  "found_telenity_name": "String (Exact Telenity entity name found)"
}

Instructions:
1. Address is often found on the last page under 'Addresses' or 'Notices'.
2. Do NOT extract Telenity's address (Maslak, Monroe, Dubai, Noida).
3. If filename date is provided, prioritize it for 'signed_date'.
4. Fix OCR typos (e.g., 'lstanbul' -> 'İstanbul').
""" % (", ".join(DOC_TYPE_CHOICES), ", ".join(COMPANY_CHOICES))

        # SMART CONTEXT HANDLING:
        # Qwen 2.5 handles large context, but let's be safe.
        # Instead of just text[:4000], we send start + end if it's too long.
        max_chars = 32000 # Qwen 7B easily handles 32k context
        if len(text) > max_chars:
            half = max_chars // 2
            processed_text = text[:half] + "\n...[SECTION OMITTED]...\n" + text[-half:]
        else:
            processed_text = text

        date_hint = f"\nFILENAME DATE: {filename_date}" if filename_date else ""
        user_prompt = f"FILE NAME: {filename or 'Unknown'}{date_hint}\n\nDOCUMENT CONTENT:\n{processed_text}"

        user_content = [{"type": "text", "text": user_prompt}]
        
        # Vision handling
        if images:
            # Qwen VL can handle multiple images, but let's limit to first page and last page for efficiency
            # if there are many images.
            target_images = images
            if len(images) > 4:
                # First 2 pages (header/intro) + Last 2 pages (signatures)
                target_images = images[:2] + images[-2:]
            
            for img_b64 in target_images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1, # Keep low for precision
            "max_tokens": 1024,
        }

        last_error = None
        for attempt in range(2):
            try:
                # Timeout increased for larger context
                resp = requests.post(self.api_url, json=payload, timeout=180)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    # Clean markdown code blocks if present
                    content = content.replace("```json", "").replace("```", "").strip()
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM attempt {attempt+1} failed: {e}")
                time.sleep(1)

        # Vision Fallback: If vision request fails, retry with text only
        if images:
            logger.info("Vision request failed, retrying with TEXT ONLY mode...")
            return self.get_analysis(text, filename=filename, images=None, filename_date=filename_date)

        return {}

    def detect_telenity_visual(self, image_b64):
        # (Bu metodunuz zaten fena değil, aynen kalabilir)
        if not self.is_connected: return None
        prompt = "Look at this document header/footer. Identify the exact Telenity Company Name (e.g. Telenity FZE, Telenity Inc, Telenity İletişim). Return ONLY the name."
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}],
            "temperature": 0.1
        }
        try:
            resp = requests.post(self.api_url, json=payload, timeout=60)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if "FZE" in content or "Dubai" in content: return "FzE - Telenity UAE", "Telenity FZE"
                elif "Inc" in content or "Monroe" in content: return "TU - Telenity USA", "Telenity Inc"
                elif "İletişim" in content or "Turkey" in content: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
                elif "India" in content: return "TI - Telenity India", "Telenity Systems Software India Private Limited"
        except Exception as e:
            logger.error(f"Vision detection failed: {e}")
        return None
