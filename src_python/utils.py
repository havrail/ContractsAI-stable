import re
from config import TELENITY_MAP, ADDRESS_BLACKLIST

def extract_date_from_filename(filename):
    """
    Dosya adından tarih çıkarma (Geliştirilmiş Regex).
    Artık 20250224 veya 24022025 gibi bitişik formatları da tanır.
    """
    if not filename: return None
    
    # Uzantıyı at, temizle
    name = filename.rsplit('.', 1)[0]
    # Gereksiz karakterleri temizle (clean copy, signed vb.)
    clean_name = re.sub(r'(?i)(clean|copy|signed|final|draft|v\d+)', '', name)
    
    # Pattern 1: YYYY-MM-DD (Ayraçlı: -, _, ., boşluk)
    match = re.search(r'(\d{4})[-_.\s]+(\d{1,2})[-_.\s]+(\d{1,2})', name)
    if match:
        try:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except: pass
    
    # Pattern 2: DD-MM-YYYY (Ayraçlı)
    match = re.search(r'(\d{1,2})[-_.\s]+(\d{1,2})[-_.\s]+(\d{4})', name)
    if match:
        try:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except: pass

    # Pattern 3: Compact YYYYMMDD (Örn: 20250224) - Riskli olduğu için tarih kontrolü sıkı
    match = re.search(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', name)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    # Pattern 4: Compact DDMMYYYY (Örn: 24022025)
    match = re.search(r'(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(20\d{2})', name)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"

    # Pattern 5: Text Month (e.g., 11August2025)
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'ocak': 1, 'subat': 2, 'şubat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5,
        'haziran': 6, 'temmuz': 7, 'agustos': 8, 'ağustos': 8, 'eylul': 9, 'eylül': 9,
        'ekim': 10, 'kasim': 11, 'kasım': 11, 'aralik': 12, 'aralık': 12
    }
    
    # Regex: Sayı + (Ayraçsız/Ayraçlı) Ay İsmi + (Ayraçsız/Ayraçlı) Yıl
    match = re.search(r'(\d{1,2})[-_.\s]?([a-zA-ZğüşıöçĞÜŞİÖÇ]+)[-_.\s]?(\d{4})', name, re.IGNORECASE)
    if match:
        try:
            day, month_str, year = match.groups()
            # İlk 3 harfine bakarak eşleştirme (Jan, January, Janu...)
            month_key = month_str.lower()[:3]
            # Sözlükte tam eşleşme veya kısaltma ara
            month_num = None
            for k, v in months.items():
                if month_str.lower().startswith(k):
                    month_num = v
                    break
            
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
    if not address: return ""
    address_lower = address.lower()
    for keyword in ADDRESS_BLACKLIST:
        if keyword.lower() in address_lower:
            return ""
    return address

def determine_telenity_entity(text):
    if not isinstance(text, str): text = "" if text is None else str(text)
    upper_text = text.upper()
    
    # 1. Direkt Kelime Arama
    for keyword, values in TELENITY_MAP.items():
        if keyword.upper() in upper_text:
            return values["code"], values["full"]

    # 2. Normalize Arama
    normalized_text = re.sub(r'[^A-Z0-9]', '', upper_text)
    for keyword, values in TELENITY_MAP.items():
        normalized_keyword = re.sub(r'[^A-Z0-9]', '', keyword.upper())
        if normalized_keyword in normalized_text:
            return values["code"], values["full"]
    
    # 3. Akıllı Fallback (Hiçbir şey bulunamazsa varsayılanı boş bırakma)
    # Eğer "Istanbul" veya "Turkey" geçiyorsa Europe'a ata
    if "TURKEY" in upper_text or "ISTANBUL" in upper_text:
        return "TE - Telenity Europe", "Telenity İletişim Sistemleri Sanayi ve Ticaret A.Ş."
    
    # Hiçbir ipucu yoksa ama dosya işlendiyse, en yaygın olanı ata (Boş kalmasından iyidir)
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
