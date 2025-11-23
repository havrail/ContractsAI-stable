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

        # Optimized system prompt (60% fewer tokens)
        system_prompt = """Extract contract data as JSON. Use ONLY these options:
doc_type: {doc_types}
company_type: {company_types}
text_signature_status: Fully Signed|Telenity Signed|Counterparty Signed

Required fields:
- contract_name: title only (no address/date)
- signing_party: non-Telenity party name
- country: signing party country
- address: signing party FULL address (check entire doc - start, signature block, parties section). NOT Telenity addresses (Maslak, Monroe, Dubai)
- signed_date: YYYY-MM-DD (use filename date if provided, else from doc)
- found_telenity_name: exact Telenity entity name in doc (e.g. "Telenity FZE", "Telenity İletişim Sistemleri...")

Rules: Fix OCR errors (lstanbul→İstanbul). No placeholders (<InsertDate>). Prioritize filename date. Find address carefully (often after "Adres:", "Address:", "Mukim:")."""

        # Prepare user prompt (concise)
        date_hint = f"\nFILE DATE: {filename_date}" if filename_date else ""
        user_prompt = f"""FILE: {filename or 'Unknown'}{date_hint}
TEXT: {text[:4000]}...

Output JSON:
{{"contract_name":"","doc_type":"","text_signature_status":"","company_type":"","signing_party":"","country":"","address":"","signed_date":"","found_telenity_name":""}}"""
        # Fill placeholders in system prompt
        system_prompt = system_prompt.format(
            doc_types=", ".join(DOC_TYPE_CHOICES),
            company_types=", ".join(COMPANY_CHOICES),
        )

        user_content = [{"type": "text", "text": user_prompt}]
        if images:
            for img_b64 in images:
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
            "temperature": 0.1,
            "stream": False,
        }

        last_error = None
        # Retry mechanism
        for attempt in range(3):
            try:
                resp = requests.post(self.api_url, json=payload, timeout=120)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                break
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM request failed (attempt {attempt+1}): {e}")
                time.sleep(2)

        # If vision payload failed (e.g., model without image support), retry once without images
        if images and last_error:
            logger.info("Vision request failed, retrying without images")
            return self.get_analysis(text, filename=filename, images=None, filename_date=filename_date)

        return {}

    def detect_telenity_visual(self, image_b64):
        """Uses Vision LLM to detect Telenity entity from logo/header in image."""
        if not self.is_connected:
            return None
            
        prompt = """
Look at this document image. Identify which Telenity company this document belongs to based on the logo, header, or letterhead.

Options:
- Telenity FZE (UAE, Dubai)
- Telenity Inc (USA, Monroe)
- Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş. (Turkey, Istanbul)
- Telenity Systems Software India Private Limited (India, Noida)

Respond with ONLY the exact company name from the options above, or "Unknown" if you cannot determine it.
"""
        
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "stream": False,
        }
        
        try:
            resp = requests.post(self.api_url, json=payload, timeout=60)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                # Map response to our codes
                if "FZE" in content or "Dubai" in content:
                    return "FzE - Telenity UAE", "Telenity FZE"
                elif "Inc" in content or "Monroe" in content:
                    return "TU - Telenity USA", "Telenity Inc"
                elif "İletişim" in content or "Turkey" in content or "Istanbul" in content:
                    return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
                elif "India" in content or "Noida" in content:
                    return "TI - Telenity India", "Telenity Systems Software India Private Limited"
        except Exception as e:
            logger.error(f"Vision Telenity detection failed: {e}")
        
        return None
