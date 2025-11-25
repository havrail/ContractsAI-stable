# 🎯 Quality Assurance System - Kullanım Kılavuzu

ContractsAI'ın kapsamlı kalite kontrol ve review sistemi.

---

## 📋 İçindekiler

1. [Multi-Stage Validation](#1-multi-stage-validation)
2. [Review UI](#2-review-ui)
3. [Ground Truth Dataset](#3-ground-truth-dataset)
4. [Audit Logging](#4-audit-logging)
5. [Deduplication & Versioning](#5-deduplication--versioning)
6. [API Endpoints](#6-api-endpoints)

---

## 1️⃣ Multi-Stage Validation

### Nasıl Çalışır?

Her sözleşme 5 aşamalı validasyondan geçer:

```python
from validation import validate_contract

validation_result = validate_contract(
    party="Acme Corp",
    contract_type="Service Agreement",
    signed_date="2024-05-15",
    start_date="2024-06-01",
    end_date="2025-06-01",
    address="123 Main St, New York",
    country="USA",
    initial_confidence=85.0,
    ocr_quality=92.0,
    llm_confidence=88.0
)

print(f"Overall Confidence: {validation_result.overall_confidence}%")
print(f"Needs Review: {validation_result.needs_review}")
print(f"Issues: {validation_result.critical_issues}")
```

### Validation Aşamaları

#### Stage 1: Field-Level Validation
- **Party**: Boş değil mi? Placeholder değil mi?
- **Date**: Format doğru mu (YYYY-MM-DD)? Mantıklı bir yıl mı?
- **Address**: En az 15 karakter mi?
- **Country**: Bilinen ülkeler listesinde mi?

#### Stage 2: Cross-Field Validation
- Signed date < start date mi?
- End date > start date mi?
- Contract süresi mantıklı mı? (30 gün - 10 yıl arası)

#### Stage 3: OCR Quality Check
- OCR kalitesi >= 60% mı?
- Düşükse warning ver

#### Stage 4: LLM Confidence Check
- LLM confidence >= 50% mi?
- Düşükse flag et

#### Stage 5: Anomaly Detection
- Tekrarlayan karakterler var mı?
- All caps (OCR hatası olabilir)
- Garip karakterler var mı?

### Confidence Skorlama

```python
# Weighted scoring
weights = {
    'party': 0.20,
    'contract_type': 0.15,
    'signed_date': 0.15,
    'address': 0.10,
    'country': 0.10,
    # ...
}

# Penalties
issue_penalty = 5% per issue
warning_penalty = 2% per warning
```

### Review Gereksinimi

**Otomatik review flag'lenir eğer:**
- Confidence < 50%
- Critical issues > 0
- Warnings >= 5
- Critical field invalid (party, signed_date, contract_type)

---

## 2️⃣ Review UI

### Kullanım

1. **Dashboard'da "Review Queue" tab'ına tıkla**
2. Pending contracts listesi görünür
3. Her sözleşmeyi expand et
4. **Field-by-field düzenleme:**
   - Edit butonu → değeri düzenle
   - Save butonu → kaydet
5. **Review decision:**
   - ✅ **Approve**: Onaylı, needs_review = false
   - ❌ **Reject**: Reddedildi
   - ✏️ **Correct**: Manuel düzeltme yapıldı

### Confidence Indicators

- **🟢 Excellent (90%+)**: Otomatik onaylanabilir
- **🔵 Good (75-89%)**: Minimal review
- **🟡 Acceptable (60-74%)**: Review önerilir
- **🔴 Low (<60%)**: Manuel review gerekli

### API Kullanımı

```python
import requests

# Get pending reviews
response = requests.get(
    "http://localhost:8000/api/review/pending",
    headers={"X-API-Key": "dev-key-12345"}
)

contracts = response.json()['contracts']

# Review a contract
requests.post(
    f"http://localhost:8000/api/review/{contract_id}",
    json={
        "review_status": "approved",
        "reviewed_by": "john.doe",
        "notes": "Looks good"
    },
    headers={"X-API-Key": "dev-key-12345"}
)

# Correct a field
requests.post(
    f"http://localhost:8000/api/correct/{contract_id}",
    json={
        "field_name": "address",
        "new_value": "456 Oak St, Boston, MA",
        "old_value": "456 Oak",
        "corrected_by": "john.doe",
        "reason": "Incomplete address"
    },
    headers={"X-API-Key": "dev-key-12345"}
)
```

---

## 3️⃣ Ground Truth Dataset

### Dataset Oluşturma

#### Yöntem 1: Manuel Ekleme

```python
from tests.test_ground_truth import GroundTruthManager

gt_manager = GroundTruthManager()

gt_manager.add_record(
    filename="contract_001.pdf",
    party="Acme Corporation",
    contract_type="Service Agreement",
    signed_date="2024-05-15",
    address="123 Main St, New York, NY 10001",
    country="USA",
    notes="Verified by legal team",
    verified_by="john.doe"
)
```

#### Yöntem 2: Excel'den Import

```python
from tests.test_ground_truth import create_ground_truth_from_verified_export

# Excel'de "is_verified" kolonu True olan satırları al
count = create_ground_truth_from_verified_export("verified_contracts.xlsx")
print(f"Imported {count} records")
```

### Automated Testing

```python
from tests.test_ground_truth import run_tests_from_results

# Pipeline'dan gelen sonuçları test et
results = pipeline.run_job(...)  # Extraction results

test_summary = run_tests_from_results(results)

print(f"Average Accuracy: {test_summary.average_accuracy}%")
print(f"Passed: {test_summary.passed}/{test_summary.total_files}")
print(f"Field Accuracy:")
for field, accuracy in test_summary.field_accuracy.items():
    print(f"  {field}: {accuracy:.2f}%")
```

### Test Raporları

Test sonuçları otomatik olarak kaydedilir:

```
tests/
├── ground_truth_dataset.json  # Ground truth data
└── test_report.json            # Test sonuçları
```

### Regression Testing

Her deploy öncesi:

```bash
# Run regression tests
python -c "from tests.test_ground_truth import *; run_tests_from_results(get_latest_results())"
```

---

## 4️⃣ Audit Logging

### Otomatik Logging

Tüm aksiyonlar otomatik loglanır:

```python
from audit import AuditLogger

audit = AuditLogger(db, user_id="john.doe", ip_address="192.168.1.100")

# Contract processed
audit.log_contract_processed(
    contract_id=123,
    filename="contract.pdf",
    confidence=85.5,
    processing_time_ms=2500
)

# Field corrected
audit.log_field_correction(
    contract_id=123,
    field_name="address",
    old_value="123 Main",
    new_value="123 Main St, Boston",
    correction_reason="Incomplete"
)
```

### Context Manager (Auto-tracking)

```python
with audit.track_action("export", "system", details={"format": "excel"}):
    # Export işlemi
    export_to_excel(contracts)
    # Otomatik duration ve status loglanır
```

### Audit Dashboard

```python
# Get statistics
import requests

stats = requests.get(
    "http://localhost:8000/api/audit/stats?days=7",
    headers={"X-API-Key": "dev-key-12345"}
).json()

print(f"Total Actions: {stats['total_actions']}")
print(f"Success Rate: {stats['success_rate']}%")
print(f"Actions by Type: {stats['actions_by_type']}")
```

### Recent Logs

```python
logs = requests.get(
    "http://localhost:8000/api/audit/logs?limit=50&action_type=correct",
    headers={"X-API-Key": "dev-key-12345"}
).json()

for log in logs['logs']:
    print(f"{log['timestamp']}: {log['action_type']} by {log['user_id']}")
```

---

## 5️⃣ Deduplication & Versioning

### Duplicate Detection

```python
from deduplication import DeduplicationService

service = DeduplicationService(db)

# Find duplicates
unique, duplicates = service.find_duplicates(new_contracts)

print(f"Unique: {len(unique)}")
print(f"Duplicates: {len(duplicates)}")

# Merge duplicate info (keep higher confidence)
for existing, new_data in conflicts:
    service.merge_duplicate_info(existing, new_data)
```

### Export Versioning

```python
from deduplication import ExportVersionControl

service = ExportVersionControl(db)

# Create version
version = service.create_export_version(
    export_path="exports/contracts_v5.xlsx",
    contracts=contract_list,
    created_by="john.doe",
    notes="Monthly export"
)

print(f"Version {version.version_number} created")

# Get history
history = service.get_export_history(limit=10)
for v in history:
    print(f"v{v['version']}: {v['total_records']} records - {v['created_at']}")

# Compare versions
comparison = service.compare_versions(version1=4, version2=5)
print(f"Added: {comparison['added_count']}")
print(f"Removed: {comparison['removed_count']}")
print(f"Change: {comparison['change_percentage']}%")

# Rollback
old_export_path = service.rollback_to_version(version_number=4)
```

### API Usage

```bash
# Get export history
curl http://localhost:8000/api/exports/history \
  -H "X-API-Key: dev-key-12345"

# Compare versions
curl http://localhost:8000/api/exports/compare/4/5 \
  -H "X-API-Key: dev-key-12345"
```

---

## 6️⃣ API Endpoints

### Review Endpoints

```
GET  /api/review/pending                 # Get contracts needing review
POST /api/review/{contract_id}           # Submit review decision
POST /api/correct/{contract_id}          # Correct a field
```

### Audit Endpoints

```
GET  /api/audit/stats?days=7             # Get audit statistics
GET  /api/audit/logs?limit=50            # Get recent audit logs
```

### Export Endpoints

```
GET  /api/exports/history                # Get export version history
GET  /api/exports/compare/{v1}/{v2}      # Compare two versions
```

---

## 🚀 Quick Start

### 1. Database Migration

```bash
cd src_python
alembic upgrade head
```

### 2. Start Services

```bash
# Terminal 1: Celery
celery -A celery_app worker --loglevel=info --pool=solo

# Terminal 2: Backend
python run_dev.py
```

### 3. Use Review UI

1. Analyze contracts
2. Switch to "Review Queue" tab
3. Review flagged contracts
4. Approve or correct

### 4. Monitor Quality

```python
# Check validation stats
from sqlalchemy import func
from models import Contract

# Contracts needing review
needs_review = db.query(func.count(Contract.id)).filter(
    Contract.needs_review == 1,
    Contract.review_status == 'pending'
).scalar()

print(f"Pending reviews: {needs_review}")

# Average confidence
avg_confidence = db.query(func.avg(Contract.confidence_score)).scalar()
print(f"Average confidence: {avg_confidence:.2f}%")
```

---

## 📊 Monitoring Dashboard

### Key Metrics

- **Pending Reviews**: Contracts needing manual review
- **Average Confidence**: Overall extraction quality
- **Validation Pass Rate**: % without critical issues
- **Review Turnaround**: Time from flag to approval
- **Field Accuracy**: Per-field extraction accuracy
- **Audit Activity**: User actions over time

### Alerts

Set up alerts for:
- High pending review count (>50)
- Low average confidence (<70%)
- High duplicate rate (>10%)
- Failed audit actions

---

## 💡 Best Practices

### 1. Regular Testing
- Run regression tests weekly
- Update ground truth dataset monthly
- Review test failures promptly

### 2. Review Workflow
- Process high-confidence contracts automatically (>90%)
- Queue medium confidence for spot checks (75-90%)
- Require full review for low confidence (<75%)

### 3. Data Quality
- Maintain at least 100 ground truth records
- Include diverse contract types
- Update after system improvements

### 4. Audit Hygiene
- Review audit logs weekly
- Monitor error patterns
- Track correction frequency by field

### 5. Version Control
- Create export version before major changes
- Compare versions after updates
- Keep rolling 30-day history

---

## 🔧 Troubleshooting

### Issue: Too Many Pending Reviews

**Solution:**
```python
# Lower review threshold
REVIEW_THRESHOLD = 40  # Was 50

# Or auto-approve high confidence
if confidence >= 90 and validation_issues == 0:
    needs_review = False
```

### Issue: Low Field Accuracy

**Solution:**
1. Check ground truth quality
2. Review failed extractions
3. Update prompts/hints
4. Add training data

### Issue: Duplicate Detection Misses

**Solution:**
```python
# Adjust hash calculation to include more fields
content_parts = [
    party, signed_date, contract_name,
    address,  # Add full address
    country   # Add country
]
```

---

## 📝 Example Workflow

```python
# 1. Process contracts
pipeline = PipelineManager()
results = pipeline.run_job(job_id=1, folder_path="/contracts")

# 2. Auto-flagged contracts sent to review queue
# (happens automatically based on validation)

# 3. User reviews via UI or API
# (manual approval/correction)

# 4. Export with versioning
from deduplication import track_export

contracts = db.query(Contract).filter(
    Contract.review_status == 'approved'
).all()

version = track_export(db, "exports/final.xlsx", contracts, "john.doe")

# 5. Run regression tests
from tests.test_ground_truth import run_tests_from_results

summary = run_tests_from_results(results)
if summary.average_accuracy < 80:
    alert_team("Low accuracy detected!")

# 6. Monitor audit logs
from audit import get_audit_stats

stats = get_audit_stats(db, days=7)
print(f"This week: {stats['total_actions']} actions")
print(f"Success rate: {stats['success_rate']}%")
```

---

## ✅ System Ready!

Tüm QA features aktif. Şimdi test edebilirsiniz:

```bash
# 1. Run migration
cd src_python
alembic upgrade head

# 2. Start services
python run_dev.py

# 3. Process contracts
# -> Low confidence contracts auto-flagged

# 4. Review in UI
# -> http://localhost:5174 -> Review Queue tab

# 5. Check audit logs
# -> http://localhost:8000/api/audit/logs
```
