"""
PDF Quality Checker Module
Analyzes PDF quality and suggests optimal processing strategy.
"""

import os
import io
import numpy as np
from PIL import Image
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pytesseract
from typing import Dict, List, Tuple
from dataclasses import dataclass
from logger import logger
from config import POPPLER_PATH, TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


@dataclass
class QualityReport:
    """PDF kalite raporu"""
    score: int  # 0-100
    issues: List[str]
    is_scanned: bool
    dpi_avg: int
    text_density: float
    page_count: int
    file_size_mb: float
    recommendation: str
    processing_strategy: str  # 'standard', 'enhanced_ocr', 'vision_model'


class PDFQualityChecker:
    """PDF kalite analiz ve optimizasyon önerisi"""
    
    # Kalite Eşikleri
    DPI_MIN = 150
    DPI_OPTIMAL = 200
    TEXT_DENSITY_MIN = 0.5  # Karakter/sayfa minimum
    FILE_SIZE_MAX_MB = 50
    
    def __init__(self):
        self.logger = logger
    
    def analyze(self, pdf_path: str) -> QualityReport:
        """
        PDF'in kapsamlı kalite analizini yapar.
        
        Args:
            pdf_path: PDF dosya yolu
            
        Returns:
            QualityReport: Detaylı kalite raporu
        """
        issues = []
        score = 100  # Başlangıç skoru
        
        # Dosya boyutu kontrolü
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        
        # Sayfa sayısı
        try:
            reader = PdfReader(pdf_path)
            page_count = len(reader.pages)
        except Exception as e:
            self.logger.error(f"PDF okuma hatası: {e}")
            return QualityReport(
                score=0,
                issues=[f"PDF okunamadı: {str(e)}"],
                is_scanned=True,
                dpi_avg=0,
                text_density=0.0,
                page_count=0,
                file_size_mb=file_size_mb,
                recommendation="❌ PDF dosyası bozuk veya şifreli",
                processing_strategy="error"
            )
        
        # Text extraction test
        text_content = self._extract_text_sample(pdf_path, reader)
        text_density = len(text_content) / max(page_count, 1)
        
        # Scanned PDF tespiti
        is_scanned = text_density < 100  # Sayfa başına 100 karakterden az
        
        # DPI kontrolü (ilk 3 sayfa)
        dpi_avg = self._estimate_dpi(pdf_path, sample_pages=min(3, page_count))
        
        # SCORING
        
        # 1. DPI Kontrolü (-20 puan)
        if dpi_avg < self.DPI_MIN:
            score -= 20
            issues.append(f"⚠️ Düşük DPI: {dpi_avg} (minimum {self.DPI_MIN})")
        elif dpi_avg < self.DPI_OPTIMAL:
            score -= 10
            issues.append(f"⚡ Orta DPI: {dpi_avg} (optimal {self.DPI_OPTIMAL})")
        
        # 2. Text Density (-30 puan)
        if is_scanned:
            score -= 30
            issues.append(f"📄 Scan edilmiş PDF - OCR gerekli (text density: {text_density:.1f})")
        elif text_density < 500:
            score -= 15
            issues.append(f"⚠️ Düşük text yoğunluğu: {text_density:.1f} char/page")
        
        # 3. Dosya boyutu (-15 puan)
        if file_size_mb > self.FILE_SIZE_MAX_MB:
            score -= 15
            issues.append(f"💾 Büyük dosya: {file_size_mb:.1f}MB (max {self.FILE_SIZE_MAX_MB}MB)")
        
        # 4. Sayfa sayısı (-10 puan)
        if page_count > 100:
            score -= 10
            issues.append(f"📚 Çok sayfalı: {page_count} sayfa (işlem yavaş olabilir)")
        
        # 5. Rotation check (-10 puan)
        if self._check_rotation(reader):
            score -= 10
            issues.append("🔄 Bazı sayfalar döndürülmüş - düzeltme gerekebilir")
        
        score = max(0, min(100, score))
        
        # Öneri oluştur
        recommendation = self._generate_recommendation(score, is_scanned, dpi_avg)
        processing_strategy = self._suggest_processing_strategy(score, is_scanned, dpi_avg)
        
        return QualityReport(
            score=score,
            issues=issues if issues else ["✅ Kalite iyi"],
            is_scanned=is_scanned,
            dpi_avg=dpi_avg,
            text_density=text_density,
            page_count=page_count,
            file_size_mb=file_size_mb,
            recommendation=recommendation,
            processing_strategy=processing_strategy
        )
    
    def _extract_text_sample(self, pdf_path: str, reader: PdfReader) -> str:
        """İlk 5 sayfadan text örneği çıkar"""
        text = ""
        sample_pages = min(5, len(reader.pages))
        
        for i in range(sample_pages):
            try:
                page_text = reader.pages[i].extract_text()
                text += page_text or ""
            except:
                pass
        
        return text
    
    def _estimate_dpi(self, pdf_path: str, sample_pages: int = 3) -> int:
        """
        PDF'in ortalama DPI'sını tahmin eder.
        Image-based PDF'ler için görüntü boyutundan hesaplar.
        """
        try:
            # İlk sayfayı 72 DPI'da aç (referans)
            images = convert_from_path(
                pdf_path,
                dpi=72,
                first_page=1,
                last_page=min(sample_pages, 3),
                poppler_path=POPPLER_PATH
            )
            
            if not images:
                return 0
            
            # İlk sayfanın boyutu
            width, height = images[0].size
            
            # A4 kağıt: 8.27 x 11.69 inç
            # Eğer sayfa ~600x800 piksel (72 DPI'da) ise, 
            # gerçek DPI muhtemelen daha yüksek
            
            # Basitleştirilmiş tahmin:
            # 72 DPI'da 600px = A4 width (8.27 inç)
            # Gerçek DPI = (width / 8.27) * 72
            
            estimated_dpi = int((width / 8.27) * 72)
            
            # Makul sınırlar
            if estimated_dpi < 50:
                estimated_dpi = 72  # Default
            elif estimated_dpi > 600:
                estimated_dpi = 300  # Makul max
            
            return estimated_dpi
            
        except Exception as e:
            self.logger.warning(f"DPI tahmini başarısız: {e}")
            return 150  # Default assumption
    
    def _check_rotation(self, reader: PdfReader) -> bool:
        """Döndürülmüş sayfaları tespit eder"""
        rotated_pages = 0
        
        for page in reader.pages:
            try:
                rotation = page.get('/Rotate', 0)
                if rotation not in [0, 360]:
                    rotated_pages += 1
            except:
                pass
        
        return rotated_pages > 0
    
    def _generate_recommendation(self, score: int, is_scanned: bool, dpi: int) -> str:
        """Kullanıcı için öneri mesajı"""
        if score >= 80:
            return "✅ Mükemmel kalite - Standart işlem yeterli"
        elif score >= 60:
            if is_scanned:
                return "⚡ Scan edilmiş PDF - Gelişmiş OCR önerilir"
            else:
                return "⚠️ Orta kalite - İşlenebilir ancak doğruluk düşebilir"
        else:
            if dpi < 100:
                return "❌ Çok düşük kalite - PDF'i 200+ DPI'da yeniden tarayın"
            else:
                return "❌ Kritik sorunlar - Manuel kontrol gerekebilir"
    
    def _suggest_processing_strategy(self, score: int, is_scanned: bool, dpi: int) -> str:
        """Hangi işleme stratejisinin kullanılacağını öner"""
        if score >= 80 and not is_scanned:
            return "standard"  # Normal pipeline
        elif is_scanned or score < 80:
            return "enhanced_ocr"  # Image preprocessing + OCR
        elif score < 50:
            return "vision_model"  # Vision-capable LLM gerekli
        else:
            return "standard"
    
    def quick_check(self, pdf_path: str) -> bool:
        """
        Hızlı kalite kontrolü - sadece işlenebilir mi?
        
        Returns:
            bool: True = işlenebilir, False = ciddi sorun var
        """
        report = self.analyze(pdf_path)
        return report.score >= 40  # Minimum eşik


