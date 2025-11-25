"""Prompt Templates & Few-Shot Examples for Contract Extraction (No Fine-Tune Path)

Bu modül; Qwen / Llama modelleri ile sadece prompt engineering yoluyla
doğruluğu artırmak için mesaj oluşturma yardımcılarını içerir.

Akış:
  build_contract_extraction_messages(text, filename, images, quality_report, adaptive_hint)
    -> provider.chat(...)

Few-shot örnekleri mümkün olduğunca kısa tutulur (token verimliliği).
Adaptive hint feedback_service üzerinden sık yapılan hatalara göre eklenebilir.
"""

from typing import List, Dict, Optional
import json
import re

# Minimal high-quality few-shot examples (TR + EN karışık)
FEW_SHOT_EXAMPLES = [
    {
        "input": "FILE: msa_abc_2023-06-15.pdf\nCONTRACT_TEXT: This MASTER SERVICES AGREEMENT (\"Agreement\") is made on 15 June 2023 between Telenity and ABC Mobile OÜ located at Peterburi tee 71-348, 11415 Tallinn, Estonia.",
        "output": {
            "contract_name": "Master Services Agreement",
            "signing_party": "ABC Mobile OÜ",
            "address": "Peterburi tee 71-348, 11415 Tallinn, Estonia",
            "country": "Estonia",
            "signed_date": "2023-06-15",
            "both_signed": True
        }
    },
    {
        "input": "FILE: nda_xyz_2024-01-10.pdf\nCONTRACT_TEXT: BU GİZLİLİK SÖZLEŞMESİ (NDA) 10 Ocak 2024 tarihinde Telenity Europe ve XYZ Teknoloji Ltd. arasında imzalanmıştır. XYZ Teknoloji Ltd. adresi: Büyükdere Cad. No: 123 Maslak Sarıyer İstanbul Türkiye.",
        "output": {
            "contract_name": "Non-Disclosure Agreement",
            "signing_party": "XYZ Teknoloji Ltd.",
            "address": "Büyükdere Cad. No: 123 Maslak, Sarıyer, İstanbul, Türkiye",
            "country": "Turkey",
            "signed_date": "2024-01-10",
            "both_signed": True
        }
    }
]

SYSTEM_INSTRUCTIONS = """You extract structured JSON from contract documents.
Rules:
1. signing_party: Only the counterparty (not Telenity). Remove 'Telenity' parts.
2. address: Full postal address of counterparty (street, city, country). If Telenity address appears (Maslak, Dubai, Monroe, Noida) exclude it.
3. country: Derive from the address; do not hallucinate.
4. signed_date: Prefer explicit date patterns (YYYY-MM-DD, DD Month YYYY). If multiple, choose the execution/date of signature block.
5. contract_name: Concise formal title (e.g. 'Master Services Agreement', 'Non-Disclosure Agreement', 'Reseller Agreement'). Strip parties and dates.
6. both_signed: true if signature indicators for both parties appear (two distinct signature blocks or 'Signed by both parties').
7. Return ONLY JSON. No commentary.
Output JSON schema:
{
  "contract_name": "String",
  "signing_party": "String",
  "address": "String",
  "country": "String",
  "signed_date": "YYYY-MM-DD",
  "both_signed": true
}
If unsure for a field leave empty string or false.
"""

OUTPUT_SKELETON = {"contract_name": "", "signing_party": "", "address": "", "country": "", "signed_date": "", "both_signed": False}


def _truncate_text(text: str, max_chars: int = 14000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[- max_chars // 2:]
    return head + "\n...[TRUNCATED]...\n" + tail


def build_few_shot_block() -> str:
    lines = []
    for ex in FEW_SHOT_EXAMPLES:
        lines.append("### Example Input\n" + ex["input"])
        lines.append("### Example Output\n" + json.dumps(ex["output"], ensure_ascii=False))
    return "\n\n".join(lines)


def build_user_prompt(filename: str, raw_text: str) -> str:
    truncated = _truncate_text(raw_text)
    return f"FILE: {filename}\nCONTRACT_TEXT:\n{truncated}\n\nReturn JSON only: {json.dumps(OUTPUT_SKELETON)}"


def build_contract_extraction_messages(
    text: str,
    filename: str,
    images_b64: Optional[List[str]] = None,
    quality_report: Optional[object] = None,
    adaptive_hint: Optional[str] = None
) -> List[Dict]:
    few_shot = build_few_shot_block()
    dynamic_quality_note = ""
    if quality_report:
        if getattr(quality_report, "is_scanned", False):
            dynamic_quality_note = "Document seems scanned; rely more on visual layout for addresses and signatures."
        elif getattr(quality_report, "score", 100) < 70:
            dynamic_quality_note = "Low quality: double-check extracted address and date."

    hint_block = adaptive_hint or ""

    system_total = SYSTEM_INSTRUCTIONS + "\n" + dynamic_quality_note + ("\n" + hint_block if hint_block else "")
    user_prompt = few_shot + "\n\n### Task\n" + build_user_prompt(filename, text)

    messages: List[Dict] = [
        {"role": "system", "content": [{"type": "text", "text": system_total}]},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}]}
    ]

    if images_b64:
        # Add only first 4 images to save tokens
        for b64 in images_b64[:4]:
            messages.append({
                "role": "user",
                "content": [{
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }]
            })
    return messages


def parse_json_response(raw: str) -> Dict:
    raw = raw.strip()
    raw = raw.replace("```json", "").replace("```", "")
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def generate_adaptive_hints(feedback_service=None) -> str:
    """
    Generate adaptive hints from feedback service based on common mistakes.
    Bu fonksiyon, sık yapılan hataları analiz ederek prompt'a eklenecek ipuçları üretir.
    
    Args:
        feedback_service: FeedbackService instance (optional)
    
    Returns:
        String of adaptive hints to add to system prompt
    """
    if not feedback_service:
        return ""
    
    try:
        # Get common mistakes from feedback
        from feedback_service import FeedbackService
        if not isinstance(feedback_service, FeedbackService):
            return ""
        
        mistakes = feedback_service.get_common_mistakes(limit=5)
        if not mistakes:
            return ""
        
        hints = []
        hints.append("COMMON MISTAKES TO AVOID:")
        
        for mistake in mistakes:
            field = mistake.get("field_name", "")
            count = mistake.get("mistake_count", 0)
            
            if field == "address":
                hints.append(f"- Address field: {count} corrections made. Double-check that you exclude Telenity addresses (Maslak, Dubai, Monroe, Noida).")
            elif field == "country":
                hints.append(f"- Country field: {count} corrections made. Ensure country matches the address location.")
            elif field == "signing_party":
                hints.append(f"- Signing party: {count} corrections made. Verify you extract only the counterparty name, not Telenity.")
            elif field == "signed_date":
                hints.append(f"- Signed date: {count} corrections made. Look for date near signature blocks, format as YYYY-MM-DD.")
            else:
                hints.append(f"- {field}: {count} corrections made. Review this field carefully.")
        
        return "\n".join(hints)
    
    except Exception as e:
        # Fail silently, don't break extraction
        return ""

