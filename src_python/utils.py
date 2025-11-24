# src_python/utils.py
import re
import unicodedata
from thefuzz import process, fuzz
from config import TELENITY_MAP, ADDRESS_BLACKLIST, DOC_TYPE_CHOICES

def asciify_text(text):
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def extract_company_from_filename(filename):
    """Dosya isminden Şirket Adını tahmin eder."""
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    name = re.sub(r'\([^)]*\)', '', name) # Parantez içlerini sil
    parts = re.split(r'[-_,]', name)
    
    ignore_list = set(x.lower() for x in DOC_TYPE_CHOICES)
    ignore_list.update([
        "signed", "clean", "copy", "final", "draft", "contract", "agreement", 
        "telenity", "v1", "v2", "rev", "eng", "tr", "tur", "executed", "scan", "mutual"
    ])
    
    potential_names = []
    for part in parts:
        clean_part = part.strip()
        lower_part = clean_part.lower()
        
        if not clean_part: continue
        if re.search(r'\d{4}', clean_part): continue # İçinde yıl varsa şirket değildir
        if lower_part in ignore_list: continue
        if any(ign in lower_part for ign in ["signed", "draft", "copy", "version"]): continue
        if "telenity" in lower_part: continue
        if len(clean_part) < 2: continue
        
        potential_names.append(clean_part)
        
    if potential_names: return potential_names[0] 
    return None

def extract_contract_name_from_filename(filename):
    """
    YENİ: Dosya isminden 'Sözleşme Adı'nı (NDA, Service Agreement vb.) çeker.
    Mantık: Tarihleri ve Şirket isimlerini at, geriye kalan anlamlı parça Sözleşme Adıdır.
    """
    if not filename: return "Agreement" # Fallback
    
    name = filename.rsplit('.', 1)[0]
    # Yaygın ayraçları boşluğa çevir
    name_clean = re.sub(r'[-_,]', ' ', name)
    
    # 1. Tarihleri Sil (YYYY, Month DD vb.)
    name_clean = re.sub(r'\d{4}', '', name_clean) # Yılı sil
    name_clean = re.sub(r'\d{1,2}', '', name_clean) # Gün/Ay rakamlarını sil
    
    # Ay isimlerini sil
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
              "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
              "ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik"]
    for m in months:
        name_clean = re.sub(r'\b' + m + r'\b', '', name_clean, flags=re.IGNORECASE)

    # 2. Gereksiz Kelimeleri Sil
    stopwords = ["signed", "clean", "copy", "final", "draft", "v1", "v2", "rev", "scan", "executed", "telenity", "fze", "inc", "ltd", "pvt", "corp"]
    for sw in stopwords:
        name_clean = re.sub(r'\b' + sw + r'\b', '', name_clean, flags=re.IGNORECASE)

    # 3. Kalanı Temizle
    # Birden fazla boşluğu teke indir
    final_name = re.sub(r'\s+', ' ', name_clean).strip()
    
    if len(final_name) < 3:
        return "Agreement" # Çok kısa kaldıysa varsayılan dön
        
    return final_name.title()

def extract_date_from_filename(filename):
    """
    GÜÇLENDİRİLMİŞ: Dosya isminden tarihi ne pahasına olursa olsun çeker.
    """
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    
    # 1. Adım: Ay İsimlerindeki Yazım Hatalarını Düzelt (Juna -> June)
    name = _correct_month_typos_in_string(name)

    # Regex 1: YYYY-MM-DD (Klasik)
    match = re.search(r'(\d{4})[-_.\s]+(\d{1,2})[-_.\s]+(\d{1,2})', name)
    if match: return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # Regex 2: DD-MM-YYYY
    match = re.search(r'(\d{1,2})[-_.\s]+(\d{1,2})[-_.\s]+(\d{4})', name)
    if match: return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"

    # Regex 3: YYYY...Month...Day (Esnek Arama)
    # Arada ne olursa olsun Yıl, Ay, Gün sırasını arar
    # Örn: 2025_SomeText_February_24
    match = re.search(r'(\d{4}).*?([a-zA-Z]+).*?(\d{1,2})', name, re.IGNORECASE)
    if match:
        date_str = _parse_month_date(match.group(3), match.group(2), match.group(1))
        if date_str: return date_str

    # Regex 4: Day...Month...Year
    match = re.search(r'(\d{1,2}).*?([a-zA-Z]+).*?(\d{4})', name, re.IGNORECASE)
    if match:
        date_str = _parse_month_date(match.group(1), match.group(2), match.group(3))
        if date_str: return date_str

    return None

def _correct_month_typos_in_string(text):
    corrections = {
        "juna": "june", "july": "july", "jul": "july",
        "agust": "august", "aug": "august",
        "sept": "september", "sep": "september",
        "oct": "october", "nov": "november", "dec": "december",
        "ocak": "january", "subat": "february", "nisan": "april", 
        "haziran": "june", "temmuz": "july", "agustos": "august", 
        "eylul": "september", "ekim": "october", "kasim": "november", "aralik": "december"
    }
    text_lower = text.lower()
    for wrong, right in corrections.items():
        if wrong in text_lower:
            # Kelimeyi orjinal text içinde bulup değiştir (case insensitive replace zordur, basit replace yapıyoruz)
            text = re.sub(wrong, right, text, flags=re.IGNORECASE)
    return text

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
    if not address: return None
    addr_lower = address.lower()
    mapping = {
        "estonia": "Estonia", "tallinn": "Estonia", "tartu": "Estonia",
        "myanmar": "Myanmar", "yangon": "Myanmar", "burma": "Myanmar",
        "uk": "United Kingdom", "london": "United Kingdom", "england": "United Kingdom",
        "germany": "Germany", "berlin": "Germany", "munich": "Germany", "gmbh": "Germany",
        "france": "France", "paris": "France", "cedex": "France",
        "uae": "UAE", "dubai": "UAE", "abu dhabi": "UAE",
        "singapore": "Singapore", "sg ": "Singapore", " sg": "Singapore",
        "turkey": "Turkey", "istanbul": "Turkey", "ankara": "Turkey", "maslak": "Turkey",
        "usa": "USA", "ny": "USA", "ca": "USA", "inc.": "USA",
        "malaysia": "Malaysia", "kuala lumpur": "Malaysia",
        "nigeria": "Nigeria", "lagos": "Nigeria", "abuja": "Nigeria",
        "india": "India", "noida": "India", "delhi": "India"
    }
    for key, country in mapping.items():
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
    return country_name.title()

def find_best_company_match(query, company_db, threshold=80):
    if not query or not company_db: return None
    choices = list(company_db.keys())
    best_match = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    if best_match:
        matched_name, score = best_match
        if score >= threshold: return company_db[matched_name]
    return None
