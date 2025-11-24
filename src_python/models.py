from sqlalchemy import Column, Integer, String, Text, DateTime, func, ForeignKey
from database import Base

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="PENDING") # PENDING, RUNNING, COMPLETED, FAILED
    progress = Column(Integer, default=0)
    message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    estimated_remaining_seconds = Column(Integer, default=0)

class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("analysis_jobs.id"))
    
    dosya_adi = Column(String, index=True)
    contract_name = Column(String, nullable=True)
    doc_type = Column(String, nullable=True)
    company_type = Column(String, nullable=True)
    
    # Parties
    signing_party = Column(String, nullable=True)
    country = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    telenity_entity = Column(String, nullable=True)
    telenity_fullname = Column(String, nullable=True)
    
    # Details
    signed_date = Column(String, nullable=True)
    signature = Column(String, nullable=True) # Fully Signed, Counterparty Signed, etc.
    
    # Metadata
    file_hash = Column(String, index=True)
    durum_notu = Column(String, nullable=True)
    
    # YENİ EKLENEN: Güven Skoru
    confidence_score = Column(Integer, default=0)
