# 🚀 PROGRAM OPTİMİZASYON ÖNERİLERİ

## 📊 Mevcut Durum Analizi

### Performans Profili
- **100 PDF işleme süresi:** ~5 dakika (optimized)
- **Tek PDF ortalama:** ~3 saniye
- **Ana bottleneck'ler:** PDF image conversion, OCR, LLM inference

---

## 🔥 KRİTİK OPTİMİZASYONLAR (Hemen Uygulanabilir)

### 1. ⚡ PDF Image Caching (-%40 hız artışı)

**Sorun:** Her PDF 2 kere convert ediliyor:
```python
# 1. Signature scan için 100 DPI
low_res_images = convert_from_path(..., dpi=100)
# 2. LLM için 200 DPI (sadece key pages)
imgs = convert_from_path(..., dpi=200)
```

**Çözüm:** Tek seferde tüm sayfaları 200 DPI'da al, downscale et:
```python
def get_all_pages_optimized(self, full_path: str, num_pages: int):
    """Single PDF conversion for all purposes"""
    # Cache key
    cache_key = f"pdf_images:{self.calculate_file_hash(full_path)}"
    
    # Check cache
    cached = self.image_cache.get(cache_key)
    if cached:
        return cached
    
    # Convert once at high DPI
    high_res = convert_from_path(full_path, dpi=200, poppler_path=POPPLER_PATH)
    
    # Create low-res versions for signature scan
    low_res = [img.copy().resize((img.width//2, img.height//2), Image.LANCZOS) 
               for img in high_res]
    
    result = {"high_res": high_res, "low_res": low_res}
    self.image_cache.set(cache_key, result, ttl=300)  # 5 min cache
    return result
```

**Kazanç:** %40-50 hız artışı (PDF conversion en yavaş işlem)

---

### 2. 🎯 Lazy Loading - Sadece Gerekli Sayfalar

**Sorun:** Tüm sayfalar signature scan için convert ediliyor
```python
# Her sayfa convert ediliyor
low_res_images = convert_from_path(..., dpi=100)  # 50 sayfalık PDF = 50 sayfa
```

**Çözüm:** İlk/son + keyword sayfaları öncelikle işle:
```python
def smart_page_selection(self, full_path: str, num_pages: int) -> List[int]:
    """Progressive page selection"""
    # Phase 1: Mandatory pages (always convert)
    pages = {0, num_pages - 1}  # First + last
    
    # Phase 2: Text-based keyword scan (NO IMAGE CONVERSION)
    try:
        reader = PdfReader(full_path)
        for i in [num_pages//3, 2*num_pages//3]:  # Middle samples
            txt = reader.pages[i].extract_text().lower()
            if any(kw in txt for kw in ["address", "signature", "tebligat"]):
                pages.add(i)
    except: pass
    
    # Phase 3: Convert only selected pages
    return sorted(pages)
```

**Kazanç:** 50 sayfalık PDF → 3-5 sayfa convert = %90 daha hız

---

### 3. 💾 Persistent Image Cache (Redis/Disk)

**Mevcut:** Sadece OCR ve LLM sonuçları cache'leniyor  
**Eksik:** PDF→Image conversion cache yok

**Çözüm:**
```python
class ImageCache:
    def __init__(self):
        self.cache_dir = Path("data/image_cache")
        self.cache_dir.mkdir(exist_ok=True)
    
    def get(self, file_hash: str) -> Optional[List[Image.Image]]:
        cache_path = self.cache_dir / f"{file_hash}.pkl"
        if cache_path.exists():
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        return None
    
    def set(self, file_hash: str, images: List[Image.Image]):
        cache_path = self.cache_dir / f"{file_hash}.pkl"
        with open(cache_path, "wb") as f:
            pickle.dump(images, f)
```

**Kazanç:** Aynı PDF tekrar işlendiğinde anında return

---

### 4. 🔀 OCR Parallelization (Thread Pool)

**Sorun:** OCR sayfalar sırayla işleniyor:
```python
for img in llm_images:
    processed = ImageProcessor.preprocess_image(img)
    text += pytesseract.image_to_string(processed, ...)  # Blocking
```

**Çözüm:** Tesseract thread-safe, parallelize et:
```python
from concurrent.futures import ThreadPoolExecutor

def parallel_ocr(self, images: List[Image.Image]) -> str:
    """OCR all pages in parallel"""
    def ocr_single(img):
        try:
            processed = ImageProcessor.preprocess_image(img)
            return pytesseract.image_to_string(processed, lang="tur+eng", 
                                               config=TESSERACT_CONFIG)
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(ocr_single, images))
    
    return "\n".join(results)
```

**Kazanç:** 4 sayfa OCR → 4x hız artışı

---

### 5. ⚙️ Image Preprocessing Optimization

**Sorun:** Her image 5 aşamalı preprocessing yapıyor:
```python
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(...).apply(gray)  # Yavaş
gray = cv2.medianBlur(gray, 3)            # Yavaş
binary = cv2.adaptiveThreshold(...)        # Yavaş
denoised = cv2.fastNlMeansDenoising(...)   # ÇOK YAVAŞ (100ms+)
```

