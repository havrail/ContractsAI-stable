import re
from datetime import datetime
# Config dosyasından harici listeleri çekiyoruz
from config import TELENITY_MAP, ADDRESS_BLACKLIST

def extract_date_from_filename(filename):
    """
    Extracts date from filename using extended patterns including dots and spaces.
    Returns date in YYYY-MM-DD format or None.
    """
    if not filename: return None
    
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    
    # Pattern 1: YYYY-MM-DD (e.g., 2025.08.11, 2025-08-11)
    match = re.search(r'(\d{4})[-_.\s](\d{1,2})[-_.\s](\d{1,2})', name)
    if match:
        try:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except: pass
    
    # Pattern 2: DD-MM-YYYY (e.g., 11.08.2025)
    match = re.search(r'(\d{1,2})[-_.\s](\d{1,2})[-_.\s](\d{4})', name)
    if match:
        try:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except: pass
    
    # Pattern 3: Text Month (e.g., 11August2025)
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5,
        'haziran': 6, 'temmuz': 7, 'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9,
        'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12
    }
    
    match = re.search(r'(\d{1,2})[-_.\s]?([a-zA-ZğüşıöçĞÜŞİÖÇ]+)[-_.\s]?(\d{4})', name, re.IGNORECASE)
    if match:
        try:
            day, month_str, year = match.groups()
            month_num = months.get(month_str.lower())
            if month_num:
                return f"{year}-{month_num:02d}-{int(day):02d}"
        except: pass
    
    return None

def clean_turkish_chars(text):
    if not text: return text
    replacements = {'Ý': 'İ', 'Þ': 'Ş', 'Ð': 'Ğ', 'ý': 'ı', 'þ': 'ş', 'ð': 'ğ', 'Ã§': 'ç', 'Ã¼': 'ü', 'Ã¶': 'ö', 'Ä±': 'ı', 'Ä°': 'İ', 'Åž': 'Ş', 'Ä': 'Ğ'}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def filter_telenity_address(address):
    """
    Adres içinde Telenity'e ait anahtar kelimeler varsa temizler.
    Keyword listesi config üzerinden JSON dosyasından gelir.
    """
    if not address: return ""
    
    address_lower = address.lower()
    
    # GÖMÜLÜ LİSTE YERİNE CONFIG KULLANIMI:
    # Böylece yeni bir yasaklı kelime eklemek için kodu değiştirmeyiz.
    for keyword in ADDRESS_BLACKLIST:
        if keyword.lower() in address_lower:
            return ""
    
    return address

def determine_telenity_entity(text):
    """
    Metin içindeki Telenity şirketini bulur.
    Mantık tamamen config/JSON dosyasına dayanır.
    """
    if not isinstance(text, str): text = "" if text is None else str(text)
    upper_text = text.upper()
    
    # 1. Direkt Kelime Arama (JSON'dan gelen harita)
    for keyword, values in TELENITY_MAP.items():
        if keyword.upper() in upper_text:
            return values["code"], values["full"]

    # 2. Normalize Edilmiş Arama (Boşluksuz/Noktalama işaretsiz)
    normalized_text = re.sub(r'[^A-Z0-9]', '', upper_text)
    for keyword, values in TELENITY_MAP.items():
        normalized_keyword = re.sub(r'[^A-Z0-9]', '', keyword.upper())
        if normalized_keyword in normalized_text:
            return values["code"], values["full"]
    
    # Fallback (Varsayılan)
    if "TELENITY" in upper_text:
        return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
        
    return "Bilinmiyor", "Telenity (Belirlenemedi)"

def normalize_country(country_name):
    """
    LLM'den gelen ülke isimlerini standartlaştırır (TR -> Turkey, UK -> United Kingdom vb).
    """
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
    
    if name in mapping:
        return mapping[name]
    
    for key, val in mapping.items():
        if key in name:
            return val
            
    return country_name.title()
