from config import TELENITY_MAP
import re
from datetime import datetime

def extract_date_from_filename(filename):
    """
    Extracts date from filename using various patterns.
    Returns date in YYYY-MM-DD format or None.
    """
    if not filename:
        return None
    
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    
    # Pattern 1: YYYY-MM-DD or YYYY_MM_DD
    match = re.search(r'(\d{4})[-_](\d{1,2})[-_](\d{1,2})', name)
    if match:
        try:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except:
            pass
    
    # Pattern 2: DD-MM-YYYY or DD_MM_YYYY
    match = re.search(r'(\d{1,2})[-_](\d{1,2})[-_](\d{4})', name)
    if match:
        try:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except:
            pass
    
    # Pattern 3: DDMonthYYYY or DD_Month_YYYY (e.g., 11August2025, 11_August_2025)
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    # Try with separators
    match = re.search(r'(\d{1,2})[-_\s]?([a-zA-Z]+)[-_\s]?(\d{4})', name, re.IGNORECASE)
    if match:
        try:
            day, month_str, year = match.groups()
            month_num = months.get(month_str.lower())
            if month_num:
                return f"{year}-{month_num:02d}-{int(day):02d}"
        except:
            pass
    
    return None

def clean_turkish_chars(text):
    """
    Fixes common OCR errors in Turkish text.
    """
    if not text:
        return text
    
    replacements = {
        'Ý': 'İ',
        'Þ': 'Ş',
        'Ð': 'Ğ',
        'ý': 'ı',
        'þ': 'ş',
        'ð': 'ğ',
        'Ã§': 'ç',
        'Ã¼': 'ü',
        'Ã¶': 'ö',
        'Ä±': 'ı',
        'Ä°': 'İ',
        'Åž': 'Ş',
        'Ä': 'Ğ',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text

def filter_telenity_address(address):
    """
    Filters out Telenity addresses. Returns empty string if address belongs to Telenity.
    """
    if not address:
        return ""
    
    # Comprehensive Telenity address blacklist
    telenity_keywords = [
        # Turkey specific Telenity locations
        "maslak", "büyükdere", "sarıyer", "yeşilköy", "bakırköy",
        # Explicit Telenity identifiers
        "telenity", "c blok",
        # India
        "mindmill", "noida", "film city", "sector-16a",
        # USA
        "monroe", "755 main street", "building 7",
        # UAE
        "dubai", "sheikh rashid tower", "world trade center",
        "floor no. 26", "premises - 26.24.2",
    ]
    
    address_lower = address.lower()
    
    # Check if any blacklist keyword exists in the address
    for keyword in telenity_keywords:
        if keyword in address_lower:
            return ""
    
    return address

def determine_telenity_entity(text):
    """
    Determines the Telenity entity code and full name based on the text.
    Uses normalized matching to handle OCR errors and variations.
    """
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    
    # Normalize input text: upper case
    upper_text = text.upper()
    
    # 1. Direct check against map keys (most accurate)
    for keyword, values in TELENITY_MAP.items():
        if keyword.upper() in upper_text:
            return values["code"], values["full"]

    # 2. Normalized check (remove spaces/punctuation) for robust matching
    # e.g. "Telenity F Z E" -> "TELENITYFZE"
    normalized_text = re.sub(r'[^A-Z0-9]', '', upper_text)
    
    for keyword, values in TELENITY_MAP.items():
        normalized_keyword = re.sub(r'[^A-Z0-9]', '', keyword.upper())
        if normalized_keyword in normalized_text:
            return values["code"], values["full"]
            
    # 3. Fallback logic based on region keywords if specific entity name not found
    if "DUBAI" in upper_text or "UAE" in upper_text or "ARAB" in upper_text:
         return "FzE - Telenity UAE", "Telenity FZE"
    if "INDIA" in upper_text or "PRIVATE LIMITED" in upper_text:
        return "TI - Telenity India", "Telenity Systems Software India Private Limited"
    if "USA" in upper_text or "INC" in upper_text or "MONROE" in upper_text:
        return "TU - Telenity USA", "Telenity Inc"
    if "TURKEY" in upper_text or "TÜRKİYE" in upper_text or "ISTANBUL" in upper_text or "İSTANBUL" in upper_text:
        return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."

    # 4. Address-based heuristic (Context-aware)
    # Even if the name is missing, the address is a strong indicator.
    if "SHEIKH RASHID" in upper_text or "WORLD TRADE" in upper_text or "DUBAI" in upper_text:
         return "FzE - Telenity UAE", "Telenity FZE"
    if "NOIDA" in upper_text or "MINDMILL" in upper_text or "SECTOR-16A" in upper_text:
        return "TI - Telenity India", "Telenity Systems Software India Private Limited"
    if "MONROE" in upper_text or "MAIN STREET" in upper_text or "CONNECTICUT" in upper_text or "06468" in upper_text:
        return "TU - Telenity USA", "Telenity Inc"
    if "MASLAK" in upper_text or "SARIYER" in upper_text or "BUYUKDERE" in upper_text or "BÜYÜKDERE" in upper_text:
        return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."

    # Default fallback
    if "TELENITY" in upper_text:
        return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
        
    return "Bilinmiyor", "Telenity (Belirlenemedi)"