**Çözüm:** Quality-based preprocessing:
```python
def preprocess_image_smart(pil_image, quality_score=100):
    """Adaptive preprocessing based on image quality"""
    img = np.array(pil_image)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # High quality images - minimal processing
    if quality_score >= 80:
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    
    # Medium quality - adaptive threshold only
    elif quality_score >= 60:
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY, 11, 2)
    
    # Low quality - full pipeline
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        # Skip medianBlur and fastNlMeansDenoising (çok yavaş)
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY, 11, 2)
```

**Kazanç:** %70 preprocessing hızlanması (fastNlMeansDenoising atlanıyor)

---

### 6. 🧠 LLM Batch Inference (GPU Kullanımı)

**Sorun:** LLM her dosya için ayrı çağrılıyor:
```python
for file in batch:
    llm_data = self.provider.chat(messages)  # Tek tek
```

**Çözüm:** Batch inference (GPU'da paralel):
```python
def batch_llm_inference(self, batch_messages: List[List[Dict]]) -> List[Dict]:
    """Process multiple files in single GPU batch"""
    if not self.provider.supports_batch:
        return [self.provider.chat(m) for m in batch_messages]
    
    # Batch API call (10x hız artışı GPU'da)
    return self.provider.chat_batch(batch_messages, max_tokens=800)
```

**Kazanç:** GPU kullanımında 5-10x hız artışı

---

## 🔧 ORTA VADELİ İYİLEŞTİRMELER

### 7. 📦 Incremental Processing (Resume Support)

**Özellik:** Job kesintiye uğrarsa kaldığı yerden devam et:
```python
# Checkpoint system
checkpoint = {
    "job_id": job_id,
    "processed_files": ["file1.pdf", "file2.pdf"],
    "last_batch": 3
}
```

### 8. 🎭 Model Quantization (4-bit → 8-bit)

**Mevcut:** 8-bit quantized models  
**İyileştirme:** 4-bit GGUF models (2x hız, minimal doğruluk kaybı)

### 9. 🌐 Multi-GPU Support (Production)

**Özellik:** Multiple Celery workers → her worker farklı GPU

---

## 📊 BEKLENEN KAZANÇLAR

| Optimizasyon | Uygulama | Kazanç | Zorluk |
|--------------|----------|--------|--------|
| **PDF Image Cache** | Hemen | %40-50 | Kolay |
| **Lazy Page Loading** | Hemen | %60-80 | Kolay |
| **Persistent Image Cache** | 1 gün | %80-100 | Orta |
| **OCR Parallelization** | Hemen | %300 (4 core) | Kolay |
| **Smart Preprocessing** | Hemen | %70 | Kolay |
| **LLM Batch Inference** | 1 hafta | %500-1000 (GPU) | Zor |

**Toplam Potansiyel:** %200-400 hız artışı (kolay optimizasyonlar)  
**Ultimate:** %1000+ (tüm optimizasyonlar + GPU batch)

---

## 🚀 ÖNCELİK SIRASI (Hızlı Kazanç)

### Faz 1: Hemen Uygulanabilir (1-2 saat)
1. ✅ Smart Preprocessing (fastNlMeansDenoising'i kaldır)
2. ✅ OCR Parallelization (ThreadPoolExecutor)
3. ✅ Lazy Page Selection (keyword-based)

**Beklenen:** %150-200 hız artışı

### Faz 2: Kısa Vadeli (1 gün)
4. ✅ PDF Image Cache (in-memory LRU cache)
5. ✅ Persistent Image Cache (disk-based)

**Beklenen:** +%100 hız artışı (toplam %250-300)

### Faz 3: Orta Vadeli (1 hafta)
6. ✅ LLM Batch Inference (provider API update)
7. ✅ Incremental Processing (checkpoint system)

**Beklenen:** +%300-500 hız artışı (toplam %500-800)

---

## 💡 KONFİGÜRASYON ÖNERİLERİ

### Optimal Settings (8 Core, 16GB RAM)
```bash
MAX_WORKERS=8              # CPU paralelizasyonu
BATCH_SIZE=20              # Bellek dengesi
OCR_WORKERS=4              # Tesseract paralel
IMAGE_CACHE_SIZE=50        # 50 PDF in-memory
PREPROCESSING_QUALITY=60   # Skip heavy filters
```

### Aggressive (16 Core, 32GB RAM)
```bash
MAX_WORKERS=16
BATCH_SIZE=40
OCR_WORKERS=8
IMAGE_CACHE_SIZE=100
```

### Conservative (4 Core, 8GB RAM)
```bash
MAX_WORKERS=4
BATCH_SIZE=10
OCR_WORKERS=2
IMAGE_CACHE_SIZE=20
```

---

## 🎯 SONUÇ

**Mevcut Baseline:** 100 PDF = 5 dakika  
**Faz 1 sonrası:** 100 PDF = 2 dakika (%150 iyileştirme)  
**Faz 2 sonrası:** 100 PDF = 1 dakika (%400 iyileştirme)  
**Faz 3 sonrası (GPU batch):** 100 PDF = 30 saniye (%900 iyileştirme)

**Önerilen İlk Adım:** Faz 1 optimizasyonlarını uygula (2 saatlik iş, %150 kazanç)
