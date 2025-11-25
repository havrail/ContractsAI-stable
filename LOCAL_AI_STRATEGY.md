# 🤖 LOCAL AI STRATEJİSİ - Tamamen Offline Çözüm

## 📋 GENEL BAKIŞ

Bu doküman, **ContractsAI** için tamamen local ve offline çalışan AI çözümünü detaylandırır. Cloud servislere (GPT-4, Claude, etc.) ihtiyaç duymadan %90+ doğruluk hedefine ulaşmak için tasarlanmıştır.

---

## 🎯 STRATEJİ: Üç Katmanlı Hybrid Architecture

```
┌────────────────────────────────────────────────────────┐
│  KATMAN 1: Rule-Based Extraction (Hızlı & Kesin)      │
│  - Filename parsing                                    │
│  - Known companies DB (fuzzy matching)                 │
│  - Blacklist filtering                                 │
│  - Regex patterns                                      │
│  → %40-50 coverage, %100 accuracy                     │
└────────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────────┐
│  KATMAN 2: Fine-Tuned Local LLM (Ana Motor)           │
│  - Llama 3.1 8B + LoRA Adapter                        │
│  - Contract-specific training (100-200 örnek)          │
│  - 4-bit quantization (8GB RAM)                        │
│  → %85-92 overall accuracy                            │
└────────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────────┐
│  KATMAN 3: Ensemble Validation & Human-in-Loop        │
│  - Multiple extraction attempts                        │
│  - Consistency scoring                                 │
│  - Low-confidence → Manual review queue               │
│  → %90-95 final accuracy                              │
└────────────────────────────────────────────────────────┘
```

---

## 🔥 KATMAN 2: FINE-TUNED LOCAL LLM (Öncelikli Çözüm)

### **Model Seçimi: Llama 3.1 8B Instruct**

#### Neden Bu Model?
- ✅ **Zaten Kullanımda:** LM Studio ile mevcut sisteminizde çalışıyor
- ✅ **Orta Boyut:** 8B parametre (4-bit quant → ~5GB RAM)
- ✅ **İyi Baseline:** Generic model bile %75-80 veriyor
- ✅ **Fine-tuning Friendly:** LoRA ile 1-2 saatte eğitilebilir
- ✅ **Topluluk Desteği:** Geniş ekosistem, çok kaynak

#### Alternatif Modeller (İhtiyaç Halinde)
1. **Mistral 7B Instruct** - Llama'dan biraz daha küçük, hızlı
2. **Phi-3 Medium (14B)** - Daha büyük ama daha doğru
3. **Qwen 2.5 7B** - Çince + İngilizce güçlü (multilingual)

---

### **Fine-Tuning Süreci (Step-by-Step)**

#### **Adım 1: Training Data Hazırlama**

##### 1.1 Manuel Etiketleme (100-200 Sözleşme)
```python
# data/training_data.jsonl

{"input": "CONTRACT: This Master Services Agreement...", 
 "output": {
   "contract_name": "Master Services Agreement",
   "signing_party": "ABC Corporation",
   "address": "123 Main St, New York, NY 10001",
   "country": "USA",
   "signed_date": "2023-01-15",
   "signature_status": "Fully Signed"
}}

# ... 200 örnek daha
```

**Kaç Örnek Gerekli?**
- **Minimum:** 50 sözleşme (bazı iyileşme)
- **Optimal:** 100-150 sözleşme (%85-90 doğruluk)
- **İdeal:** 200+ sözleşme (%90-95 doğruluk)

**Veri Dağılımı:**
- %40 Basit (tek taraflı, temiz PDF)
- %40 Orta (çok sayfalı, scan edilmiş)
- %20 Zor (karmaşık, çok taraflı, düşük kalite)

##### 1.2 Otomatik Data Augmentation
```python
# scripts/augment_training_data.py

def augment_contract_data(sample):
    """Mevcut örnekleri çoğalt"""
    
    variations = []
    
    # 1. Tarih formatı varyasyonları
    original = sample['output']['signed_date']
    variations.append({
        **sample,
        'input': sample['input'].replace(original, "15/01/2023")
    })
    
    # 2. İsim varyasyonları (büyük/küçük harf)
    # 3. Adres formatları
    # ...
    
    return variations

# 100 örnek → 300 örnek (3x augmentation)
```

---

#### **Adım 2: LoRA Fine-Tuning**

LoRA (Low-Rank Adaptation) = Modelin sadece küçük bir kısmını eğit, tüm parametreleri değil.

**Avantajlar:**
- ⚡ **Hızlı:** 1-2 saat (vs 1-2 gün full fine-tuning)
- 💾 **Az Veri:** 50-100 örnek yeterli
- 💰 **Ucuz:** Normal GPU (RTX 3060) yeterli
- 📦 **Küçük:** Adapter dosyası ~100MB (base model 5GB değişmez)

