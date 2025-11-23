import sys
import os

# src_python klasörünü yola ekle
sys.path.append(os.path.join(os.getcwd(), "src_python"))

print("-" * 50)
print("Sistem Kontrolü Başlıyor...")
print("-" * 50)

try:
    print("1. Config yükleniyor...")
    from src_python import config
    print("   ✅ Config OK.")
    
    print("2. Utils yükleniyor...")
    from src_python import utils
    if hasattr(utils, 'normalize_country'):
        print("   ✅ Utils OK (normalize_country bulundu).")
    else:
        print("   ❌ Utils HATALI: 'normalize_country' fonksiyonu yok!")
        print("      Lütfen utils.py dosyasını güncellediğinizden emin olun.")
        sys.exit(1)

    print("3. LLM Client yükleniyor...")
    from src_python import llm_client
    print("   ✅ LLM Client OK.")

    print("4. Pipeline yükleniyor...")
    from src_python import pipeline
    print("   ✅ Pipeline OK.")

    print("5. Tasks (Celery) yükleniyor...")
    from src_python import tasks
    print("   ✅ Tasks OK.")
    
    print("-" * 50)
    print("🎉 TEBRİKLER! Kodda Syntax veya Import hatası yok.")
    print("Celery Worker'ı şimdi tekrar başlatabilirsiniz.")
    print("-" * 50)

except ImportError as e:
    print(f"\n❌ İMPORT HATASI: {e}")
    print("Hangi dosyanın eksik veya hatalı olduğunu yukarıdaki adımlardan anlayabilirsiniz.")
except SyntaxError as e:
    print(f"\n❌ YAZIM HATASI (SyntaxError): {e}")
    print(f"Hata Yeri: {e.filename}, Satır: {e.lineno}")
except Exception as e:
    print(f"\n❌ BEKLENMEYEN HATA: {e}")
