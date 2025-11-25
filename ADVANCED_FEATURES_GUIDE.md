# 🚀 Advanced Features Guide

ContractsAI'ın gelişmiş özellikleri: A/B Testing ve Folder Automation.

---

## 📋 İçindekiler

1. [A/B Testing Framework](#1-ab-testing-framework)
2. [Folder Structure Automation](#2-folder-structure-automation)
3. [API Usage Examples](#3-api-usage-examples)

---

## 1️⃣ A/B Testing Framework

### Amaç
Farklı prompt varyasyonlarını test ederek en iyi performansı veren promptu otomatik belirle.

### Nasıl Çalışır?

#### 1. Prompt Varyantları Tanımla

```python
from ab_testing import ABTestManager
from database import SessionLocal

db = SessionLocal()
manager = ABTestManager(db)

# Yeni varyant ekle
manager.add_variant(
    variant_id="v5_minimal",
    name="Minimal Prompt",
    template="minimal",
    description="Ultra-minimal prompt for speed"
)
```

#### 2. A/B Test Çalıştır

```python
from ab_testing import run_prompt_ab_test

# Son 7 günün verisi üzerinden test
result = run_prompt_ab_test(
    db,
    variant_ids=["v1_standard", "v2_detailed", "v3_structured"],
    days=7
)

print(f"Winner: {result.winner}")
print(f"Confidence: {result.confidence_level:.1f}%")
print(f"Recommendation: {result.recommendation}")
```

#### 3. Test Metrikleri

Her varyant için ölçülen metrikler:

```python
metrics = result.metrics["v1_standard"]

print(f"Total Contracts: {metrics.total_contracts}")
print(f"Avg Confidence: {metrics.avg_confidence:.1f}%")
print(f"Correction Rate: {metrics.correction_rate:.1f}%")
print(f"Review Rate: {metrics.review_rate:.1f}%")
print(f"Field Accuracy: {metrics.field_accuracy}")
```

### Composite Scoring

Winner belirleme formülü:

```
Score = (avg_confidence * 0.4) +
        ((100 - correction_rate) * 0.3) +
        ((100 - review_rate) * 0.2) +
        ((100 - error_count) * 0.1)
```

**Ağırlıklar:**
- %40: Confidence score
- %30: Accuracy (düzeltme ihtiyacı düşük)
- %20: Auto-approval rate (review ihtiyacı düşük)
- %10: Error reduction

### API Kullanımı

```bash
# A/B test çalıştır
curl http://localhost:8000/api/ab-test/run?days=7 \
  -H "X-API-Key: dev-key-12345"

# Mevcut varyantları listele
curl http://localhost:8000/api/ab-test/variants \
  -H "X-API-Key: dev-key-12345"

# En iyi promptu al
curl http://localhost:8000/api/ab-test/best-prompt \
  -H "X-API-Key: dev-key-12345"
```

### Python API

```python
import requests

# A/B test çalıştır
response = requests.get(
    "http://localhost:8000/api/ab-test/run?days=7",
    headers={"X-API-Key": "dev-key-12345"}
)

result = response.json()

if result['success']:
    print(f"🏆 Winner: {result['winner']}")
    print(f"📊 Confidence: {result['confidence']}%")
    print(f"💡 {result['recommendation']}")
    
    # Metrics comparison
    for variant_id, metrics in result['metrics'].items():
        print(f"\n{variant_id}:")
        print(f"  Confidence: {metrics['avg_confidence']:.1f}%")
        print(f"  Corrections: {metrics['correction_rate']:.1f}%")
```

### Confidence Levels

- **80%+**: STRONG - Deploy to production immediately
- **60-79%**: MODERATE - Consider extending test
- **40-59%**: WEAK - No clear winner, similar performance
- **<40%**: INCONCLUSIVE - Need more data

### Best Practices

1. **Minimum Sample Size**: En az 30 contract per variant
2. **Test Duration**: Minimum 7 gün (1 hafta)
3. **Variant Count**: 2-4 varyant (çok fazla varyant split eder)
4. **Statistical Significance**: Confidence >60% olana kadar test et

### Configuration File

`data/ab_test_config.json`:

```json
{
  "variants": [
    {
      "id": "v1_standard",
      "name": "Standard Prompt",
      "template": "standard",
      "description": "Original prompt",
      "is_active": true
    },
    {
      "id": "v2_detailed",
      "name": "Detailed Prompt",
      "template": "detailed",
      "description": "More detailed instructions",
      "is_active": true
    }
  ],
  "active_test": null
}
```

---

## 2️⃣ Folder Structure Automation

### Amaç
İşlenmiş sözleşmeleri otomatik olarak düzenli klasör yapısına organize et.

### Organization Methods

#### Method 1: By Contract Type

```python
from folder_automation import organize_contracts

contracts = db.query(Contract).all()
contract_dicts = [...]  # Convert to dicts

result = organize_contracts(
    contracts=contract_dicts,
    source_folder="input_pdfs",
    method="type",
    output_dir="organized_contracts"
)
```

**Çıktı Yapısı:**
```
organized_contracts/
├── Service_Agreements/
│   ├── contract1.pdf
│   └── contract3.pdf
├── NDAs/
│   └── contract2.pdf
└── Purchase_Orders/
    └── contract4.pdf
```

#### Method 2: By Company

```python
result = organize_contracts(
    contracts=contract_dicts,
    source_folder="input_pdfs",
    method="company",
    output_dir="organized_by_company"
)
```

**Çıktı Yapısı:**
```
organized_by_company/
├── Acme_Corp/
│   ├── contract1.pdf
│   └── contract3.pdf
└── Nokia/
    └── contract2.pdf
```

#### Method 3: By Date

```python
result = organize_contracts(
    contracts=contract_dicts,
    source_folder="input_pdfs",
    method="date",
    output_dir="organized_by_date"
)
```

**Çıktı Yapısı:**
```
organized_by_date/
├── 2024/
│   ├── 01_January/
│   │   └── contract1.pdf
│   └── 06_June/
│       └── contract2.pdf
└── 2025/
    └── 01_January/
        └── contract3.pdf
```

#### Method 4: By Confidence Score

```python
result = organize_contracts(
    contracts=contract_dicts,
    source_folder="input_pdfs",
    method="confidence",
    output_dir="organized_by_confidence"
)
```

**Çıktı Yapısı:**
```
organized_by_confidence/
├── High_Confidence_90plus/
│   ├── contract1.pdf
│   └── contract3.pdf
├── Medium_Confidence_70_89/
│   └── contract2.pdf
└── Low_Confidence_50_69/
    └── contract4.pdf
```

#### Method 5: Hierarchical (Recommended)

```python
result = organize_contracts(
    contracts=contract_dicts,
    source_folder="input_pdfs",
    method="hierarchical",
    output_dir="organized_hierarchical"
)
```

**Çıktı Yapısı:**
```
organized_hierarchical/
├── 2024/
│   ├── Acme_Corp/
│   │   ├── Service_Agreement/
│   │   │   └── contract1.pdf
│   │   └── NDA/
│   │       └── contract5.pdf
│   └── Nokia/
│       └── Service_Agreement/
│           └── contract2.pdf
└── 2025/
    └── Acme_Corp/
        └── Service_Agreement/
            └── contract3.pdf
```

### API Usage

```bash
# Organize contracts
curl -X POST http://localhost:8000/api/organize \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "hierarchical",
    "output_dir": "organized_contracts"
  }'
```

### Python API

```python
import requests

response = requests.post(
    "http://localhost:8000/api/organize",
    json={
        "method": "hierarchical",
        "output_dir": "organized_contracts"
    },
    headers={"X-API-Key": "dev-key-12345"}
)

result = response.json()
print(f"✅ {result['files_organized']} files organized")
print(f"📁 {result['folders_created']} folders created")
```

### Organization Report

Her organize işleminden sonra otomatik rapor oluşur:

`organized_contracts/organization_report.txt`:

```
============================================================
CONTRACT ORGANIZATION REPORT
============================================================
Generated: 2024-11-25 14:30:00
Total Folders: 8
Total Files: 45

============================================================

📁 2024/Acme_Corp/Service_Agreement/ (3 files)
   └── contract1.pdf
   └── contract5.pdf
   └── contract8.pdf

📁 2024/Nokia/NDA/ (2 files)
   └── contract2.pdf
   └── contract6.pdf

...
```

### Custom Organization

```python
from folder_automation import FolderOrganizer

organizer = FolderOrganizer(base_output_dir="custom_output")

# Custom logic
organized = {}
for contract in contracts:
    # Your custom organization logic
    country = contract['country']
    year = contract['signed_date'][:4]
    
    folder_path = f"{country}/{year}"
    # ... organize files
```

### Folder Name Sanitization

Otomatik olarak:
- ✅ Geçersiz karakterler temizlenir (`<>:"/\|?*`)
- ✅ Boşluklar underscore'a çevrilir
- ✅ Uzun isimler kısaltılır (max 50 karakter)
- ✅ Multiple underscores birleştirilir

**Örnek:**
```
"Service Agreement (2024)" → "Service_Agreement_2024"
"Acme Corp. / Inc." → "Acme_Corp_Inc"
```

---

## 3️⃣ API Usage Examples

### Complete Workflow

```python
import requests

API_URL = "http://localhost:8000"
API_KEY = "dev-key-12345"
headers = {"X-API-Key": API_KEY}

# 1. Run A/B test
print("🔬 Running A/B test...")
ab_result = requests.get(f"{API_URL}/api/ab-test/run?days=7", headers=headers).json()

if ab_result['success']:
    winner = ab_result['winner']
    print(f"✅ Winner: {winner} ({ab_result['confidence']:.1f}%)")
    
    # 2. Deploy winner (manual step - update config)
    # In production, automatically switch to winner
    
    # 3. Process new batch with best prompt
    print("\n📄 Processing contracts...")
    job = requests.post(
        f"{API_URL}/analyze",
        json={"folder_path": "new_contracts"},
        headers=headers
    ).json()
    
    job_id = job['job_id']
    
    # Wait for completion...
    
    # 4. Organize results
    print("\n📁 Organizing contracts...")
    org_result = requests.post(
        f"{API_URL}/api/organize",
        json={
            "method": "hierarchical",
            "output_dir": "organized_contracts"
        },
        headers=headers
    ).json()
    
    print(f"✅ Organized {org_result['files_organized']} files")
    print(f"📊 Created {org_result['folders_created']} folders")
    
    # 5. Check accuracy
    print("\n📈 Checking accuracy...")
    accuracy = requests.get(
        f"{API_URL}/api/accuracy",
        headers=headers
    ).json()
    
    print(f"Overall Accuracy: {accuracy['overall']['accuracy']:.1f}%")
```

### Automated Daily Workflow

```python
#!/usr/bin/env python3
"""
Daily automation script for ContractsAI.
Run this via cron/scheduler daily.
"""

import requests
from datetime import datetime

API_URL = "http://localhost:8000"
API_KEY = "dev-key-12345"
headers = {"X-API-Key": API_KEY}

def daily_workflow():
    print(f"🕐 Daily workflow started: {datetime.now()}")
    
    # 1. Weekly A/B test (every Monday)
    if datetime.now().weekday() == 0:
        print("\n📊 Running weekly A/B test...")
        ab_result = requests.get(
            f"{API_URL}/api/ab-test/run?days=7",
            headers=headers
        ).json()
        
        if ab_result['success'] and ab_result['confidence'] > 80:
            print(f"🏆 Strong winner found: {ab_result['winner']}")
            # TODO: Auto-deploy winner
    
    # 2. Check pending reviews
    print("\n👁️ Checking pending reviews...")
    pending = requests.get(
        f"{API_URL}/api/review/pending",
        headers=headers
    ).json()
    
    if pending['total'] > 50:
        print(f"⚠️ WARNING: {pending['total']} contracts need review!")
        # TODO: Send alert
    
    # 3. Generate accuracy report
    print("\n📈 Generating accuracy report...")
    accuracy = requests.get(
        f"{API_URL}/api/accuracy",
        headers=headers
    ).json()
    
    if accuracy['overall']['accuracy'] < 80:
        print(f"⚠️ WARNING: Accuracy dropped to {accuracy['overall']['accuracy']:.1f}%")
        # TODO: Investigate and alert
    
    # 4. Organize yesterday's contracts
    print("\n📁 Organizing contracts...")
    org_result = requests.post(
        f"{API_URL}/api/organize",
        json={"method": "hierarchical"},
        headers=headers
    ).json()
    
    print(f"✅ Organized {org_result['files_organized']} files")
    
    print(f"\n✅ Daily workflow completed: {datetime.now()}")

if __name__ == "__main__":
    daily_workflow()
```

### Schedule with Cron (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Add daily workflow at 2 AM
0 2 * * * /usr/bin/python3 /path/to/daily_workflow.py >> /var/log/contractsai_daily.log 2>&1
```

### Schedule with Task Scheduler (Windows)

```powershell
# Create scheduled task for daily workflow
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "C:\path\to\daily_workflow.py"
$trigger = New-ScheduledTaskTrigger -Daily -At 2AM
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "ContractsAI Daily Workflow" -Description "Daily automation for ContractsAI"
```

---

## 🎯 Best Practices

### A/B Testing

1. **Start Small**: 2-3 varyant ile başla
2. **Wait for Data**: En az 30 contract per variant
3. **Test Duration**: Minimum 1 hafta
4. **Iterate**: Kazanan promptu base alarak yeni varyantlar test et
5. **Monitor**: Accuracy düşerse rollback yap

### Folder Organization

1. **Backup First**: Organize etmeden önce backup al
2. **Test Small**: Küçük batch ile test et
3. **Hierarchical**: Büyük datasets için hierarchical method kullan
4. **Automation**: Export'tan sonra otomatik organize et
5. **Clean Names**: Company/contract names standardize et

### Integration

```python
# Pipeline'a entegre et
class PipelineManager:
    def run_job(self, job_id, folder_path):
        # ... existing processing ...
        
        # After processing
        if all_contracts:
            # Auto-organize
            from folder_automation import organize_contracts
            organize_contracts(
                contracts=all_contracts,
                source_folder=folder_path,
                method="hierarchical",
                output_dir=f"organized_{job_id}"
            )
```

---

## ✅ System Ready!

Tüm gelişmiş özellikler aktif:

```bash
# Test A/B
curl http://localhost:8000/api/ab-test/run?days=7 -H "X-API-Key: dev-key-12345"

# Test Organization
curl -X POST http://localhost:8000/api/organize \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"method": "hierarchical"}'
```

🎉 **Ready to optimize!**