##### 2.1 Environment Setup
```bash
# 1. Unsloth yükle (en hızlı fine-tuning library)
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install --upgrade --no-deps xformers trl peft accelerate bitsandbytes

# veya Google Colab kullan (ücretsiz GPU)
```

##### 2.2 Training Script
```python
# scripts/finetune_llama.py

from unsloth import FastLanguageModel
import torch

# 1. Base model yükle
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Meta-Llama-3.1-8B-Instruct",
    max_seq_length=4096,
    dtype=None,  # Auto-detect
    load_in_4bit=True,  # 4-bit quantization (RAM optimize)
)

# 2. LoRA configuration
model = FastLanguageModel.get_peft_model(
    model,
    r=16,  # LoRA rank (büyük = daha güçlü ama yavaş)
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
)

# 3. Training data hazırla
from datasets import load_dataset

dataset = load_dataset("json", data_files="data/training_data.jsonl")

def formatting_func(examples):
    """Dataset'i model formatına çevir"""
    texts = []
    for input_text, output_json in zip(examples['input'], examples['output']):
        text = f"""### Instruction:
Extract contract information from the following text and return JSON.

### Input:
{input_text}

### Response:
{json.dumps(output_json)}"""
        texts.append(text)
    return {"text": texts}

dataset = dataset.map(formatting_func, batched=True)

# 4. Trainer setup
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset["train"],
    dataset_text_field="text",
    max_seq_length=4096,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        num_train_epochs=3,  # 3 epoch yeterli
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        output_dir="outputs",
    ),
)

# 5. Train!
trainer.train()

# 6. Save LoRA adapter
model.save_pretrained("lora_model")
tokenizer.save_pretrained("lora_model")

# 7. (Opsiyonel) GGUF formatına çevir (LM Studio için)
model.save_pretrained_gguf("contracts_llama_8b", tokenizer)
```

**Eğitim Süresi:**
- Google Colab (T4 GPU): ~1-2 saat
- RTX 3060 (12GB): ~1 saat
- RTX 4090 (24GB): ~20-30 dakika

**Maliyet:**
- Google Colab Free: $0 (limitli)
- Google Colab Pro: $10/ay (unlimited)
- Kendi GPU: $0 (bir kerelik elektrik)

---

#### **Adım 3: Model Deployment (LM Studio'ya Entegrasyon)**

##### 3.1 GGUF Model Export
```python
# Model'i GGUF formatına çevir (LM Studio formatı)
model.save_pretrained_gguf(
    "contracts_llama_8b",
    tokenizer,
    quantization_method="q4_k_m"  # 4-bit quantization
)

# Çıktı: contracts_llama_8b-Q4_K_M.gguf (~5GB)
```

##### 3.2 LM Studio'ya Yükle
```bash
# 1. Model dosyasını LM Studio models klasörüne kopyala
# Windows: C:\Users\<user>\.cache\lm-studio\models\

cp contracts_llama_8b-Q4_K_M.gguf "C:\Users\dagha\.cache\lm-studio\models\custom\"

# 2. LM Studio'yu aç ve model'i seç
# 3. API Server'ı başlat (localhost:1234)
```

##### 3.3 ContractsAI Config Güncelle
```python
# config.py

# Yeni fine-tuned model
LM_STUDIO_MODEL_NAME = "contracts_llama_8b-Q4_K_M"

# llm_client.py'de model adını güncelle
self.model_name = LM_STUDIO_MODEL_NAME
```

---

### **Beklenen İyileşme**

| Metrik | Baseline (Generic) | Fine-tuned | İyileşme |
|--------|-------------------|------------|----------|
| **Genel Doğruluk** | 75% | **88-92%** | +13-17% |
| **Signing Party** | 80% | **95%** | +15% |
| **Address** | 70% | **90%** | +20% |
| **Country** | 85% | **95%** | +10% |
| **Signed Date** | 88% | **95%** | +7% |
| **Contract Name** | 65% | **85%** | +20% |

---

## 🔄 SÜREKLİ İYİLEŞME DÖNGÜSÜ

```
1. Sözleşmeleri İşle
        ↓
2. Kullanıcı Düzeltmeleri Kaydet (feedback_service.py)
        ↓
3. Her 100 Düzeltmede Export Yap
   (api.py → /api/export/training-data)
        ↓
4. Yeni Training Data ile Re-train
   (3 ayda bir veya 500+ düzeltme)
        ↓
5. Yeni Model Deploy Et
        ↓
1. (Daha İyi Doğrulukla) Tekrar Başla
```

### **Otomatik Re-training Pipeline**

