import re
import unicodedata
from thefuzz import process, fuzz
from config import TELENITY_MAP, ADDRESS_BLACKLIST, DOC_TYPE_CHOICES

def asciify_text(text):
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def correct_month_typos(month_str):
    """Kullanıcıların dosya ismindeki yazım hatalarını düzeltir (Juna -> June)."""
    month_str = month_str.lower()
    corrections = {
        "juna": "june", "july": "july", "agust": "august", "sept": "september",
        "oct": "october", "nov": "november", "dec": "december",
        "ocak": "january", "subat": "february", "nisan": "april"
    }
    for wrong, right in corrections.items():
        if wrong in month_str: return right
    return month_str

def extract_date_from_filename(filename):
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    
    # Regex 1: YYYY-MM-DD
    match = re.search(r'(\d{4})[-_.\s]+(\d{1,2})[-_.\s]+(\d{1,2})', name)
    if match: return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # Regex 2: DD-MM-YYYY
    match = re.search(r'(\d{1,2})[-_.\s]+(\d{1,2})[-_.\s]+(\d{4})', name)
    if match: return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"

    # Regex 3: YYYY, MonthDD (Yazım hatalarını düzelterek)
    match = re.search(r'(\d{4})[-_.,\s]+([a-zA-Z]+)[-_.,\s]*(\d{1,2})', name, re.IGNORECASE)
    if match:
        month = correct_month_typos(match.group(2))
        return _parse_month_date(match.group(3), month, match.group(1))

    # Regex 4: DD Month YYYY
    match = re.search(r'(\d{1,2})[-_.,\s]+([a-zA-Z]+)[-_.,\s]+(\d{4})', name, re.IGNORECASE)
    if match:
        month = correct_month_typos(match.group(2))
        return _parse_month_date(match.group(1), month, match.group(3))

    return None

def _parse_month_date(day, month_str, year):
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    month_key = month_str.lower()[:3]
    for k, v in months.items():
        if month_key.startswith(k):
            return f"{year}-{v:02d}-{int(day):02d}"
    return None

def infer_country_from_address(address):
    """Adresten ülkeyi çıkarır (LLM hatasını düzeltmek için)."""
    if not address: return None
    addr_lower = address.lower()
    
    # Şehir/Ülke Anahtar Kelimeleri
    mapping = {
        "estonia": "Estonia", "tallinn": "Estonia", "tartu": "Estonia",
        "myanmar": "Myanmar", "yangon": "Myanmar", "burma": "Myanmar",
        "uk": "United Kingdom", "london": "United Kingdom", "england": "United Kingdom",
        "germany": "Germany", "berlin": "Germany", "munich": "Germany", "gmbh": "Germany",
        "france": "France", "paris": "France", "cedex": "France",
        "uae": "UAE", "dubai": "UAE", "abu dhabi": "UAE",
        "turkey": "Turkey", "istanbul": "Turkey", "ankara": "Turkey", "maslak": "Turkey",
        "usa": "USA", "ny": "USA", "ca": "USA", "inc.": "USA",
        "malaysia": "Malaysia", "kuala lumpur": "Malaysia"
    }
    
    for key, country in mapping.items():
        # Kelime sınırlarıyla arama yap (örn: 'UK' kelimesini 'Ukraine' içinde bulmasın)
        if re.search(r'\b' + re.escape(key) + r'\b', addr_lower):
            return country
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
        if asciify_text(keyword.lower()) in address_ascii: return "" 
    splitters = [';', ' and ', ' & ', ' vs ', '\n']
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
    return country_name.title() # Basitleştirdik, asıl işi infer_country_from_address yapacak

def extract_company_from_filename(filename):
    # (Eski kodunuzdakiyle aynı kalabilir)
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    name = re.sub(r'\([^)]*\)', '', name)
    parts = re.split(r'[-_,]', name)
    ignore_list = set(x.lower() for x in DOC_TYPE_CHOICES)
    ignore_list.update(["signed", "clean", "copy", "final", "draft", "contract", "agreement", "telenity", "v1", "v2", "rev", "eng", "tr", "tur", "executed", "scan", "mutual"])
    potential_names = []
    for part in parts:
        clean_part = part.strip()
        lower_part = clean_part.lower()
        if not clean_part or re.search(r'\d{4}', clean_part): continue 
        if lower_part in ignore_list or any(ign in lower_part for ign in ["signed", "draft", "copy", "version"]): continue
        if "telenity" in lower_part or len(clean_part) < 2: continue
        potential_names.append(clean_part)
    if potential_names: return potential_names[0] 
    return None

def find_best_company_match(query, company_db, threshold=80):
    if not query or not company_db: return None
    choices = list(company_db.keys())
    best_match = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    if best_match:
        matched_name, score = best_match
        if score >= threshold: return company_db[matched_name]
    return None
