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

        # 1. System Prompt (Tek parça string halinde düzeltildi)
        system_prompt = """Extract contract data as JSON. 
WARNING: Be precise. Do NOT hallucinate.

Field Rules:
1. doc_type: Must be exactly one of: {doc_types}. If unsure, pick closest.
2. company_type: Must be exactly one of: {company_types}.
3. contract_name: extract the specific TITLE of the agreement. 
   - Good: "Master Services Agreement", "Non-Disclosure Agreement for Project X"
   - Bad: "Agreement", "Contract", "Page 1". 
   - Do NOT include dates or addresses in the title.
4. address: Find the full address of the Counterparty (NOT Telenity). 
   - Look at the VERY END of the document (signature block).
   - Look for 'Registered Office', 'Principal Place of Business'.
5. country: Extract the country from the address found above.
6. signed_date: Look for handwritten dates in signature blocks or "Effective Date". Format: YYYY-MM-DD.
7. found_telenity_name: Find exact Telenity entity name in doc (e.g. "Telenity FZE").

Output JSON:
{{
  "contract_name": "String",
  "doc_type": "String",
  "company_type": "String",
  "signing_party": "String",
  "country": "String",
  "address": "String",
  "signed_date": "YYYY-MM-DD",
  "text_signature_status": "String",
  "found_telenity_name": "String"
}}
"""

        # 2. Context Optimization (Metin çok uzunsa başını ve sonunu birleştir)
        max_chars = 12000 
        if len(text) > max_chars:
            half = max_chars // 2
            processed_text = text[:half] + "\n...[SECTION OMITTED]...\n" + text[-half:]
        else:
            processed_text = text

        date_hint = f"\nFILE DATE: {filename_date}" if filename_date else ""
        user_prompt = f"""FILE: {filename or 'Unknown'}{date_hint}
TEXT: {processed_text}

Output JSON:
{{"contract_name":"","doc_type":"","text_signature_status":"","company_type":"","signing_party":"","country":"","address":"","signed_date":"","found_telenity_name":""}}"""
        
        system_prompt = system_prompt.format(
            doc_types=", ".join(DOC_TYPE_CHOICES),
            company_types=", ".join(COMPANY_CHOICES),
        )

        user_content = [{"type": "text", "text": user_prompt}]
        
        # Vision Image Handling
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
        
        # 3. Request & Retry Mechanism
        for attempt in range(2): 
            try:
                resp = requests.post(self.api_url, json=payload, timeout=120)
                
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    content = content.replace("```json", "").replace("```", "").strip()
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                
                last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                logger.warning(f"LLM attempt {attempt+1} failed: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM attempt {attempt+1} exception: {e}")
                time.sleep(1)

        # 4. Vision Fallback
        if images:
            logger.error(f"Vision request FAILED. Reason: {last_error}")
            logger.info("Retrying with TEXT ONLY mode...")
            return self.get_analysis(text, filename=filename, images=None, filename_date=filename_date)

        return {}

    def detect_telenity_visual(self, image_b64):
        if not self.is_connected:
            return None
            
        prompt = """
Look at this document image. Identify which Telenity company this document belongs to based on the logo, header, or letterhead.
Respond with ONLY the exact company name or "Unknown".
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
                if "FZE" in content or "Dubai" in content: return "FzE - Telenity UAE", "Telenity FZE"
                elif "Inc" in content or "Monroe" in content: return "TU - Telenity USA", "Telenity Inc"
                elif "İletişim" in content or "Turkey" in content or "Istanbul" in content: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
                elif "India" in content or "Noida" in content: return "TI - Telenity India", "Telenity Systems Software India Private Limited"
        except Exception as e:
            logger.error(f"Vision Telenity detection failed: {e}")
        
        return None
