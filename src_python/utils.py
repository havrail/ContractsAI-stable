import re
import unicodedata
from thefuzz import process, fuzz
from config import TELENITY_MAP, ADDRESS_BLACKLIST, DOC_TYPE_CHOICES

def asciify_text(text):
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# --- BAŞLIK TEMİZLEME (YENİ) ---
def clean_contract_name(text):
    """
    LLM'den gelen ham başlığı temizler.
    Örn: "SERVICE AGREEMENT dated 2023" -> "Service Agreement"
    """
    if not text: return ""
    text = str(text).strip()
    
    # Gereksiz Cümle Kalıplarını At
    patterns = [
        r'(?i)\s+between\s+.*', r'(?i)\s+entered\s+into.*',
        r'(?i)\s+dated\s+.*', r'(?i)\s+effective\s+.*',
        r'(?i)\s+by\s+and\s+between.*', r'(?i)\s+made\s+this.*'
    ]
    for pat in patterns:
        text = re.sub(pat, '', text).strip()
        
    text = text.strip('-_.,:;"\'')
    if len(text) > 100: return "" # Hatalı çekim
    return text.title()

def extract_contract_name_from_filename(filename):
    """Dosya isminden Sözleşme Adı tahmini (Yedek Plan)."""
    if not filename: return "Agreement"
    name = filename.rsplit('.', 1)[0]
    name_clean = re.sub(r'[-_,]', ' ', name)
    
    # Tarihleri Sil
    name_clean = re.sub(r'\d{4}', '', name_clean)
    name_clean = re.sub(r'\d{1,2}', '', name_clean)
    
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik"]
    for m in months:
        name_clean = re.sub(r'\b' + m + r'\b', '', name_clean, flags=re.IGNORECASE)

    stopwords = ["signed", "clean", "copy", "final", "draft", "v1", "v2", "rev", "scan", "executed", "telenity", "fze", "inc", "ltd", "pvt", "corp"]
    for sw in stopwords:
        name_clean = re.sub(r'\b' + sw + r'\b', '', name_clean, flags=re.IGNORECASE)

    final_name = re.sub(r'\s+', ' ', name_clean).strip()
    if len(final_name) < 3: return "Agreement"
    return final_name.title()

def extract_company_from_filename(filename):
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

def extract_date_from_filename(filename, aggressive=False):
    """
    Extract date from filename.
    
    Args:
        filename: File name to parse
        aggressive: If True, try harder with less strict patterns
    
    Returns:
        Date string in YYYY-MM-DD format or None
    """
    if not filename: return None
    name = filename.rsplit('.', 1)[0]
    name = _correct_month_typos_in_string(name) # Juna -> June düzeltmesi

    match = re.search(r'(\d{4})[-_.\s]+(\d{1,2})[-_.\s]+(\d{1,2})', name)
    if match: return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    match = re.search(r'(\d{1,2})[-_.\s]+(\d{1,2})[-_.\s]+(\d{4})', name)
    if match: return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"

    match = re.search(r'(\d{4}).*?([a-zA-Z]+).*?(\d{1,2})', name, re.IGNORECASE)
    if match:
        date_str = _parse_month_date(match.group(3), match.group(2), match.group(1))
        if date_str: return date_str

    match = re.search(r'(\d{1,2}).*?([a-zA-Z]+).*?(\d{4})', name, re.IGNORECASE)
    if match:
        date_str = _parse_month_date(match.group(1), match.group(2), match.group(3))
        if date_str: return date_str
    
    # Aggressive mode: Try to find any 4-digit year
    if aggressive:
        match = re.search(r'\b(20\d{2}|19\d{2})\b', name)
        if match:
            year = match.group(1)
            # Try to find month nearby
            month_match = re.search(r'([a-zA-Z]{3,})', name[max(0, match.start()-20):match.end()+20], re.IGNORECASE)
            if month_match:
                month_str = month_match.group(1).lower()
                months = {
                    "jan": "01", "january": "01", "ocak": "01",
                    "feb": "02", "february": "02", "subat": "02", "şubat": "02",
                    "mar": "03", "march": "03", "mart": "03",
                    "apr": "04", "april": "04", "nisan": "04",
                    "may": "05", "mayis": "05", "mayıs": "05",
                    "jun": "06", "june": "06", "haziran": "06",
                    "jul": "07", "july": "07", "temmuz": "07",
                    "aug": "08", "august": "08", "agustos": "08", "ağustos": "08",
                    "sep": "09", "september": "09", "eylul": "09", "eylül": "09",
                    "oct": "10", "october": "10", "ekim": "10",
                    "nov": "11", "november": "11", "kasim": "11", "kasım": "11",
                    "dec": "12", "december": "12", "aralik": "12", "aralık": "12"
                }
                for month_key, month_num in months.items():
                    if month_key in month_str:
                        return f"{year}-{month_num}-01"
            # Fallback: Just year with 01-01
            return f"{year}-01-01"

    return None

