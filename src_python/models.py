# src_python/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from datetime import datetime
from database import Base # Base artık database.py'dan geliyor

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="PENDING") 
    progress = Column(Float, default=0.0)
    message = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    estimated_remaining_seconds = Column(Float, default=0.0)

class Contract(Base):
    __tablename__ = "contracts"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("analysis_jobs.id"), nullable=True)
    
    dosya_adi = Column(String, index=True)
    contract_name = Column(String, nullable=True)
    doc_type = Column(String, nullable=True)
    
    # Parties
    company_type = Column(String, nullable=True)
    signing_party = Column(String, nullable=True)
    country = Column(String, nullable=True)
    address = Column(String, nullable=True)
    
    # Telenity
    telenity_entity = Column(String, nullable=True)
    telenity_fullname = Column(String, nullable=True)
    
    # Details
    signature = Column(String, nullable=True)
    signed_date = Column(String, nullable=True)
    
    # Metadata
    file_hash = Column(String, index=True, nullable=True)
    durum_notu = Column(String, nullable=True)
    islenme_zamani = Column(DateTime, default=datetime.utcnow)
    
    # Yeni Eklenen
    confidence_score = Column(Integer, default=0)
    
    # Quality Assurance fields
    needs_review = Column(Integer, default=0)  # Boolean: 0=no, 1=yes
    review_reason = Column(Text, nullable=True)
    review_status = Column(String, default="pending")  # pending, approved, rejected, corrected
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    validation_issues = Column(Integer, default=0)
    validation_warnings = Column(Integer, default=0)


class Correction(Base):
    """Manuel düzeltme kayıtları - Feedback loop için"""
    __tablename__ = "corrections"
    
    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False, index=True)
    
    # Düzeltilen alan
    field_name = Column(String, nullable=False, index=True)  # 'address', 'signing_party', etc.
    
    # Değerler
    old_value = Column(Text, nullable=True)  # AI'ın çıkardığı değer
    new_value = Column(Text, nullable=False)  # Kullanıcının düzelttiği değer
    
    # Kim düzeltti?
    corrected_by = Column(String, nullable=True)  # user email/name
    
    # Ne zaman?
    corrected_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Ek bilgi
    correction_reason = Column(String, nullable=True)  # Neden düzeltildi?
    confidence_before = Column(Integer, nullable=True)  # Düzeltmeden önceki confidence


class ExtractionPattern(Base):
    """Öğrenilen extraction pattern'leri - Adaptive learning için"""
    __tablename__ = "extraction_patterns"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Pattern bilgisi
    field_name = Column(String, nullable=False, index=True)
    pattern_type = Column(String, nullable=False)  # 'regex', 'keyword', 'ml_rule'
    pattern_value = Column(Text, nullable=False)  # Actual pattern
    
    # Performans
    success_count = Column(Integer, default=0)  # Kaç kez doğru sonuç verdi
    failure_count = Column(Integer, default=0)  # Kaç kez yanlış
    accuracy = Column(Float, default=0.0)  # Calculated accuracy
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)  # SQLite için Boolean yerine Integer
    
    # Hangi şirket için etkili?
    applicable_to = Column(String, nullable=True)  # Company pattern (optional)


class AuditLog(Base):
    """Audit log for all system actions and data changes"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # What happened
    action_type = Column(String, nullable=False, index=True)  # 'process', 'review', 'correct', 'export', 'delete'
    entity_type = Column(String, nullable=False)  # 'contract', 'job', 'user'
    entity_id = Column(Integer, nullable=True, index=True)  # ID of affected entity
    
    # Who did it
    user_id = Column(String, nullable=True, index=True)  # User identifier
    ip_address = Column(String, nullable=True)
    
    # Details
    action_details = Column(Text, nullable=True)  # JSON with details
    old_values = Column(Text, nullable=True)  # JSON with old values (for updates)
    new_values = Column(Text, nullable=True)  # JSON with new values
    
    # Status
    status = Column(String, default="success")  # success, failed, warning
    error_message = Column(Text, nullable=True)
    
    # When
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Metadata
    session_id = Column(String, nullable=True)  # Track user sessions
    duration_ms = Column(Integer, nullable=True)  # Action duration


class ExportVersion(Base):
    """Track export versions for duplicate detection and rollback"""
    __tablename__ = "export_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Export info
    version_number = Column(Integer, nullable=False)
    export_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)
    
    # Content
    total_records = Column(Integer, default=0)
    record_hashes = Column(Text, nullable=True)  # JSON array of contract hashes
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