```python
# scripts/auto_retrain.py

def check_and_retrain():
    """Her hafta çalışan otomatik re-training kontrolü"""
    
    feedback = FeedbackService()
    
    # Son re-training'den beri kaç düzeltme var?
    new_corrections = get_corrections_since_last_training()
    
    if len(new_corrections) >= 100:
        logger.info(f"🎓 {len(new_corrections)} yeni düzeltme bulundu. Re-training başlıyor...")
        
        # 1. Export training data
        export_corrections_to_training_data()
        
        # 2. Trigger fine-tuning (Colab notebook veya local)
        trigger_finetuning_job()
        
        # 3. Email bildirim
        send_email("Re-training completed! New model ready.")

# Cron job: Her Pazar 02:00
# 0 2 * * 0 python scripts/auto_retrain.py
```

---

## 🚀 ALTERNATİF: Embedded Tiny Model (Gelecek İçin)

Eğer fine-tuning çok karmaşık geliyorsa, daha küçük bir model **executable içine gömülebilir**.

### **Model: Phi-3 Mini (3.8B)**
- Boyut: ~2GB (quantized)
- RAM: 4GB
- Doğruluk: %80-85 (fine-tune ile %88)

### **Avantaj:**
- ✅ Tek executable, harici bağımlılık yok
- ✅ LM Studio gereksiz
- ✅ Çok hızlı (CPU'da bile)

### **Dezavantaj:**
- ❌ Daha düşük doğruluk (8B modelden)
- ❌ Embedding karmaşık

**Sonuç:** Şimdilik **Fine-tuned Llama 3.1 8B + LM Studio** daha pratik.

---

## 📊 PERFORMANS TAHMİNİ

### **İşlem Hızı (Fine-tuned Model)**
- **Baseline:** 100 PDF = 5 dakika
- **Fine-tuned:** 100 PDF = 4 dakika (LLM daha emin, daha az retry)
- **Confidence > 85%:** %60 → %80 (daha az manuel review)

### **Doğruluk Kazancı**
```
Rule-based (40% coverage, 100% accurate)
    +
Fine-tuned LLM (60% coverage, 90% accurate)
    +
Human Review (low confidence < 15%)
    =
TOPLAM: %92-95 overall accuracy
```

---

## 🛠️ UYGULAMA ADIMLARI (ÖNCELİK SIRASI)

### **Hafta 1: Veri Hazırlama**
- [ ] 100 sözleşme seç (çeşitli tipte)
- [ ] Manuel etiketleme yap (JSON format)
- [ ] Data augmentation uygula (2x-3x çoğalt)
- [ ] Train/test split (80/20)

### **Hafta 2: Fine-tuning**
- [ ] Google Colab setup (veya local GPU)
- [ ] Unsloth + LoRA script hazırla
- [ ] İlk training run (3 epoch)
- [ ] Test set'te doğruluk ölç
- [ ] Hyperparameter tuning (gerekirse)

### **Hafta 3: Deployment & Integration**
- [ ] GGUF export
- [ ] LM Studio'ya yükle
- [ ] ContractsAI'de model değiştir
- [ ] 50 sözleşme ile production test
- [ ] Baseline ile karşılaştır

### **Hafta 4: Monitoring & İyileştirme**
- [ ] Feedback loop aktifleştir
- [ ] Accuracy metrics takip et
- [ ] Problem alanları belirle
- [ ] Prompt tuning yap
- [ ] İkinci iteration planla

---

## 💡 SORU & CEVAPLAR

### **S: Fine-tuning için GPU şart mı?**
**C:** Hayır! Google Colab Free tier yeterli (T4 GPU, ücretsiz). Eğer premium alırsanız ($10/ay) daha hızlı.

### **S: Her düzeltmede re-train etmek gerekir mi?**
**C:** Hayır. Her 100-200 düzeltmede bir (3-6 ayda bir) yeterli.

### **S: Model boyutu çok büyük, küçültebilir miyiz?**
**C:** Evet! 4-bit quantization ile 8B model ~5GB. Daha küçük istiyorsanız Phi-3 Mini (3.8B) kullanabilirsiniz.

### **S: LM Studio yerine direkt Python'da çalıştırabilir miyiz?**
**C:** Evet! `llama-cpp-python` ile direkt entegre edilebilir. Ancak LM Studio daha user-friendly.

### **S: Fine-tuning başarısız olursa?**
**C:** Rule-based + Generic model + Human review ile de %85-88 ulaşılabilir. Fine-tuning bonus.

---

## 📚 KAYNAKLAR

### **Fine-tuning Tutorials:**
- Unsloth Documentation: https://github.com/unslothai/unsloth
- Llama 3.1 Fine-tuning Guide: https://huggingface.co/blog/llama31
- Google Colab Template: https://colab.research.google.com/...

### **Model Hubs:**
- Hugging Face: https://huggingface.co/models
- LM Studio Compatible Models: https://lmstudio.ai/models

### **Community:**
- r/LocalLLaMA (Reddit)
- Hugging Face Forums
- Llama Community Discord

---

## ✅ SONUÇ

**En İyi Strateji:**
1. ✅ **Rule-based extraction** (hızlı kazançlar)
2. ✅ **Fine-tuned Llama 3.1 8B** (ana motor)
3. ✅ **Feedback loop** (sürekli iyileşme)
4. ✅ **Human-in-loop** (low confidence review)

**Hedef:**
- %90-95 overall accuracy
- Tamamen local & offline
- Maliyet: ~$10 (Colab Pro, opsiyonel)
- Süre: 3-4 hafta

**Başlangıç:** Training data hazırlama ✨

---

## 🧩 QWEN3-VL-8B-INSTRUCT GGUF ENTEGRASYON EKİ

### Neden Qwen3-VL-8B?
| İhtiyaç | Qwen VL Katkısı |
|---------|-----------------|
| İmza alanı / mühür tespiti | Görsel encoder ile zero-shot mümkün |
| Scan edilmiş düşük kalite PDF | OCR öncesi görselden doğrudan çıkarım |
| Tablo veya kutu içi metin | Görsel bağlam daha tutarlı yakalanır |
| Çok dilli içeriğin karışımı | TR + EN karışımı iyi idare eder |

### Mimari Öneri (Hybrid Backend)
```
Quality Check (pdf_quality_checker)
     ├─ score >= 80 & text_density yüksek → Text Llama (fine-tuned)
     ├─ score < 80 veya is_scanned True → Qwen3-VL-8B (vision extraction)
     └─ fallback hata → OCR + text model yeniden dene
```

### Backend Abstraction
`model_provider.py` ile üçlü strateji:
1. In-process `llama-cpp-python` (GGUF direkt)
2. LM Studio (OpenAI style endpoint)
3. Ollama (text ağırlıklı, vision sınırlı → sadece fallback)

### Qwen VL Fine-tune Notu
- Multi-modal LoRA için her sayfa görüntüsünü (JPEG) + hedef JSON etiketini eşlemeniz gerekir.
- İlk iterasyonda yalnızca TEXT tower fine-tune yeterli; vision kısmı zero-shot kullanılabilir.
- Vision LoRA için ek karmaşıklık (image patch embedding adaptasyonu). Gelecek faza bırakılmalı.

### Multi-modal Dataset Format (Örnek JSONL satırı)
```json
{
    "page_images": ["data:image/jpeg;base64,....", "data:image/jpeg;base64,..."],
    "full_text": "CONTRACT PAGE 1...\nPAGE 2...",
    "labels": {
        "counterparty_name": "ABC Mobile",
        "address": "Street 12, Tallinn, Estonia",
        "country": "Estonia",
        "signed_date": "2023-06-15",
        "both_signed": true,
        "contract_name": "Master Services Agreement"
    }
}
```

### Önerilen Yol
1. Şimdi: Llama 3.1 8B LoRA (text) + Qwen VL inference (vision sayfalarına seçici).
2. Sonra: Düzeltmelerden multimodal dataset üretimi.
3. Faz 2: Qwen VL LoRA (yalnızca kritik alanlarda - imza statüsü, adres blokları).

### Entegrasyon Durumu
- `llm_client.py` içine unified provider eklendi.
- `model_provider.py` backend geçişi otomatik deniyor.
- İleride pipeline içinde: kalite raporuna göre `provider.chat(...)` çağrısı seçilecektir.

### Önemli Çevresel Değişkenler (.env)
```
LLM_MODEL=Qwen3-VL-8B-Instruct-GGUF
GGUF_MODEL_PATH=./models/Qwen3-VL-8B-Instruct-Q4_K_M.gguf
LM_STUDIO_IP=http://localhost:1234
OLLAMA_HOST=http://localhost:11434
LLAMA_THREADS=8
```

### Test Hızlı Komutları
```bash
python src_python/model_provider.py  # basit quick_test
```

### Riskler & Mitigasyon
| Risk | Çözüm |
|------|-------|
| Vision model yavaş | Sadece düşük kalite sayfalarda kullan |
| Multi-modal fine-tune karmaşık | İlk fazda text LoRA + zero-shot vision |
| GPU bellek sınırı | 4-bit quant, page başına tek görüntü sınırı |
| JSON format sapması | Post-processing regex + doğrulama katmanı |

---
**Qwen VL entegrasyonu eklenmiştir. Fine-tuning fazı için önce text LoRA uygulanacaktır.**