def _correct_month_typos_in_string(text):
    corrections = {
        "juna": "june", "july": "july", "jul": "july", "agust": "august", "aug": "august",
        "sept": "september", "sep": "september", "oct": "october", "nov": "november", "dec": "december",
        "ocak": "january", "subat": "february", "nisan": "april", "haziran": "june", 
        "temmuz": "july", "agustos": "august", "eylul": "september", "ekim": "october", 
        "kasim": "november", "aralik": "december"
    }
    text_lower = text.lower()
    for wrong, right in corrections.items():
        if wrong in text_lower:
            text = re.sub(wrong, right, text, flags=re.IGNORECASE)
    return text

def _parse_month_date(day, month_str, year):
    months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
    month_key = month_str.lower()[:3]
    for k, v in months.items():
        if month_key.startswith(k): return f"{year}-{v:02d}-{int(day):02d}"
    return None

def infer_country_from_address(address):
    if not address: return None
    addr_lower = address.lower()
    mapping = {
        "estonia": "Estonia", "tallinn": "Estonia", "tartu": "Estonia",
        "uk": "United Kingdom", "london": "United Kingdom", "england": "United Kingdom", "great britain": "United Kingdom",
        "germany": "Germany", "berlin": "Germany", "munich": "Germany", "gmbh": "Germany",
        "france": "France", "paris": "France", "cedex": "France",
        "netherlands": "Netherlands", "amsterdam": "Netherlands", "rotterdam": "Netherlands", "holland": "Netherlands",
        "spain": "Spain", "madrid": "Spain", "barcelona": "Spain",
        "italy": "Italy", "rome": "Italy", "milan": "Italy",
        "singapore": "Singapore", "sg ": "Singapore", " sg": "Singapore",
        "malaysia": "Malaysia", "kuala lumpur": "Malaysia",
        "india": "India", "noida": "India", "gurgaon": "India", "mumbai": "India", "delhi": "India",
        "myanmar": "Myanmar", "yangon": "Myanmar", "burma": "Myanmar",
        "china": "China", "beijing": "China", "shanghai": "China", "hong kong": "Hong Kong",
        "indonesia": "Indonesia", "jakarta": "Indonesia",
        "pakistan": "Pakistan", "islamabad": "Pakistan",
        "uae": "UAE", "dubai": "UAE", "abu dhabi": "UAE", "arab emirates": "UAE",
        "nigeria": "Nigeria", "lagos": "Nigeria", "abuja": "Nigeria",
        "egypt": "Egypt", "cairo": "Egypt",
        "saudi": "Saudi Arabia", "riyadh": "Saudi Arabia", "jeddah": "Saudi Arabia", "ksa": "Saudi Arabia",
        "usa": "USA", "united states": "USA", "new york": "USA", "ny ": "USA", "california": "USA", "inc.": "USA", "llc": "USA",
        "canada": "Canada", "toronto": "Canada", "vancouver": "Canada",
        "turkey": "Turkey", "türkiye": "Turkey", "istanbul": "Turkey", "ankara": "Turkey", "izmir": "Turkey", "maslak": "Turkey"
    }
    for key, country in mapping.items():
        if re.search(r'\b' + re.escape(key) + r'\b', addr_lower): return country
    return None

def clean_turkish_chars(text):
    if not text: return text
    replacements = {'Ý': 'İ', 'Þ': 'Ş', 'Ð': 'Ğ', 'ý': 'ı', 'þ': 'ş', 'ð': 'ğ', 'Ã§': 'ç', 'Ã¼': 'ü', 'Ã¶': 'ö', 'Ä±': 'ı', 'Ä°': 'İ', 'Åž': 'Ş', 'Ä': 'Ğ'}
    for old, new in replacements.items(): text = text.replace(old, new)
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
