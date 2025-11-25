"""
Smart File Renamer Module
Automatically renames contract files to standard format: [TYPE]_[COMPANY]_[DATE].pdf
"""

import os
import re
from datetime import datetime
from typing import Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

from logger import logger
from config import DOC_TYPE_CHOICES
from utils import extract_date_from_filename, extract_company_from_filename


@dataclass
class RenameResult:
    """Yeniden adlandırma sonucu"""
    success: bool
    old_name: str
    new_name: str
    reason: str


class SmartFileRenamer:
    """
    Sözleşme dosyalarını akıllı şekilde yeniden adlandırır.
    
    Standard Format: [CONTRACT_TYPE]_[COMPANY_NAME]_[YYYY-MM-DD].pdf
    
    Örnek:
        - "nda document.pdf" → "NDA_CompanyA_2023-01-15.pdf"
        - "msa signed 15.01.2023.pdf" → "MSA_CompanyB_2023-01-15.pdf"
    """
    
    # Contract type pattern mapping
    CONTRACT_PATTERNS = {
        'NDA': [
            r'\bnda\b',
            r'non.?disclosure',
            r'confidentiality\s+agreement',
            r'secrecy\s+agreement'
        ],
        'MSA': [
            r'\bmsa\b',
            r'master\s+service',
            r'framework\s+agreement'
        ],
        'SOW': [
            r'\bsow\b',
            r'statement\s+of\s+work',
            r'scope\s+of\s+work'
        ],
        'SLA': [
            r'\bsla\b',
            r'service\s+level',
            r'level\s+agreement'
        ],
        'PO': [
            r'\bpo\b',
            r'purchase\s+order',
            r'order\s+form'
        ],
        'Consultancy Agreement': [
            r'consultanc[yi]',
            r'consultant\s+agreement',
            r'advisory\s+agreement'
        ],
        'Reseller Agreement': [
            r'reseller',
            r're.?seller',
            r'distribution\s+agreement'
        ],
        'Agency Agreement': [
            r'agency\s+agreement',
            r'agent\s+agreement',
            r'\bagent\b'
        ],
        'EULA': [
            r'\beula\b',
            r'end\s+user\s+license',
            r'software\s+license'
        ],
        'DPA': [
            r'\bdpa\b',
            r'data\s+processing',
            r'privacy\s+agreement'
        ]
    }
    
    # Stopwords - dosya adından çıkarılacak kelimeler
    STOPWORDS = [
        'signed', 'clean', 'copy', 'final', 'draft', 'version',
        'v1', 'v2', 'v3', 'rev', 'revision', 'scan', 'scanned',
        'executed', 'original', 'document', 'agreement', 'contract',
        'telenity', 'fze', 'inc', 'ltd', 'llc', 'corp', 'pvt'
    ]
    
    def __init__(self):
        self.logger = logger
    
    def suggest_rename(
        self,
        filepath: str,
        extracted_data: Optional[Dict] = None,
        folder_name: Optional[str] = None
    ) -> str:
        """
        Dosya için yeni isim önerir.
        
        Args:
            filepath: Mevcut dosya yolu
            extracted_data: LLM'den çıkarılan veri (opsiyonel)
            folder_name: Klasör adı (şirket adı için fallback)
            
        Returns:
            str: Önerilen yeni dosya adı
        """
        filename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(filename)[0]
        
        # 1. CONTRACT TYPE BELİRLE
        contract_type = self._detect_contract_type(
            filename,
            extracted_data.get('doc_type') if extracted_data else None
        )
        
        # 2. COMPANY NAME BELİRLE
        company_name = self._extract_company_name(
            name_without_ext,
            extracted_data.get('signing_party') if extracted_data else None,
            folder_name
        )
        
        # 3. DATE BELİRLE
        date_str = self._extract_date(
            name_without_ext,
            extracted_data.get('signed_date') if extracted_data else None
        )
        
        # 4. YENİ İSİM OLUŞTUR
        new_name = self._build_filename(contract_type, company_name, date_str)
        
        return new_name
    
    def _detect_contract_type(self, filename: str, extracted_type: Optional[str] = None) -> str:
        """Contract type'ı tespit eder"""
        
        # Önce extracted data'ya bak
        if extracted_type and extracted_type in DOC_TYPE_CHOICES:
            return self._normalize_contract_type(extracted_type)
        
        # Dosya adından pattern matching
        filename_lower = filename.lower()
        
        for contract_type, patterns in self.CONTRACT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    return self._normalize_contract_type(contract_type)
        
        # Default
        return "Agreement"
    
    def _normalize_contract_type(self, contract_type: str) -> str:
        """Contract type'ı standardize eder"""
        # Kısaltmalar uppercase
        if len(contract_type) <= 4:
            return contract_type.upper()
        
        # Uzun isimler title case
        return contract_type.replace(' ', '_').title()
    
    def _extract_company_name(
        self,
        filename: str,
        extracted_party: Optional[str] = None,
        folder_name: Optional[str] = None
    ) -> str:
        """Şirket adını çıkarır"""
        
        # 1. Extracted data'dan al
        if extracted_party:
            return self._clean_company_name(extracted_party)
        
        # 2. Folder name'den al
        if folder_name:
            return self._clean_company_name(folder_name)
        
        # 3. Dosya adından parse et
        parsed_company = extract_company_from_filename(filename)
        if parsed_company:
            return self._clean_company_name(parsed_company)
        
        # 4. Default
        return "Unknown"
    
    def _clean_company_name(self, company_name: str) -> str:
        """Şirket adını temizler ve standardize eder"""
        if not company_name:
            return "Unknown"
        
        # Özel karakterleri temizle
        cleaned = re.sub(r'[^\w\s-]', '', company_name)
        
        # Stopwords'leri çıkar
        words = cleaned.split()
        words = [w for w in words if w.lower() not in self.STOPWORDS]
        
        # Boşlukları underscore'a çevir
        cleaned = '_'.join(words)
        
        # Telenity kelimesini çıkar
        cleaned = re.sub(r'(?i)telenity', '', cleaned)
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        
        # İlk 30 karakter (çok uzun olmasın)
        if len(cleaned) > 30:
            cleaned = cleaned[:30]
        
        return cleaned if cleaned else "Unknown"
    
    def _extract_date(self, filename: str, extracted_date: Optional[str] = None) -> str:
        """Tarih bilgisini çıkarır"""
        
        # 1. Extracted data'dan al (öncelikli)
        if extracted_date:
            # Format kontrolü
            if self._validate_date_format(extracted_date):
                return extracted_date
        
        # 2. Dosya adından parse et
        parsed_date = extract_date_from_filename(filename)
        if parsed_date:
            return parsed_date
        
        # 3. Default: Bugünün tarihi (son çare)
        return datetime.now().strftime('%Y-%m-%d')
    
    def _validate_date_format(self, date_str: str) -> bool:
        """Tarih formatını kontrol eder (YYYY-MM-DD)"""
        if not date_str:
            return False
        
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except:
            return False
    
    def _build_filename(self, contract_type: str, company: str, date: str) -> str:
        """Final dosya adını oluşturur"""
        
        # Parçaları birleştir
        parts = [contract_type, company, date]
        
        # Boş parçaları çıkar
        parts = [p for p in parts if p and p != "Unknown"]
        
        # Birleştir
        filename = "_".join(parts)
        
        # Güvenli karakter kontrolü
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        
        # PDF uzantısı ekle
        filename += ".pdf"
        
        return filename
    
    def rename_file(
        self,
        filepath: str,
        new_name: str,
        dry_run: bool = False
    ) -> RenameResult:
        """
        Dosyayı yeniden adlandırır.
        
        Args:
            filepath: Mevcut dosya yolu
            new_name: Yeni dosya adı
            dry_run: True ise sadece simülasyon (dosya değişmez)
            
        Returns:
            RenameResult: Yeniden adlandırma sonucu
        """
        old_name = os.path.basename(filepath)
        
        # Aynı isim kontrolü
        if old_name == new_name:
            return RenameResult(
                success=False,
                old_name=old_name,
                new_name=new_name,
                reason="Aynı isim - değişiklik gerekli değil"
            )
        
        # Yeni path oluştur
        directory = os.path.dirname(filepath)
        new_path = os.path.join(directory, new_name)
        
        # Çakışma kontrolü
        if os.path.exists(new_path):
            # Versiyon ekle
            base, ext = os.path.splitext(new_name)
            counter = 1
            while os.path.exists(new_path):
                new_name = f"{base}_v{counter}{ext}"
                new_path = os.path.join(directory, new_name)
                counter += 1
        
        # Dry run kontrolü
        if dry_run:
            return RenameResult(
                success=True,
                old_name=old_name,
                new_name=new_name,
                reason="[DRY RUN] Başarılı - dosya değiştirilmedi"
            )
        
        # Dosyayı yeniden adlandır
        try:
            os.rename(filepath, new_path)
            self.logger.info(f"Renamed: {old_name} → {new_name}")
            
            return RenameResult(
                success=True,
                old_name=old_name,
                new_name=new_name,
                reason="Başarıyla yeniden adlandırıldı"
            )
        
        except Exception as e:
            self.logger.error(f"Rename error: {e}")
            return RenameResult(
                success=False,
                old_name=old_name,
                new_name=new_name,
                reason=f"Hata: {str(e)}"
            )
    
    def bulk_rename(
        self,
        folder_path: str,
        dry_run: bool = True,
        recursive: bool = True
    ) -> Dict[str, list]:
        """
        Klasördeki tüm PDF'leri toplu yeniden adlandırır.
        
        Args:
            folder_path: Klasör yolu
            dry_run: True ise simülasyon modu
            recursive: Alt klasörlere de uygulanır
            
        Returns:
            Dict: {'renamed': [...], 'skipped': [...], 'errors': [...]}
        """
        results = {
            'renamed': [],
            'skipped': [],
            'errors': []
        }
        
        # PDF dosyalarını topla
        pdf_files = []
        
        if recursive:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        pdf_files.append(os.path.join(root, file))
        else:
            pdf_files = [
                os.path.join(folder_path, f)
                for f in os.listdir(folder_path)
                if f.lower().endswith('.pdf')
            ]
        
        self.logger.info(f"🔍 {len(pdf_files)} PDF bulundu")
        
        # Her dosyayı işle
        for filepath in pdf_files:
            try:
                # Folder name'i al (şirket adı için)
                folder_name = os.path.basename(os.path.dirname(filepath))
                
                # Yeni isim öner
                new_name = self.suggest_rename(
                    filepath,
                    extracted_data=None,
                    folder_name=folder_name
                )
                
                # Rename
                result = self.rename_file(filepath, new_name, dry_run=dry_run)
                
                if result.success:
                    if result.reason.startswith("[DRY RUN]") or "Aynı isim" in result.reason:
                        results['skipped'].append(result)
                    else:
                        results['renamed'].append(result)
                else:
                    if "Aynı isim" in result.reason:
                        results['skipped'].append(result)
                    else:
                        results['errors'].append(result)
            
            except Exception as e:
                self.logger.error(f"Bulk rename error for {filepath}: {e}")
                results['errors'].append(
                    RenameResult(
                        success=False,
                        old_name=os.path.basename(filepath),
                        new_name="",
                        reason=str(e)
                    )
                )
        
        return results


