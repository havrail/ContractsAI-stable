# src_python/config.py
# Central configuration for paths, database, and lookup data.
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# 1. TEMEL AYARLAR VE PATH TANIMLARI
# ---------------------------------------------------
SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Dosya Yolları
SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", str(ROOT_DIR / "settings.json")))
TELENITY_MAP_PATH = Path(os.getenv("TELENITY_MAP_PATH", str(ROOT_DIR / "telenity_map.json")))
ADDRESS_BLACKLIST_PATH = Path(os.getenv("ADDRESS_BLACKLIST_PATH", str(ROOT_DIR / "address_blacklist.json")))

# 2. YARDIMCI FONKSİYONLAR (Önce Tanımlanmalı!)
# ---------------------------------------------------
def load_json_config(path, default=None):
    if default is None:
        default = {}
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading config from {path}: {e}")
    return default

# 3. KONFİGÜRASYONLARI YÜKLE
# ---------------------------------------------------

# Settings.json yükle
DEFAULT_SETTINGS = {
    "TESSERACT_CMD": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "POPPLER_PATH": r"C:\Program Files\poppler-25.11.0\Library\bin",
    "LM_STUDIO_IP": "http://localhost:1234",
    "MAX_WORKERS": 2,
    "USE_VISION_MODEL": False
}
settings = load_json_config(SETTINGS_PATH, DEFAULT_SETTINGS)

# Telenity Map yükle
TELENITY_MAP = load_json_config(TELENITY_MAP_PATH, {})
if not TELENITY_MAP:
    TELENITY_MAP = {
        "FZE": {"code": "FzE - Telenity UAE", "full": "Telenity FZE"}
    }

# Address Blacklist yükle (Utils.py için gerekli)
DEFAULT_BLACKLIST = [
    "maslak", "büyükdere", "sarıyer", "telenity", "noida", "monroe", "dubai"
]
ADDRESS_BLACKLIST = load_json_config(ADDRESS_BLACKLIST_PATH, DEFAULT_BLACKLIST)

# 4. VERİTABANI AYARLARI (PostgreSQL Öncelikli)
# ---------------------------------------------------
# Öncelik: .env dosyasındaki DATABASE_URL (Docker/PostgreSQL için)
# Fallback: Eğer yoksa yerel SQLite dosyasını kullan.
sqlite_path = str(DATA_DIR / "contracts_ai.db").replace("\\", "/")
DEFAULT_DB_URL = f"sqlite:///{sqlite_path}"

# SQLAlchemy'nin kullanacağı nihai URL
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

# Geri uyumluluk için (Eski kodlar DB_NAME kullanıyorsa)
DB_NAME = DATABASE_URL 

# 5. ENVIRONMENT VE ARAÇ AYARLARI
# ---------------------------------------------------
# Environment variables take priority over JSON settings
TESSERACT_CMD = os.getenv("TESSERACT_CMD", settings.get("TESSERACT_CMD", DEFAULT_SETTINGS["TESSERACT_CMD"]))
POPPLER_PATH = os.getenv("POPPLER_PATH", settings.get("POPPLER_PATH", DEFAULT_SETTINGS["POPPLER_PATH"]))
LM_STUDIO_IP = os.getenv("LM_STUDIO_IP", settings.get("LM_STUDIO_IP", DEFAULT_SETTINGS["LM_STUDIO_IP"]))

# Processing Configuration
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '8'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '20'))
USE_VISION_MODEL = os.getenv('USE_VISION_MODEL', 'false').lower() == 'true'

# OCR Configuration
DPI = 200

# API Security
API_KEY = os.getenv("API_KEY", "")

# 6. SEÇİM LİSTELERİ (CONSTANTS)
# ---------------------------------------------------
DOC_TYPE_CHOICES = [
    "Acceptance",
    "Agency Agreement",
    "Agency Agreement for Revenue Share",
    "Commercial Proposal",
    "Consultancy Agreement",
    "Data Processing Agreement",
    "Employee Contracts",
    "EULA - End User License Agreement",
    "Managed Services Agreement",
    "NDA",
    "Other",
    "PO",
    "Reseller Agreement",
    "Revenue Share Managed Services Agreement",
    "S&M Agreement",
    "Service Agent Agreement",
    "Service Partner Agreement",
    "Teaming Agreement",
]

SIGNATURE_CHOICES = [
    "Telenity Signed",
    "Counterparty Signed",
    "Fully Signed",
]

COMPANY_CHOICES = [
    "Customer",
    "Partner",
    "Consultant",
    "Other",
]
