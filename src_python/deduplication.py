"""
Deduplication and export version control service.
"""

import os
import json
import hashlib
from typing import List, Dict, Tuple, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from models import Contract, ExportVersion
from logger import logger


class DeduplicationService:
    """Service for detecting and handling duplicate contracts."""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = logger
    
    def calculate_content_hash(self, contract: Dict) -> str:
        """
        Calculate a hash of contract content for duplicate detection.
        
        Uses key fields to generate hash:
        - signing_party
        - signed_date
        - contract_name
        - address (first 50 chars)
        """
        # Normalize and concatenate key fields
        content_parts = [
            str(contract.get('signing_party', '')).lower().strip(),
            str(contract.get('signed_date', '')).strip(),
            str(contract.get('contract_name', '')).lower().strip(),
            str(contract.get('address', ''))[:50].lower().strip()
        ]
        
        content_string = '|'.join(content_parts)
        
        # Calculate SHA-256 hash
        content_hash = hashlib.sha256(content_string.encode('utf-8')).hexdigest()[:16]
        
        return content_hash
    
    def find_duplicates(self, new_contracts: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Find duplicates among new contracts and existing database records.
        
        Args:
            new_contracts: List of new contract dictionaries
        
        Returns:
            Tuple of (unique_contracts, duplicate_contracts)
        """
        unique = []
        duplicates = []
        
        # Get existing hashes from database
        existing_hashes = set()
        existing_contracts = self.db.query(Contract).all()
        
        for contract in existing_contracts:
            if contract.file_hash:
                existing_hashes.add(contract.file_hash)
        
        # Check new contracts
        seen_in_batch = set()
        
        for contract in new_contracts:
            # Use file_hash if available, otherwise calculate content hash
            if 'file_hash' in contract and contract['file_hash']:
                contract_hash = contract['file_hash']
            else:
                contract_hash = self.calculate_content_hash(contract)
                contract['file_hash'] = contract_hash
            
            # Check for duplicates
            if contract_hash in existing_hashes or contract_hash in seen_in_batch:
                duplicates.append(contract)
                self.logger.warning(
                    f"Duplicate detected: {contract.get('dosya_adi', 'unknown')} "
                    f"(hash: {contract_hash[:8]}...)"
                )
            else:
                unique.append(contract)
                seen_in_batch.add(contract_hash)
        
        self.logger.info(
            f"Deduplication: {len(unique)} unique, {len(duplicates)} duplicates "
            f"out of {len(new_contracts)} total"
        )
        
        return unique, duplicates
    
    def merge_duplicate_info(
        self,
        existing_contract: Contract,
        new_data: Dict
    ) -> Contract:
        """
        Merge information from duplicate detection.
        
        Updates existing contract with better confidence data if available.
        """
        # If new confidence is higher, update fields
        new_confidence = new_data.get('confidence_score', 0)
        old_confidence = existing_contract.confidence_score or 0
        
        if new_confidence > old_confidence:
            self.logger.info(
                f"Updating {existing_contract.dosya_adi} with higher confidence data "
                f"({old_confidence}% -> {new_confidence}%)"
            )
            
            # Update fields
            for field in ['signing_party', 'address', 'country', 'signed_date', 'contract_name']:
                if field in new_data and new_data[field]:
                    setattr(existing_contract, field, new_data[field])
            
            existing_contract.confidence_score = new_confidence
            self.db.commit()
        
        return existing_contract
    
    def resolve_conflicts(
        self,
        conflicts: List[Tuple[Contract, Dict]]
    ) -> List[Contract]:
        """
        Resolve conflicts between existing and new contracts.
        
        Args:
            conflicts: List of (existing_contract, new_data) tuples
        
        Returns:
            List of resolved contracts
        """
        resolved = []
        
        for existing, new_data in conflicts:
            # Strategy: Keep higher confidence version
            resolved_contract = self.merge_duplicate_info(existing, new_data)
            resolved.append(resolved_contract)
        
        return resolved


class ExportVersionControl:
    """Version control for exports."""
    
    def __init__(self, db: Session):
        self.db = db
        self.logger = logger
    
    def create_export_version(
        self,
        export_path: str,
        contracts: List[Contract],
        created_by: str = "system",
        notes: Optional[str] = None
    ) -> ExportVersion:
        """
        Create a new export version record.
        
        Args:
            export_path: Path to exported file
            contracts: List of contracts included in export
            created_by: User who created the export
            notes: Optional notes about this export
        
        Returns:
            ExportVersion object
        """
        # Calculate next version number
        latest_version = self.db.query(ExportVersion).order_by(
            ExportVersion.version_number.desc()
        ).first()
        
        next_version = (latest_version.version_number + 1) if latest_version else 1
        
        # Calculate file hash
        file_hash = self._calculate_file_hash(export_path)
        
        # Get contract hashes
        record_hashes = [c.file_hash for c in contracts if c.file_hash]
        
        # Create version record
        version = ExportVersion(
            version_number=next_version,
            export_path=export_path,
            file_hash=file_hash,
            total_records=len(contracts),
            record_hashes=json.dumps(record_hashes),
            created_at=datetime.utcnow(),
            created_by=created_by,
            notes=notes
        )
        
        self.db.add(version)
        self.db.commit()
        
        self.logger.info(
            f"Created export version {next_version}: {export_path} "
            f"({len(contracts)} records)"
        )
        
        return version
    
    def get_export_history(self, limit: int = 10) -> List[Dict]:
        """
        Get export version history.
        
        Returns:
            List of export version dictionaries
        """
        versions = self.db.query(ExportVersion).order_by(
            ExportVersion.created_at.desc()
        ).limit(limit).all()
        
        return [
            {
                "version": v.version_number,
                "path": v.export_path,
                "total_records": v.total_records,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by,
                "notes": v.notes
            }
            for v in versions
        ]
    
    def compare_versions(
        self,
        version1: int,
        version2: int
    ) -> Dict:
        """
        Compare two export versions.
        
        Returns:
            Dictionary with comparison results
        """
        v1 = self.db.query(ExportVersion).filter(
            ExportVersion.version_number == version1
        ).first()
        v2 = self.db.query(ExportVersion).filter(
            ExportVersion.version_number == version2
        ).first()
        
        if not v1 or not v2:
            return {"error": "Version not found"}
        
        # Parse record hashes
        hashes1 = set(json.loads(v1.record_hashes) if v1.record_hashes else [])
        hashes2 = set(json.loads(v2.record_hashes) if v2.record_hashes else [])
        
        # Calculate differences
        added = hashes2 - hashes1
        removed = hashes1 - hashes2
        unchanged = hashes1 & hashes2
        
        return {
            "version1": version1,
            "version2": version2,
            "total_v1": len(hashes1),
            "total_v2": len(hashes2),
            "added_count": len(added),
            "removed_count": len(removed),
            "unchanged_count": len(unchanged),
            "change_percentage": (len(added) + len(removed)) / max(len(hashes1), 1) * 100
        }
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of export file."""
        if not os.path.exists(file_path):
            return ""
        
        sha256 = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()[:16]
        except Exception as e:
            self.logger.error(f"Failed to hash file {file_path}: {e}")
            return ""
    
    def rollback_to_version(self, version_number: int) -> Optional[str]:
        """
        Get path to a specific export version for rollback.
        
        Returns:
            Export file path if found, None otherwise
        """
        version = self.db.query(ExportVersion).filter(
            ExportVersion.version_number == version_number
        ).first()
        
        if not version:
            self.logger.error(f"Version {version_number} not found")
            return None
        
        if not os.path.exists(version.export_path):
            self.logger.error(f"Export file not found: {version.export_path}")
            return None
        
        self.logger.info(f"Rolling back to version {version_number}: {version.export_path}")
        return version.export_path


# Convenience functions
def deduplicate_contracts(db: Session, contracts: List[Dict]) -> List[Dict]:
    """
    Remove duplicates from contract list.
    
    Returns:
        List of unique contracts
    """
    service = DeduplicationService(db)
    unique, _ = service.find_duplicates(contracts)
    return unique


def track_export(
    db: Session,
    export_path: str,
    contracts: List[Contract],
    user: str = "system"
) -> ExportVersion:
    """
    Create export version tracking record.
    
    Returns:
        ExportVersion object
    """
    service = ExportVersionControl(db)
    return service.create_export_version(export_path, contracts, user)
