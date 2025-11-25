"""
Quick Test Script - Yeni özellikleri test eder
"""

import os
import sys

# Add src_python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src_python'))

def test_pdf_quality_checker():
    """PDF Quality Checker testi"""
    print("\n" + "="*60)
    print("🔍 TEST 1: PDF Quality Checker")
    print("="*60)
    
    from src_python.pdf_quality_checker import PDFQualityChecker
    
    checker = PDFQualityChecker()
    
    # Test için örnek PDF (varsa)
    test_pdf = "test_contract.pdf"
    
    if os.path.exists(test_pdf):
        report = checker.analyze(test_pdf)
        
        print(f"\n✅ Kalite Skoru: {report.score}/100")
        print(f"📄 Sayfa Sayısı: {report.page_count}")
        print(f"💾 Dosya Boyutu: {report.file_size_mb:.1f} MB")
        print(f"📐 DPI: {report.dpi_avg}")
        print(f"🖨️ Scan Edilmiş: {'Evet' if report.is_scanned else 'Hayır'}")
        print(f"\n💡 Öneri: {report.recommendation}")
        print(f"⚙️ Strateji: {report.processing_strategy}")
        
        if report.issues:
            print(f"\n⚠️ Sorunlar:")
            for issue in report.issues:
                print(f"  - {issue}")
    else:
        print("⚠️ Test PDF bulunamadı. Simülasyon modu.")
        print("✅ PDFQualityChecker modülü başarıyla yüklendi")


def test_file_renamer():
    """File Renamer testi"""
    print("\n" + "="*60)
    print("📁 TEST 2: Smart File Renamer")
    print("="*60)
    
    from src_python.file_renamer import SmartFileRenamer, suggest_filename
    
    renamer = SmartFileRenamer()
    
    # Test cases
    test_files = [
        ("nda document.pdf", {"doc_type": "NDA", "signing_party": "ABC Corp", "signed_date": "2023-01-15"}),
        ("contract signed 15.01.2023.pdf", {"signing_party": "XYZ Limited", "signed_date": "2023-01-15"}),
        ("msa_company_2024.pdf", None),
    ]
    
    print("\n🔄 Dosya İsmi Önerileri:\n")
    
    for old_name, data in test_files:
        new_name = renamer.suggest_rename(old_name, data)
        print(f"  {old_name}")
        print(f"  → {new_name}")
        print()
    
    print("✅ SmartFileRenamer modülü başarıyla çalıştı")


def test_feedback_service():
    """Feedback Service testi"""
    print("\n" + "="*60)
    print("📊 TEST 3: Feedback Service")
    print("="*60)
    
    from src_python.feedback_service import FeedbackService
    from src_python.database import SessionLocal
    
    db = SessionLocal()
    service = FeedbackService(db)
    
    # Accuracy raporu
    report = service.get_overall_accuracy(days=30)
    
    print(f"\n📈 Son 30 Günlük Doğruluk:")
    print(f"  Genel: {report['overall']['accuracy']:.1f}%")
    print(f"  Toplam Sözleşme: {report['overall']['total_contracts']}")
    print(f"  Toplam Düzeltme: {report['overall']['total_corrections']}")
    
    print("\n🎯 Alan Bazlı:")
    for field, stats in report.items():
        if field != 'overall':
            print(f"  {field}: {stats['accuracy']:.1f}%")
    
    db.close()
    print("\n✅ FeedbackService modülü başarıyla çalıştı")


def test_api_endpoints():
    """API endpoint testi (simülasyon)"""
    print("\n" + "="*60)
    print("🌐 TEST 4: API Endpoints")
    print("="*60)
    
    print("\n✅ Yeni API Endpoint'leri:")
    endpoints = [
        "POST   /api/corrections - Manuel düzeltme kaydı",
        "POST   /api/corrections/bulk - Toplu düzeltme",
        "GET    /api/accuracy - Genel doğruluk raporu",
        "GET    /api/accuracy/{field} - Alan bazlı doğruluk",
        "GET    /api/common-mistakes/{field} - Yaygın hatalar",
        "GET    /api/reports/weekly - Haftalık rapor",
        "POST   /api/export/training-data - Fine-tuning verisi export",
    ]
    
    for endpoint in endpoints:
        print(f"  ✓ {endpoint}")
    
    print("\n💡 Test etmek için:")
    print("  1. Backend'i başlat: python run_dev.py")
    print("  2. API docs'a git: http://localhost:8000/docs")
    print("  3. Endpoint'leri dene")


def test_database():
    """Veritabanı tablolarını test et"""
    print("\n" + "="*60)
    print("🗄️ TEST 5: Database Tables")
    print("="*60)
    
    from src_python.database import SessionLocal
    from src_python.models import AnalysisJob, Contract, Correction, ExtractionPattern
    
    db = SessionLocal()
    
    # Tablo sayılarını kontrol et
    tables_info = [
        ("AnalysisJob", db.query(AnalysisJob).count()),
        ("Contract", db.query(Contract).count()),
        ("Correction", db.query(Correction).count()),
        ("ExtractionPattern", db.query(ExtractionPattern).count()),
    ]
    
    print("\n📊 Veritabanı İstatistikleri:\n")
    for table_name, count in tables_info:
        print(f"  {table_name}: {count} kayıt")
    
    db.close()
    print("\n✅ Tüm tablolar başarıyla oluşturuldu")


def main():
    """Tüm testleri çalıştır"""
    print("\n" + "="*70)
    print("🧪 CONTRACTSAI - YENİ ÖZELLİKLER TEST SÜİTİ")
    print("="*70)
    
    try:
        test_pdf_quality_checker()
    except Exception as e:
        print(f"❌ PDF Quality Checker Test Failed: {e}")
    
    try:
        test_file_renamer()
    except Exception as e:
        print(f"❌ File Renamer Test Failed: {e}")
    
    try:
        test_feedback_service()
    except Exception as e:
        print(f"❌ Feedback Service Test Failed: {e}")
    
    try:
        test_api_endpoints()
    except Exception as e:
        print(f"❌ API Test Failed: {e}")
    
    try:
        test_database()
    except Exception as e:
        print(f"❌ Database Test Failed: {e}")
    
    print("\n" + "="*70)
    print("✅ TÜM TESTLER TAMAMLANDI!")
    print("="*70)
    
    print("\n📚 Sonraki Adımlar:")
    print("  1. ✅ PDF Quality Checker → Pipeline'a entegre et")
    print("  2. ✅ File Renamer → Bulk rename tool çalıştır")
    print("  3. ✅ Feedback System → UI'da düzeltme formu ekle")
    print("  4. 🔄 Fine-tuning → Training data hazırla (LOCAL_AI_STRATEGY.md)")
    print("  5. 📊 Monitoring → Weekly accuracy reports")
    
    print("\n💡 Dokümantasyon:")
    print("  - LOCAL_AI_STRATEGY.md: Fine-tuning rehberi")
    print("  - src_python/pdf_quality_checker.py: PDF analiz")
    print("  - src_python/file_renamer.py: Naming standardı")
    print("  - src_python/feedback_service.py: Öğrenme sistemi")


if __name__ == "__main__":
    main()