# Convenience function
def check_pdf_quality(pdf_path: str) -> QualityReport:
    """Tek satırda PDF kalite kontrolü"""
    checker = PDFQualityChecker()
    return checker.analyze(pdf_path)


if __name__ == "__main__":
    # Test
    import sys
    
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        
        print("🔍 PDF Kalite Analizi\n" + "=" * 50)
        report = check_pdf_quality(test_path)
        
        print(f"\n📊 Kalite Skoru: {report.score}/100")
        print(f"📄 Sayfa Sayısı: {report.page_count}")
        print(f"💾 Dosya Boyutu: {report.file_size_mb:.1f} MB")
        print(f"📐 Ortalama DPI: {report.dpi_avg}")
        print(f"📝 Text Yoğunluğu: {report.text_density:.1f} char/page")
        print(f"🖨️ Scan Edilmiş: {'Evet' if report.is_scanned else 'Hayır'}")
        print(f"\n💡 Öneri: {report.recommendation}")
        print(f"⚙️ İşleme Stratejisi: {report.processing_strategy}")
        
        if report.issues:
            print(f"\n⚠️ Tespit Edilen Sorunlar:")
            for issue in report.issues:
                print(f"  - {issue}")
    else:
        print("Kullanım: python pdf_quality_checker.py <pdf_path>")
