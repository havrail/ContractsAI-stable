import re
import unicodedata
from thefuzz import process, fuzz # <--- YENİ KÜTÜPHANE
from config import TELENITY_MAP, ADDRESS_BLACKLIST, DOC_TYPE_CHOICES

def asciify_text(text):
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def extract_company_from_filename(filename):
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    parts = re.split(r'[-_]', name)
    
    ignore_list = set(x.lower() for x in DOC_TYPE_CHOICES)
    ignore_list.update([
        "signed", "clean", "copy", "final", "draft", "contract", "agreement", 
        "telenity", "v1", "v2", "rev", "eng", "tr", "tur", "executed", "scan"
    ])
    
    potential_names = []
    for part in parts:
        clean_part = part.strip()
        lower_part = clean_part.lower()
        if not clean_part: continue
        if re.search(r'\d{4}', clean_part): continue 
        if lower_part in ignore_list: continue
        if any(ign in lower_part for ign in ["signed", "draft", "copy", "version"]): continue
        if "telenity" in lower_part: continue
        if len(clean_part) < 3: continue
        potential_names.append(clean_part)
        
    if potential_names: return potential_names[0] 
    return None

def extract_date_from_filename(filename):
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    
    match = re.search(r'(\d{4})[-_.\s]+(\d{1,2})[-_.\s]+(\d{1,2})', name)
    if match: return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    match = re.search(r'(\d{1,2})[-_.\s]+(\d{1,2})[-_.\s]+(\d{4})', name)
    if match: return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"

    match = re.search(r'(\d{4})[-_.,\s]+([a-zA-Z]+)[-_.,\s]*(\d{1,2})', name, re.IGNORECASE)
    if match: return _parse_month_date(match.group(3), match.group(2), match.group(1))

    match = re.search(r'(\d{1,2})[-_.\s]+([a-zA-Z]+)[-_.\s]+(\d{4})', name, re.IGNORECASE)
    if match: return _parse_month_date(match.group(1), match.group(2), match.group(3))

    return None

def _parse_month_date(day, month_str, year):
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'ocak': 1, 'subat': 2, 'şubat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5,
        'haziran': 6, 'temmuz': 7, 'agustos': 8, 'ağustos': 8, 'eylul': 9, 'eylül': 9,
        'ekim': 10, 'kasim': 11, 'kasım': 11, 'aralik': 12, 'aralık': 12
    }
    month_key = month_str.lower()[:3]
    for k, v in months.items():
        if month_str.lower().startswith(k):
            return f"{year}-{v:02d}-{int(day):02d}"
    return None

def clean_turkish_chars(text):
    if not text: return text
    replacements = {'Ý': 'İ', 'Þ': 'Ş', 'Ð': 'Ğ', 'ý': 'ı', 'þ': 'ş', 'ð': 'ğ', 'Ã§': 'ç', 'Ã¼': 'ü', 'Ã¶': 'ö', 'Ä±': 'ı', 'Ä°': 'İ', 'Åž': 'Ş', 'Ä': 'Ğ'}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def filter_telenity_address(address):
    if not address: return ""
    address_ascii = asciify_text(address.lower())
    for keyword in ADDRESS_BLACKLIST:
        keyword_ascii = asciify_text(keyword.lower())
        if keyword_ascii in address_ascii: return "" 
    splitters = [';', ' and ', ' & ', ' vs ']
    for splitter in splitters:
        if splitter in address:
            parts = address.split(splitter)
            valid_parts = []
            for part in parts:
                if not any(asciify_text(kw.lower()) in asciify_text(part.lower()) for kw in ADDRESS_BLACKLIST):
                    valid_parts.append(part.strip())
            if valid_parts: return ", ".join(valid_parts)
    return address

def determine_telenity_entity(text):
    if not isinstance(text, str): text = "" if text is None else str(text)
    upper_text = text.upper()
    for keyword, values in TELENITY_MAP.items():
        if keyword.upper() in upper_text: return values["code"], values["full"]
    normalized_text = re.sub(r'[^A-Z0-9]', '', upper_text)
    for keyword, values in TELENITY_MAP.items():
        normalized_keyword = re.sub(r'[^A-Z0-9]', '', keyword.upper())
        if normalized_keyword in normalized_text: return values["code"], values["full"]
    if "TURKEY" in upper_text or "ISTANBUL" in upper_text: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
    return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş." 

def normalize_country(country_name):
    if not country_name: return ""
    name = country_name.lower().strip().replace(".", "")
    mapping = {
        "turkey": "Turkey", "türkiye": "Turkey", "turkiye": "Turkey", "tr": "Turkey",
        "usa": "USA", "united states": "USA", "united states of america": "USA", "us": "USA",
        "uk": "United Kingdom", "united kingdom": "United Kingdom", "great britain": "United Kingdom", "england": "United Kingdom",
        "uae": "UAE", "united arab emirates": "UAE", "dubai": "UAE",
        "nl": "Netherlands", "holland": "Netherlands", "netherlands": "Netherlands",
        "de": "Germany", "germany": "Germany", "deutschland": "Germany"
    }
    if name in mapping: return mapping[name]
    for key, val in mapping.items():
        if key in name: return val
    return country_name.title()

# --- THEFUZZ GÜNCELLEMESİ ---
def find_best_company_match(query, company_db, threshold=80):
    """
    TheFuzz kütüphanesi ile en iyi eşleşmeyi bulur.
    'G00gle' -> 'Google' eşleşmesini %90 skorla yakalar.
    """
    if not query or not company_db: return None
    
    # Company DB'deki anahtarları (Şirket isimlerini) listele
    choices = list(company_db.keys())
    
    # process.extractOne en iyi eşleşmeyi ve skoru döndürür
    # Örn: ('Vodafone', 95)
    best_match = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    
    if best_match:
        matched_name, score = best_match
        if score >= threshold:
            return company_db[matched_name]
            
    return None
