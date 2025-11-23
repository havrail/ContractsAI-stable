from config import TELENITY_MAP
import re
from datetime import datetime

def extract_date_from_filename(filename):
    """
    Extracts date from filename using extended patterns including dots and spaces.
    Returns date in YYYY-MM-DD format or None.
    """
    if not filename:
        return None
    
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    
    # Common separators: dot, dash, underscore, space
    # Regex explanations:
    # \d{4} : Year
    # \d{1,2}: Day or Month
    # [-_.\s]: Separator (dash, underscore, dot, space)
    
    # Pattern 1: YYYY-MM-DD (e.g., 2025.08.11, 2025-08-11, 2025 08 11)
    match = re.search(r'(\d{4})[-_.\s](\d{1,2})[-_.\s](\d{1,2})', name)
    if match:
        try:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except:
            pass
    
    # Pattern 2: DD-MM-YYYY (e.g., 11.08.2025, 11-08-2025, 11 08 2025)
    match = re.search(r'(\d{1,2})[-_.\s](\d{1,2})[-_.\s](\d{4})', name)
    if match:
        try:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except:
            pass
    
    # Pattern 3: Text Month (e.g., 11August2025, 11 Aug 2025)
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5,
        'haziran': 6, 'temmuz': 7, 'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9,
        'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12
    }
    
    # Updated regex to be more permissive with separators
    match = re.search(r'(\d{1,2})[-_.\s]?([a-zA-ZğüşıöçĞÜŞİÖÇ]+)[-_.\s]?(\d{4})', name, re.IGNORECASE)
    if match:
        try:
            day, month_str, year = match.groups()
            month_num = months.get(month_str.lower())
            if month_num:
                return f"{year}-{month_num:02d}-{int(day):02d}"
        except:
            pass
    
    return None

# (Geri kalan fonksiyonlar - clean_turkish_chars, filter_telenity_address vs. aynı kalabilir)
def clean_turkish_chars(text):
    if not text: return text
    replacements = {'Ý': 'İ', 'Þ': 'Ş', 'Ð': 'Ğ', 'ý': 'ı', 'þ': 'ş', 'ð': 'ğ', 'Ã§': 'ç', 'Ã¼': 'ü', 'Ã¶': 'ö', 'Ä±': 'ı', 'Ä°': 'İ', 'Åž': 'Ş', 'Ä': 'Ğ'}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def filter_telenity_address(address):
    # (Mevcut kodunuzdakiyle aynı bırakın)
    if not address: return ""
    telenity_keywords = ["maslak", "büyükdere", "sarıyer", "yeşilköy", "bakırköy", "telenity", "c blok", "mindmill", "noida", "film city", "sector-16a", "monroe", "755 main street", "building 7", "dubai", "sheikh rashid tower", "world trade center", "floor no. 26", "premises - 26.24.2"]
    address_lower = address.lower()
    for keyword in telenity_keywords:
        if keyword in address_lower: return ""
    return address

def determine_telenity_entity(text):
    # (Mevcut kodunuzdakiyle aynı bırakın)
    if not isinstance(text, str): text = "" if text is None else str(text)
    upper_text = text.upper()
    for keyword, values in TELENITY_MAP.items():
        if keyword.upper() in upper_text: return values["code"], values["full"]
    normalized_text = re.sub(r'[^A-Z0-9]', '', upper_text)
    for keyword, values in TELENITY_MAP.items():
        normalized_keyword = re.sub(r'[^A-Z0-9]', '', keyword.upper())
        if normalized_keyword in normalized_text: return values["code"], values["full"]
    if "DUBAI" in upper_text or "UAE" in upper_text or "ARAB" in upper_text: return "FzE - Telenity UAE", "Telenity FZE"
    if "INDIA" in upper_text or "PRIVATE LIMITED" in upper_text: return "TI - Telenity India", "Telenity Systems Software India Private Limited"
    if "USA" in upper_text or "INC" in upper_text or "MONROE" in upper_text: return "TU - Telenity USA", "Telenity Inc"
    if "TURKEY" in upper_text or "TÜRKİYE" in upper_text or "ISTANBUL" in upper_text or "İSTANBUL" in upper_text: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
    if "SHEIKH RASHID" in upper_text or "WORLD TRADE" in upper_text: return "FzE - Telenity UAE", "Telenity FZE"
    if "NOIDA" in upper_text or "MINDMILL" in upper_text: return "TI - Telenity India", "Telenity Systems Software India Private Limited"
    if "MONROE" in upper_text or "MAIN STREET" in upper_text: return "TU - Telenity USA", "Telenity Inc"
    if "MASLAK" in upper_text or "SARIYER" in upper_text: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
    if "TELENITY" in upper_text: return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
    return "Bilinmiyor", "Telenity (Belirlenemedi)"
