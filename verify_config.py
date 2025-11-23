import sys
import os

# Add the current directory to sys.path so we can import src
sys.path.append(os.getcwd())

try:
    from src import config
    print("Config imported successfully.")
    print(f"TESSERACT_CMD: {config.TESSERACT_CMD}")
    print(f"TELENITY_MAP keys count: {len(config.TELENITY_MAP)}")
    
    if config.TESSERACT_CMD == r"C:\Program Files\Tesseract-OCR\tesseract.exe":
        print("TESSERACT_CMD matches default/json.")
    else:
        print("TESSERACT_CMD mismatch.")
        
    if "FZE" in config.TELENITY_MAP:
        print("TELENITY_MAP loaded correctly.")
    else:
        print("TELENITY_MAP missing keys.")
        
except Exception as e:
    print(f"Error importing config: {e}")
