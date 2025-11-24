import re
import unicodedata
from difflib import SequenceMatcher # <--- YENİ: Fuzzy Matching için
from config import TELENITY_MAP, ADDRESS_BLACKLIST

def asciify_text(text):
    """Türkçe ve özel karakterleri ASCII'ye çevirir (Örn: Yeşilköy -> Yesilkoy)."""
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def extract_date_from_filename(filename):
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    
    # Temizlik
    clean_name = re.sub(r'(?i)(clean|copy|signed|final|draft|v\d+)', '', name)
    
    # 1. Klasik YYYY-MM-DD
    match = re.search(r'(\d{4})[-_.\s]+(\d{1,2})[-_.\s]+(\d{1,2})', name)
    if match: return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # 2. Klasik DD-MM-YYYY
    match = re.search(r'(\d{1,2})[-_.\s]+(\d{1,2})[-_.\s]+(\d{4})', name)
    if match: return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"

    # 3. YYYY, Month DD (Loglarda görülen format: 2025,February24)
    match = re.search(r'(\d{4})[-_.,\s]+([a-zA-Z]+)[-_.,\s]*(\d{1,2})', name, re.IGNORECASE)
    if match:
        return _parse_month_date(match.group(3), match.group(2), match.group(1))

    # 4. Text Month (DD Month YYYY)
    match = re.search(r'(\d{1,2})[-_.\s]+([a-zA-Z]+)[-_.\s]+(\d{4})', name, re.IGNORECASE)
    if match:
        return _parse_month_date(match.group(1), match.group(2), match.group(3))

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
        if keyword_ascii in address_ascii:
            return "" 
    
    splitters = [';', ' and ', ' & ', ' vs ']
    for splitter in splitters:
        if splitter in address:
            parts = address.split(splitter)
            valid_parts = []
            for part in parts:
                if not any(asciify_text(kw.lower()) in asciify_text(part.lower()) for kw in ADDRESS_BLACKLIST):
                    valid_parts.append(part.strip())
            if valid_parts:
                return ", ".join(valid_parts)

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

# --- YENİ EKLENEN FUZZY MATCHING FONKSİYONU ---
def find_best_company_match(query, company_db, threshold=80):
    """
    Verilen şirket ismini (query) hafızadaki (company_db) isimlerle kıyaslar.
    Benzerlik oranı %80 (threshold) üzerindeyse eşleşeni döndürür.
    """
    if not query: return None
    query_lower = query.lower()
    
    best_match = None
    highest_score = 0
    
    for key, data in company_db.items():
        key_lower = key.lower()
        
        # 1. Tam Eşleşme veya Kapsama (Kesin)
        if key_lower in query_lower or query_lower in key_lower:
            return data
            
        # 2. Fuzzy Benzerlik Hesabı
        # SequenceMatcher iki metin arasındaki benzerliği 0-100 arası puanlar
        score = SequenceMatcher(None, query_lower, key_lower).ratio() * 100
        
        if score > highest_score:
            highest_score = score
            best_match = data
            
    # Eşik değerini geçiyorsa döndür
    if highest_score >= threshold:
        return best_match
        
    return None
