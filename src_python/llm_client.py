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

        # src_python/llm_client.py içindeki system_prompt:

        system_prompt = """Extract contract data as JSON. 
WARNING: Strict Rules Apply.

1. signing_party: The name of the Counterparty ONLY. 
   - STRICTLY EXCLUDE "Telenity", "Telenity FZE", "Telenity Inc".
   - If text says "Between Telenity and Google", output ONLY "Google".
   - Do NOT output "Telenity and Google".

2. address: The FULL address of the Counterparty ONLY.
   - If you see Telenity's address (Maslak, Istanbul, Dubai, Monroe, Noida), IGNORE IT.
   - Look for the address under the Counterparty's signature or specific 'Notices' section.
   - If two addresses are present (Telenity & Partner), output ONLY the Partner's address.

3. country: The country of the Counterparty (derived from the address above). 
   - NOT Turkey (unless counterparty is Turkish). 
   - NOT UAE (unless counterparty is from UAE).

4. contract_name: Specific Title (e.g. "Service Agreement"). No dates.
5. signed_date: YYYY-MM-DD. Look for handwritten dates in signature block.
6. doc_type: Pick one: {doc_types}
7. company_type: Pick one: {company_types}
8. found_telenity_name: Exact Telenity entity name found in doc.

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
