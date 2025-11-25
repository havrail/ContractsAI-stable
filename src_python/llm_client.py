import requests
import json
import time
import re
from config import LM_STUDIO_IP, DOC_TYPE_CHOICES, COMPANY_CHOICES
from model_provider import ModelProvider
from logger import logger

class LLMClient:
    def __init__(self):
        self.api_url = None
        self.model_name = "local-model"
        self.is_connected = False
        # Yeni: unified provider (Qwen / Llama / Ollama)
        self.provider = ModelProvider(vision_enabled=True)

    def autodetect_connection(self):
        logger.info("Bağlantı aranıyor...")
        # Always add /v1 suffix for LM Studio
        lm_studio_url = LM_STUDIO_IP.rstrip("/") + "/v1"
        endpoints = [lm_studio_url, LM_STUDIO_IP]
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
        # Eğer unified provider aktifse onu kullan
        if self.provider.active_backend:
            try:
                system_prompt = """You are a contract extraction engine. Return strict JSON only."""
                messages = [
                    {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "text", "text": f"FILE: {filename}\n{text}"}]}
                ]
                imgs_bytes = []
                if images:
                    # images is list of base64 strings already sized
                    import base64
                    for b64 in images:
                        try:
                            imgs_bytes.append(base64.b64decode(b64))
                        except Exception: pass
                raw = self.provider.chat(messages, images=imgs_bytes, max_tokens=800)
                cleaned = raw.replace("```json", "").replace("```", "").strip()
                m = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if m:
                    return json.loads(m.group(0))
                return {}
            except Exception as e:
                logger.warning(f"Unified provider extraction failed: {e}. Falling back LM Studio path.")

        if not self.is_connected: return {}

        # System Prompt: Contract Name kuralı güncellendi
        system_prompt = """Extract contract data as JSON. 
WARNING: Be precise. Do NOT hallucinate.

Field Rules:
1. doc_type: Must be exactly one of: {doc_types}. If unsure, pick closest.
2. company_type: Must be exactly one of: {company_types}.
3. contract_name: 
   - Look at the TOP of the FIRST PAGE. 
   - Extract the capitalized/bold TITLE (e.g. "MASTER SERVICES AGREEMENT").
   - Do NOT include the parties or date in the title (e.g. remove "Between X and Y").
   - If there is no clear title, infer it from the content (e.g. "NDA").
4. address: Find the FULL address of the Counterparty (NOT Telenity). 
   - Look at the FIRST PAGE header/preamble OR the LAST PAGE signature block.
   - If you see Telenity's address (Maslak, Istanbul, Dubai, Monroe), IGNORE IT.
5. country: Extract the country FROM THE COUNTERPARTY'S ADDRESS. 
   - Example: "Tallinn, Estonia" -> Country: "Estonia".
   - Do NOT default to Turkey unless the address is actually in Turkey.
6. signed_date: YYYY-MM-DD. Look for handwritten dates.
7. found_telenity_name: Exact Telenity entity name.
8. confidence_score: Rate your confidence 0-100 (Integer).

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
  "found_telenity_name": "String",
  "confidence_score": 0
}}
"""
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
{{"contract_name":"","doc_type":"","text_signature_status":"","company_type":"","signing_party":"","country":"","address":"","signed_date":"","found_telenity_name":"","confidence_score":0}}"""
        
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
        for attempt in range(2): 
            try:
                resp = requests.post(self.api_url, json=payload, timeout=90)
                if resp.status_code == 200:
                    result = resp.json()
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        content = content.replace("```json", "").replace("```", "").strip()
                        match = re.search(r"\{.*\}", content, re.DOTALL)
                        if match: return json.loads(match.group(0))
                last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                logger.warning(f"LLM attempt {attempt+1} failed: {last_error}")
            except Exception as e:
                last_error = str(e)
                # Timeout hatalarını özel logla
                if "Read timed out" in last_error or "timeout" in last_error.lower():
                    logger.warning(f"⏱️ LLM attempt {attempt+1} timeout (90s) - LM Studio may be overloaded or model is slow")
                else:
                    logger.warning(f"LLM attempt {attempt+1} exception: {e}")
                time.sleep(1)

        if images:
            logger.error(f"Vision request FAILED. Reason: {last_error}")
            logger.info("Retrying with TEXT ONLY mode...")
            return self.get_analysis(text, filename=filename, images=None, filename_date=filename_date)

        return {}

    def verify_extraction(self, current_data, text, filename):
        """AI Auditor: Metin tabanlı ikinci kontrol."""
        if not self.is_connected: return current_data

        max_chars = 6000
        if len(text) > max_chars:
            half = max_chars // 2
            processed_text = text[:half] + "\n...[END]...\n" + text[-half:]
        else:
            processed_text = text

        prompt = f"""You are a strict Quality Assurance Auditor.
Your job is to verify the extracted data against the source text and filename.

SOURCE FILENAME: {filename}
SOURCE TEXT (Snippet):
{processed_text}

CURRENT EXTRACTED DATA:
{json.dumps(current_data, indent=2)}

INSTRUCTIONS:
1. Check 'signing_party': Is it consistent with the filename?
2. Check 'country': Does the 'address' actually belong to this country?
3. Check 'signed_date': Is the filename date more accurate?
4. Check 'contract_name': Extract the actual title from the text if the current one is generic (e.g. "Agreement").

OUTPUT:
Return the CORRECTED JSON object. If no changes needed, return the same JSON.
"""
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": False,
        }

        try:
            start_t = time.time()
            resp = requests.post(self.api_url, json=payload, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    content = content.replace("```json", "").replace("```", "").strip()
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        logger.info(f"🤖 AI Verification completed in {time.time()-start_t:.1f}s")
                        return json.loads(match.group(0))
        except Exception as e:
            logger.warning(f"AI Verification failed: {e}")
        
        return current_data

    def detect_telenity_visual(self, image_b64):
        if not self.is_connected: return None
        prompt = "Look at this document. Identify Telenity Company Name. Return ONLY the name."
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt},{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}],
            "temperature": 0.1, "stream": False
        }
        try:
            resp = requests.post(self.api_url, json=payload, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"].strip()
                    if "FZE" in content or "Dubai" in content: return "FzE - Telenity UAE", "Telenity FZE"
                    elif "Inc" in content or "Monroe" in content: return "TU - Telenity USA", "Telenity Inc"
                    elif "İletişim" in content or "Turkey" in content: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
                    elif "India" in content: return "TI - Telenity India", "Telenity Systems Software India Private Limited"
        except Exception as e: logger.error(f"Vision detection failed: {e}")
        return None
