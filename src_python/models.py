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
