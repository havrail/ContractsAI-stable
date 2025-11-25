"""
Feedback Service Module
Handles user corrections and adaptive learning from feedback.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from models import Contract, Correction, ExtractionPattern
from database import SessionLocal, get_db
from logger import logger


class FeedbackService:
    """
    Manuel düzeltmeleri kaydeder ve sistemin öğrenmesini sağlar.
    
    Özellikler:
    - Correction tracking (hangi alanlar sık düzeltiliyor?)
    - Pattern learning (hangi hatalar tekrar ediyor?)
    - Accuracy reporting (alan bazlı doğruluk oranları)
    - Adaptive prompting (hataları prompt'a ekle)
    """
    
    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self.logger = logger
    
    def record_correction(
        self,
        contract_id: int,
        field_name: str,
        old_value: str,
        new_value: str,
        corrected_by: str = "user",
        reason: Optional[str] = None
    ) -> Correction:
        """
        Kullanıcının yaptığı düzeltmeyi kaydeder.
        
        Args:
            contract_id: Düzeltilen sözleşme ID
            field_name: Düzeltilen alan ('address', 'signing_party', etc.)
            old_value: AI'ın çıkardığı orijinal değer
            new_value: Kullanıcının düzelttiği değer
            corrected_by: Kim düzeltti (email/username)
            reason: Düzeltme nedeni (opsiyonel)
            
        Returns:
            Correction: Kaydedilen düzeltme
        """
        # Contract'ı bul
        contract = self.db.query(Contract).filter(Contract.id == contract_id).first()
        
        if not contract:
            raise ValueError(f"Contract ID {contract_id} bulunamadı")
        
        # Correction kaydı oluştur
        correction = Correction(
            contract_id=contract_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            corrected_by=corrected_by,
            corrected_at=datetime.utcnow(),
            correction_reason=reason,
            confidence_before=contract.confidence_score
        )
        
        self.db.add(correction)
        
        # Contract'ı güncelle
        setattr(contract, field_name, new_value)
        
        # Confidence score'u artır (düzeltme yapıldı = artık doğru)
        if contract.confidence_score < 100:
            contract.confidence_score = min(100, contract.confidence_score + 10)
        
        self.db.commit()
        self.db.refresh(correction)
        
        self.logger.info(
            f"✏️ Correction recorded: Contract {contract_id}, "
            f"Field '{field_name}', By '{corrected_by}'"
        )
        
        # Pattern analizi yap
        self._analyze_correction_pattern(correction)
        
        return correction
    
    def bulk_record_corrections(self, corrections: List[Dict]) -> int:
        """
        Toplu düzeltme kaydı.
        
        Args:
            corrections: Liste of dicts with keys:
                {contract_id, field_name, old_value, new_value, corrected_by}
        
        Returns:
            int: Kaydedilen düzeltme sayısı
        """
        count = 0
        
        for corr_data in corrections:
            try:
                self.record_correction(**corr_data)
                count += 1
            except Exception as e:
                self.logger.error(f"Bulk correction error: {e}")
        
        return count
    
    def get_field_accuracy(
        self,
        field_name: str,
        days: int = 30
    ) -> Dict:
        """
        Belirli bir alanın doğruluk oranını hesaplar.
        
        Args:
            field_name: Alan adı
            days: Kaç günlük veriyi analiz et
            
        Returns:
            Dict: {'accuracy': 0.92, 'total_contracts': 100, 'corrections': 8}
        """
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Bu alanda düzeltme yapılan contract'lar
        corrections_count = self.db.query(Correction).filter(
            Correction.field_name == field_name,
            Correction.corrected_at >= since_date
        ).count()
        
        # Toplam işlenen contract
        total_contracts = self.db.query(Contract).filter(
            Contract.islenme_zamani >= since_date
        ).count()
        
        if total_contracts == 0:
            return {
                'accuracy': 0.0,
                'total_contracts': 0,
                'corrections': 0,
                'error_rate': 0.0
            }
        
        # Accuracy = (Doğru olanlar / Toplam) * 100
        # Doğru olanlar = Toplam - Düzeltilmesi gerekenler
        accuracy = ((total_contracts - corrections_count) / total_contracts) * 100
        
        return {
            'accuracy': round(accuracy, 2),
            'total_contracts': total_contracts,
            'corrections': corrections_count,
            'error_rate': round((corrections_count / total_contracts) * 100, 2)
        }
    
    def get_overall_accuracy(self, days: int = 30) -> Dict:
        """
        Tüm alanların genel doğruluk raporu.
        
        Returns:
            Dict: Alan bazlı accuracy map
        """
        fields = [
            'signing_party',
            'address',
            'country',
            'signed_date',
            'contract_name',
            'doc_type',
            'signature'
        ]
        
        report = {}
        
        for field in fields:
            report[field] = self.get_field_accuracy(field, days)
        
        # Genel accuracy (weighted average)
        total_contracts = sum(r['total_contracts'] for r in report.values())
        total_corrections = sum(r['corrections'] for r in report.values())
        
        if total_contracts > 0:
            overall_accuracy = ((total_contracts - total_corrections) / total_contracts) * 100
        else:
            overall_accuracy = 0.0
        
        report['overall'] = {
            'accuracy': round(overall_accuracy, 2),
            'total_contracts': total_contracts,
            'total_corrections': total_corrections
        }
        
        return report
    
    def get_common_mistakes(
        self,
        field_name: str,
        limit: int = 10,
        days: int = 30
    ) -> List[Dict]:
        """
        En sık yapılan hataları listeler.
        
        Returns:
            List[Dict]: [{'old_value': 'X', 'new_value': 'Y', 'count': 5}, ...]
        """
        since_date = datetime.utcnow() - timedelta(days=days)
        
        corrections = self.db.query(Correction).filter(
            Correction.field_name == field_name,
            Correction.corrected_at >= since_date
        ).all()
        
        # Pattern analizi
        mistake_patterns = defaultdict(int)
        
        for corr in corrections:
            # Basitleştirilmiş pattern matching
            pattern = self._identify_mistake_pattern(corr.old_value, corr.new_value)
            mistake_patterns[pattern] += 1
        
        # En yaygın pattern'leri döndür
        sorted_patterns = sorted(
            mistake_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        return [
            {'pattern': pattern, 'count': count}
            for pattern, count in sorted_patterns
        ]
    
    def _identify_mistake_pattern(self, old_value: str, new_value: str) -> str:
        """Hata pattern'ini tespit eder"""
        
        if not old_value:
            return "missing_field"
        
        old_lower = old_value.lower()
        new_lower = new_value.lower() if new_value else ""
        
        # Yaygın pattern'ler
        if 'telenity' in old_lower and 'telenity' not in new_lower:
            return "telenity_address_confusion"
        
        if len(old_value) < len(new_value) * 0.5:
            return "incomplete_extraction"
        
        if old_value == new_value:
            return "formatting_issue"
        
        # Kelime sayısı farkı
        old_words = len(old_value.split())
        new_words = len(new_value.split())
        
        if old_words < new_words * 0.5:
            return "truncated_text"
        
        return "other"
    
    def _analyze_correction_pattern(self, correction: Correction):
        """
        Düzeltmeyi analiz eder ve öğrenir.
        Tekrarlayan hatalar için ExtractionPattern kaydı oluşturur.
        """
        pattern_key = self._identify_mistake_pattern(
            correction.old_value,
            correction.new_value
        )
        
        # Bu pattern daha önce kaydedilmiş mi?
        existing_pattern = self.db.query(ExtractionPattern).filter(
            ExtractionPattern.field_name == correction.field_name,
            ExtractionPattern.pattern_type == 'mistake',
            ExtractionPattern.pattern_value == pattern_key,
            ExtractionPattern.is_active == 1
        ).first()
        
        if existing_pattern:
            # Mevcut pattern'i güncelle
            existing_pattern.failure_count += 1
            existing_pattern.last_used = datetime.utcnow()
            
            # Accuracy güncelle
            total = existing_pattern.success_count + existing_pattern.failure_count
            if total > 0:
                existing_pattern.accuracy = (existing_pattern.success_count / total) * 100
        else:
            # Yeni pattern oluştur
            new_pattern = ExtractionPattern(
                field_name=correction.field_name,
                pattern_type='mistake',
                pattern_value=pattern_key,
                failure_count=1,
                success_count=0,
                accuracy=0.0,
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow(),
                is_active=1
            )
            self.db.add(new_pattern)
        
        self.db.commit()
    
    def get_adaptive_prompt_hint(self, field_name: str) -> Optional[str]:
        """
        Belirli bir alan için adaptive prompt hint'i döndürür.
        En sık yapılan hatalara göre uyarı mesajı oluşturur.
        
        Returns:
            str: Prompt'a eklenecek uyarı metni
        """
        # Son 30 gündeki en yaygın hatalar
        common_mistakes = self.get_common_mistakes(field_name, limit=3, days=30)
        
        if not common_mistakes:
            return None
        
        # En yaygın hata pattern'i
        top_mistake = common_mistakes[0]
        
        hints = {
            'telenity_address_confusion': (
                "⚠️ CRITICAL: NEVER return Telenity's address. "
                "Only extract the COUNTERPARTY's address!"
            ),
            'incomplete_extraction': (
                "⚠️ WARNING: Extract the COMPLETE information. "
                "Don't truncate or summarize."
            ),
            'truncated_text': (
                "⚠️ Make sure to extract FULL text, not just the beginning."
            ),
            'missing_field': (
                "⚠️ This field is often empty. Look carefully in the document."
            )
        }
        
        hint = hints.get(top_mistake['pattern'])
        
        if hint and top_mistake['count'] >= 5:
            return hint
        
        return None
    
    def generate_weekly_report(self) -> str:
        """
        Haftalık accuracy raporu oluşturur.
        
        Returns:
            str: Formatted report
        """
        accuracy_report = self.get_overall_accuracy(days=7)
        
        report_lines = [
            "📊 HAFTALIK DOĞRULUK RAPORU",
            "=" * 60,
            f"Tarih: {datetime.utcnow().strftime('%Y-%m-%d')}",
            f"Dönem: Son 7 gün",
            "",
            "📈 GENEL DURUM:",
            f"  • Toplam İşlenen: {accuracy_report['overall']['total_contracts']} sözleşme",
            f"  • Toplam Düzeltme: {accuracy_report['overall']['total_corrections']}",
            f"  • Genel Doğruluk: {accuracy_report['overall']['accuracy']:.1f}%",
            "",
            "🎯 ALAN BAZLI DOĞRULUK:",
        ]
        
        # Alan bazlı
        for field, stats in accuracy_report.items():
            if field == 'overall':
                continue
            
            emoji = "✅" if stats['accuracy'] >= 90 else "⚠️" if stats['accuracy'] >= 80 else "❌"
            report_lines.append(
                f"  {emoji} {field.ljust(20)}: {stats['accuracy']:>5.1f}% "
                f"({stats['corrections']} düzeltme)"
            )
        
        # Problem alanları
        problem_fields = [
            (field, stats)
            for field, stats in accuracy_report.items()
            if field != 'overall' and stats['accuracy'] < 85
        ]
        
        if problem_fields:
            report_lines.extend([
                "",
                "⚠️ DİKKAT GEREKTİREN ALANLAR:",
            ])
            
            for field, stats in problem_fields:
                common_mistakes = self.get_common_mistakes(field, limit=2, days=7)
                report_lines.append(f"  • {field}: {stats['accuracy']:.1f}% doğruluk")
                
                if common_mistakes:
                    for mistake in common_mistakes:
                        report_lines.append(
                            f"    - {mistake['pattern']}: {mistake['count']} kez"
                        )
        
        report_lines.extend([
            "",
            "=" * 60,
            "💡 Öneriler:",
            "  1. Problem alanları için prompt optimization yapın",
            "  2. Düşük doğruluk alanlarında manuel kontrol artırın",
            "  3. Yaygın hataları known_companies.json'a ekleyin",
        ])
        
        return "\n".join(report_lines)
    
    def export_corrections_to_training_data(
        self,
        output_path: str,
        days: int = 90,
        min_corrections: int = 3
    ):
        """
        Düzeltmeleri fine-tuning için training data'ya dönüştürür.
        
        Args:
            output_path: JSON çıktı dosyası
            days: Kaç günlük veriyi al
            min_corrections: Minimum düzeltme sayısı (filtering için)
        """
        import json
        
        since_date = datetime.utcnow() - timedelta(days=days)
        
        corrections = self.db.query(Correction).filter(
            Correction.corrected_at >= since_date
        ).all()
        
        # Contract'ları grupla
        contract_corrections = defaultdict(list)
        
        for corr in corrections:
            contract_corrections[corr.contract_id].append(corr)
        
        # Training data oluştur
        training_samples = []
        
        for contract_id, corrs in contract_corrections.items():
            # Minimum düzeltme kontrolü
            if len(corrs) < min_corrections:
                continue
            
            contract = self.db.query(Contract).filter(Contract.id == contract_id).first()
            
            if not contract:
                continue
            
            # Corrected values oluştur
            corrected_data = {}
            for corr in corrs:
                corrected_data[corr.field_name] = corr.new_value
            
            sample = {
                'contract_id': contract_id,
                'filename': contract.dosya_adi,
                'corrected_fields': corrected_data,
                'correction_count': len(corrs),
                'original_confidence': corrs[0].confidence_before
            }
            
            training_samples.append(sample)
        
        # JSON'a yaz
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(training_samples, f, indent=2, ensure_ascii=False)
        
        self.logger.info(
            f"📝 Exported {len(training_samples)} training samples to {output_path}"
        )
        
        return len(training_samples)


# Convenience functions
def record_correction(contract_id: int, field: str, old: str, new: str, by: str = "user"):
    """Tek satırda düzeltme kaydı"""
    service = FeedbackService()
    return service.record_correction(contract_id, field, old, new, by)


def get_accuracy_report(days: int = 30) -> Dict:
    """Tek satırda accuracy raporu"""
    service = FeedbackService()
    return service.get_overall_accuracy(days)


def generate_weekly_report() -> str:
    """Tek satırda haftalık rapor"""
    service = FeedbackService()
    return service.generate_weekly_report()


if __name__ == "__main__":
    # Test
    print("🧪 Feedback Service Test\n")
    
    service = FeedbackService()
    
    # Accuracy raporu
    report = service.get_overall_accuracy(days=30)
    
    print("📊 Son 30 Günlük Doğruluk:")
    print(f"  Genel: {report['overall']['accuracy']:.1f}%")
    print(f"  Toplam: {report['overall']['total_contracts']} sözleşme")
    print()
    
    for field, stats in report.items():
        if field != 'overall':
            print(f"  {field}: {stats['accuracy']:.1f}%")
    
    print("\n" + "=" * 60)
    print("\n📝 Haftalık Rapor:\n")
    print(service.generate_weekly_report())
