"""
Automated folder structure organization for processed contracts.
Organizes files by contract type, date, company, etc.
"""

import os
import shutil
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from logger import logger


class FolderOrganizer:
    """Organize processed contracts into structured folders."""
    
    def __init__(self, base_output_dir: str = "organized_contracts"):
        self.base_output_dir = base_output_dir
        self.logger = logger
        
        # Create base directory
        os.makedirs(base_output_dir, exist_ok=True)
    
    def organize_by_contract_type(
        self,
        contracts: List[Dict],
        source_folder: str
    ) -> Dict[str, List[str]]:
        """
        Organize contracts by contract type.
        
        Structure:
            organized_contracts/
                ├── Service_Agreements/
                ├── NDAs/
                ├── Purchase_Orders/
                └── Other/
        
        Returns:
            Dict mapping contract_type -> list of moved files
        """
        organized = {}
        
        for contract in contracts:
            contract_type = contract.get('contract_name', 'Other')
            filename = contract.get('dosya_adi', '')
            
            if not filename:
                continue
            
            # Sanitize contract type for folder name
            folder_name = self._sanitize_folder_name(contract_type)
            
            # Create subfolder
            type_folder = os.path.join(self.base_output_dir, folder_name)
            os.makedirs(type_folder, exist_ok=True)
            
            # Move file
            source_path = os.path.join(source_folder, filename)
            dest_path = os.path.join(type_folder, filename)
            
            try:
                if os.path.exists(source_path):
                    shutil.copy2(source_path, dest_path)
                    
                    if folder_name not in organized:
                        organized[folder_name] = []
                    organized[folder_name].append(filename)
                    
                    self.logger.debug(f"Organized: {filename} -> {folder_name}/")
            except Exception as e:
                self.logger.error(f"Failed to organize {filename}: {e}")
        
        self.logger.info(
            f"Organized {sum(len(v) for v in organized.values())} files "
            f"into {len(organized)} folders"
        )
        
        return organized
    
    def organize_by_company(
        self,
        contracts: List[Dict],
        source_folder: str
    ) -> Dict[str, List[str]]:
        """
        Organize contracts by signing party (company).
        
        Structure:
            organized_contracts/
                ├── Acme_Corp/
                ├── Nokia/
                └── Unknown/
        """
        organized = {}
        
        for contract in contracts:
            company = contract.get('signing_party', 'Unknown')
            filename = contract.get('dosya_adi', '')
            
            if not filename:
                continue
            
            # Sanitize company name
            folder_name = self._sanitize_folder_name(company)
            
            # Create subfolder
            company_folder = os.path.join(self.base_output_dir, folder_name)
            os.makedirs(company_folder, exist_ok=True)
            
            # Move file
            source_path = os.path.join(source_folder, filename)
            dest_path = os.path.join(company_folder, filename)
            
            try:
                if os.path.exists(source_path):
                    shutil.copy2(source_path, dest_path)
                    
                    if folder_name not in organized:
                        organized[folder_name] = []
                    organized[folder_name].append(filename)
            except Exception as e:
                self.logger.error(f"Failed to organize {filename}: {e}")
        
        return organized
    
    def organize_by_date(
        self,
        contracts: List[Dict],
        source_folder: str,
        date_format: str = "year_month"  # "year", "year_month", "year_month_day"
    ) -> Dict[str, List[str]]:
        """
        Organize contracts by signed date.
        
        Structure (year_month):
            organized_contracts/
                ├── 2024/
                │   ├── 01_January/
                │   ├── 02_February/
                │   └── ...
                └── 2025/
                    ├── 01_January/
                    └── ...
        """
        organized = {}
        
        for contract in contracts:
            signed_date = contract.get('signed_date', '')
            filename = contract.get('dosya_adi', '')
            
            if not filename:
                continue
            
            # Parse date
            try:
                date_obj = datetime.strptime(signed_date, '%Y-%m-%d')
            except (ValueError, TypeError):
                date_obj = None
            
            # Create folder path based on date
            if date_obj:
                if date_format == "year":
                    folder_path = str(date_obj.year)
                elif date_format == "year_month":
                    folder_path = os.path.join(
                        str(date_obj.year),
                        f"{date_obj.month:02d}_{date_obj.strftime('%B')}"
                    )
                else:  # year_month_day
                    folder_path = os.path.join(
                        str(date_obj.year),
                        f"{date_obj.month:02d}_{date_obj.strftime('%B')}",
                        f"{date_obj.day:02d}"
                    )
            else:
                folder_path = "Unknown_Date"
            
            # Create subfolder
            date_folder = os.path.join(self.base_output_dir, folder_path)
            os.makedirs(date_folder, exist_ok=True)
            
            # Move file
            source_path = os.path.join(source_folder, filename)
            dest_path = os.path.join(date_folder, filename)
            
            try:
                if os.path.exists(source_path):
                    shutil.copy2(source_path, dest_path)
                    
                    if folder_path not in organized:
                        organized[folder_path] = []
                    organized[folder_path].append(filename)
            except Exception as e:
                self.logger.error(f"Failed to organize {filename}: {e}")
        
        return organized
    
    def organize_hierarchical(
        self,
        contracts: List[Dict],
        source_folder: str
    ) -> Dict[str, List[str]]:
        """
        Organize contracts in hierarchical structure.
        
        Structure:
            organized_contracts/
                ├── 2024/
                │   ├── Acme_Corp/
                │   │   ├── Service_Agreement/
                │   │   │   └── contract1.pdf
                │   │   └── NDA/
                │   └── Nokia/
                └── 2025/
        """
        organized = {}
        
        for contract in contracts:
            # Extract info
            signed_date = contract.get('signed_date', '')
            company = contract.get('signing_party', 'Unknown')
            contract_type = contract.get('contract_name', 'Other')
            filename = contract.get('dosya_adi', '')
            
            if not filename:
                continue
            
            # Parse year
            try:
                year = datetime.strptime(signed_date, '%Y-%m-%d').year
            except (ValueError, TypeError):
                year = "Unknown_Year"
            
            # Build hierarchical path: Year/Company/Type/
            folder_path = os.path.join(
                str(year),
                self._sanitize_folder_name(company),
                self._sanitize_folder_name(contract_type)
            )
            
            # Create subfolder
            full_folder = os.path.join(self.base_output_dir, folder_path)
            os.makedirs(full_folder, exist_ok=True)
            
            # Move file
            source_path = os.path.join(source_folder, filename)
            dest_path = os.path.join(full_folder, filename)
            
            try:
                if os.path.exists(source_path):
                    shutil.copy2(source_path, dest_path)
                    
                    if folder_path not in organized:
                        organized[folder_path] = []
                    organized[folder_path].append(filename)
            except Exception as e:
                self.logger.error(f"Failed to organize {filename}: {e}")
        
        return organized
    
    def organize_by_confidence(
        self,
        contracts: List[Dict],
        source_folder: str,
        thresholds: Dict[str, Tuple[int, int]] = None
    ) -> Dict[str, List[str]]:
        """
        Organize contracts by confidence score.
        
        Structure:
            organized_contracts/
                ├── High_Confidence_90plus/
                ├── Medium_Confidence_70_89/
                ├── Low_Confidence_50_69/
                └── Very_Low_Confidence_below50/
        """
        if thresholds is None:
            thresholds = {
                'High_Confidence_90plus': (90, 100),
                'Medium_Confidence_70_89': (70, 89),
                'Low_Confidence_50_69': (50, 69),
                'Very_Low_Confidence_below50': (0, 49)
            }
        
        organized = {}
        
        for contract in contracts:
            confidence = contract.get('confidence_score', 0)
            filename = contract.get('dosya_adi', '')
            
            if not filename:
                continue
            
            # Determine confidence bucket
            folder_name = 'Unknown_Confidence'
            for bucket, (min_conf, max_conf) in thresholds.items():
                if min_conf <= confidence <= max_conf:
                    folder_name = bucket
                    break
            
            # Create subfolder
            conf_folder = os.path.join(self.base_output_dir, folder_name)
            os.makedirs(conf_folder, exist_ok=True)
            
            # Move file
            source_path = os.path.join(source_folder, filename)
            dest_path = os.path.join(conf_folder, filename)
            
            try:
                if os.path.exists(source_path):
                    shutil.copy2(source_path, dest_path)
                    
                    if folder_name not in organized:
                        organized[folder_name] = []
                    organized[folder_name].append(filename)
            except Exception as e:
                self.logger.error(f"Failed to organize {filename}: {e}")
        
        return organized
    
    def create_summary_report(
        self,
        organized: Dict[str, List[str]],
        output_file: str = "organization_report.txt"
    ):
        """Create a text report of the organization."""
        report_path = os.path.join(self.base_output_dir, output_file)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("CONTRACT ORGANIZATION REPORT\n")
            f.write("=" * 60 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Folders: {len(organized)}\n")
            f.write(f"Total Files: {sum(len(v) for v in organized.values())}\n")
            f.write("\n" + "=" * 60 + "\n\n")
            
            for folder, files in sorted(organized.items()):
                f.write(f"📁 {folder}/ ({len(files)} files)\n")
                for filename in sorted(files):
                    f.write(f"   └── {filename}\n")
                f.write("\n")
        
        self.logger.info(f"Organization report saved: {report_path}")
    
    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize string for use as folder name."""
        if not name or name.strip() == '':
            return 'Unknown'
        
        # Remove invalid characters
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        
        # Replace spaces with underscores
        name = name.strip().replace(' ', '_')
        
        # Remove multiple underscores
        name = re.sub(r'_+', '_', name)
        
        # Limit length
        if len(name) > 50:
            name = name[:50]
        
        return name


# Convenience functions
def organize_contracts(
    contracts: List[Dict],
    source_folder: str,
    method: str = "hierarchical",
    output_dir: str = "organized_contracts"
) -> Dict[str, List[str]]:
    """
    Organize contracts using specified method.
    
    Args:
        contracts: List of contract dictionaries
        source_folder: Source folder with PDF files
        method: Organization method:
            - "type": By contract type
            - "company": By signing party
            - "date": By signed date
            - "confidence": By confidence score
            - "hierarchical": Year/Company/Type structure
        output_dir: Output directory for organized files
    
    Returns:
        Dict mapping folder paths to file lists
    """
    organizer = FolderOrganizer(output_dir)
    
    if method == "type":
        result = organizer.organize_by_contract_type(contracts, source_folder)
    elif method == "company":
        result = organizer.organize_by_company(contracts, source_folder)
    elif method == "date":
        result = organizer.organize_by_date(contracts, source_folder)
    elif method == "confidence":
        result = organizer.organize_by_confidence(contracts, source_folder)
    elif method == "hierarchical":
        result = organizer.organize_hierarchical(contracts, source_folder)
    else:
        logger.error(f"Unknown organization method: {method}")
        return {}
    
    # Create summary report
    organizer.create_summary_report(result)
    
    logger.info(f"✅ Organization complete: {len(result)} folders created")
    
    return result


# Example usage
if __name__ == "__main__":
    # Example contracts
    contracts = [
        {
            'dosya_adi': 'contract1.pdf',
            'contract_name': 'Service Agreement',
            'signing_party': 'Acme Corp',
            'signed_date': '2024-05-15',
            'confidence_score': 92
        },
        {
            'dosya_adi': 'contract2.pdf',
            'contract_name': 'NDA',
            'signing_party': 'Nokia',
            'signed_date': '2024-06-20',
            'confidence_score': 78
        },
        {
            'dosya_adi': 'contract3.pdf',
            'contract_name': 'Service Agreement',
            'signing_party': 'Acme Corp',
            'signed_date': '2025-01-10',
            'confidence_score': 95
        }
    ]
    
    # Organize hierarchically
    result = organize_contracts(
        contracts,
        source_folder="input_pdfs",
        method="hierarchical",
        output_dir="organized_contracts"
    )
    
    print(f"\n✅ Organized {sum(len(v) for v in result.values())} files")
    print(f"📊 Created {len(result)} folders")