# Convenience functions
def suggest_filename(filepath: str, extracted_data: Dict = None) -> str:
    """Tek satırda dosya adı önerisi"""
    renamer = SmartFileRenamer()
    return renamer.suggest_rename(filepath, extracted_data)


def bulk_rename_folder(folder_path: str, dry_run: bool = True):
    """Tek satırda toplu yeniden adlandırma"""
    renamer = SmartFileRenamer()
    return renamer.bulk_rename(folder_path, dry_run)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Kullanım:")
        print("  python file_renamer.py <folder_path> [--apply]")
        print("\nÖrnekler:")
        print("  python file_renamer.py ./contracts/        # Dry run (önizleme)")
        print("  python file_renamer.py ./contracts/ --apply # Gerçek yeniden adlandırma")
        sys.exit(1)
    
    folder = sys.argv[1]
    apply_changes = '--apply' in sys.argv
    
    print("📁 Toplu Dosya Yeniden Adlandırma")
    print("=" * 60)
    print(f"Klasör: {folder}")
    print(f"Mod: {'UYGULA' if apply_changes else 'DRY RUN (Önizleme)'}")
    print()
    
    results = bulk_rename_folder(folder, dry_run=not apply_changes)
    
    # Sonuçları göster
    print("\n✅ Yeniden Adlandırılacak:")
    for r in results['renamed'][:10]:  # İlk 10
        print(f"  {r.old_name} → {r.new_name}")
    if len(results['renamed']) > 10:
        print(f"  ... ve {len(results['renamed']) - 10} dosya daha")
    
    print(f"\n⏭️ Atlanan: {len(results['skipped'])} dosya")
    
    if results['errors']:
        print(f"\n❌ Hatalar: {len(results['errors'])} dosya")
        for r in results['errors'][:5]:
            print(f"  {r.old_name}: {r.reason}")
    
    print("\n" + "=" * 60)
    print(f"📊 Toplam: {len(results['renamed'])} renamed, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    
    if not apply_changes:
        print("\n💡 Değişiklikleri uygulamak için: --apply parametresi ekleyin")
