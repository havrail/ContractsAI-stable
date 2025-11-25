from fastapi import FastAPI, HTTPException, Depends, Request, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import traceback
import uuid
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from pipeline import PipelineManager
from config import SETTINGS_PATH, load_json_config, API_KEY as CONFIGURED_API_KEY
from database import get_db, init_db
from models import AnalysisJob, Contract
from logger import logger, set_request_context, clear_context
from tasks import process_analysis_job  # Celery task
from feedback_service import FeedbackService  # NEW: Feedback system

# Initialize Sentry for error tracking
SENTRY_DSN = os.getenv('SENTRY_DSN')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        # Performance Monitoring
        traces_sample_rate=1.0 if ENVIRONMENT == 'development' else 0.1,  # 100% in dev, 10% in prod
        # Error Sampling
        sample_rate=1.0,  # Send all errors
        # Environment
        environment=ENVIRONMENT,
        # Release tracking (optional - use git commit hash in production)
        # release="contractsai@1.0.0",
        # Additional options
        attach_stacktrace=True,
        send_default_pii=False,  # Don't send personally identifiable info
        max_breadcrumbs=50,
    )
    logger.info(f"Sentry initialized for environment: {ENVIRONMENT}")
else:
    logger.info("Sentry DSN not configured, error tracking disabled")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    yield
    # Shutdown: Clean up resources if needed
    pass

app = FastAPI(lifespan=lifespan)

# Request ID middleware for tracking
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    set_request_context(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    clear_context()  # Clean up after request
    return response

# API Key Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key if authentication is enabled."""
    # If no API key is configured, skip authentication (development mode)
    if not CONFIGURED_API_KEY:
        return True
    
    if api_key != CONFIGURED_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    return True

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with Sentry integration."""
    print(f"Global Error: {exc}")
    traceback.print_exc()
    
    # Capture exception in Sentry with context
    if SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            scope.set_context("request", {
                "url": str(request.url),
                "method": request.method,
                "headers": dict(request.headers),
            })
            sentry_sdk.capture_exception(exc)
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



pipeline_manager = PipelineManager()

class AnalyzeRequest(BaseModel):
    folder_path: str

class SettingsUpdate(BaseModel):
    TESSERACT_CMD: str
    POPPLER_PATH: str
    LM_STUDIO_IP: str
    MAX_WORKERS: int
    USE_VISION_MODEL: bool

@app.post("/analyze")
async def start_analysis(req: AnalyzeRequest, db: Session = Depends(get_db), authenticated: bool = Depends(verify_api_key)):
    """Start analysis using Celery distributed task queue."""
    if not os.path.exists(req.folder_path):
        raise HTTPException(status_code=404, detail="Folder not found")

    # Create Job (sync DB operation)
    job = AnalysisJob(status="PENDING", message="Başlatılıyor...")
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch to Celery worker (restart-safe, distributed)
    task = process_analysis_job.delay(job.id, req.folder_path)
    
    logger.info(f"Celery task {task.id} dispatched for job {job.id}")
    
    # Add Sentry breadcrumb for tracking
    if SENTRY_DSN:
        sentry_sdk.add_breadcrumb(
            category='job',
            message=f'Analysis job {job.id} started',
            level='info',
            data={'job_id': job.id, 'task_id': task.id, 'folder': req.folder_path}
        )

    return {
        "message": "Analysis started", 
        "job_id": job.id,
        "celery_task_id": task.id  # For tracking
    }

@app.post("/cancel/{job_id}")
def cancel_job(job_id: int, db: Session = Depends(get_db), authenticated: bool = Depends(verify_api_key)):
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status in ["PENDING", "RUNNING"]:
        job.status = "CANCELLED"
        job.message = "İptal edildi"
        db.commit()
    
    return {"message": "Job cancellation requested"}

@app.get("/status/{job_id}")
async def get_job_status(job_id: int, db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "progress": job.progress,
        "estimated_remaining_seconds": job.estimated_remaining_seconds,
    }

@app.get("/results")
async def get_results(db: Session = Depends(get_db)):
    contracts = db.query(Contract).order_by(Contract.islenme_zamani.desc()).all()
    return contracts

@app.delete("/results")
def clear_results(db: Session = Depends(get_db), authenticated: bool = Depends(verify_api_key)):
    try:
        db.query(Contract).delete()
        db.query(AnalysisJob).delete()
        db.commit()
        return {"message": "All results cleared successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pdf/{filename}")
async def serve_pdf(filename: str):
    """Serve PDF files for preview."""
    from fastapi.responses import FileResponse
    import glob
    
    # Search for PDF in common locations
    # Note: In production, you'd track the original folder path in the database
    possible_paths = [
        f"./{filename}",
        f"./exports/{filename}",
        f"../exports/{filename}",
    ]
    
    # Also search recent analysis folders (last analyzed folder)
    # For now, we'll just check if file exists in any of these paths
    for path in possible_paths:
        if os.path.exists(path) and path.lower().endswith('.pdf'):
            return FileResponse(
                path,
                media_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
    
    # Not found
    raise HTTPException(status_code=404, detail="PDF file not found")

@app.get("/settings")
def get_settings():
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.post("/settings")
def update_settings(settings: SettingsUpdate, authenticated: bool = Depends(verify_api_key)):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings.dict(), f, indent=4)
    return {"message": "Settings updated"}

@app.get("/logs")
def get_logs(lines: int = 100, authenticated: bool = Depends(verify_api_key)):
    """Get recent application logs."""
    log_file = "app.log"
    if not os.path.exists(log_file):
        return {"logs": []}
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Read all lines and get the last 'lines' count
            all_lines = f.readlines()
            recent_logs = all_lines[-lines:]
            
            # Parse JSON logs if possible
            parsed_logs = []
            for line in recent_logs:
                try:
                    parsed_logs.append(json.loads(line))
                except json.JSONDecodeError:
                    parsed_logs.append({"message": line.strip(), "level": "INFO", "timestamp": ""})
            
            return {"logs": parsed_logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")

@app.get("/logs/download")
def download_logs(authenticated: bool = Depends(verify_api_key)):
    """Download system logs as a plain text file."""
    from fastapi.responses import PlainTextResponse
    from datetime import datetime
    
    log_file = "app.log"
    if not os.path.exists(log_file):
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        filename = f"system_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        return PlainTextResponse(
            content=content,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")

@app.post("/system/shutdown")
def shutdown_system(authenticated: bool = Depends(verify_api_key)):
    """
    Shuts down the entire application by killing related processes.
    Specific to Windows environment as requested.
    """
    import subprocess
    
    def kill_processes():
        time.sleep(1)  # Give time for the response to be sent
        # Kill by Window Title (as set in start_app.bat)
        subprocess.run("taskkill /F /FI \"WINDOWTITLE eq ContractsAI*\"", shell=True)
        # Kill by process name just in case (careful not to kill system python if used elsewhere, but for this user it's likely fine)
        # subprocess.run("taskkill /F /IM celery.exe /T", shell=True)
        # subprocess.run("taskkill /F /IM uvicorn.exe /T", shell=True)
        
        # Finally kill self
        os._exit(0)

    # Run in separate thread to allow returning response first
    threading.Thread(target=kill_processes).start()
    return {"message": "System shutting down..."}

@app.get("/debug/export-logs")
def export_logs(authenticated: bool = Depends(verify_api_key)):
    """
    Bundles application logs and system info into a single text file.
    """
    import platform
    from datetime import datetime
    
    output = []
    output.append("="*50)
    output.append(f"CONTRACTS AI - DEBUG REPORT")
    output.append(f"Date: {datetime.now().isoformat()}")
    output.append("="*50)
    output.append("")
    
    # System Info
    output.append(f"OS: {platform.system()} {platform.release()}")
    output.append(f"Python: {platform.python_version()}")
    output.append(f"Processor: {platform.processor()}")
    output.append("")
    
    # App Config (Safe subset)
    output.append("-" * 20 + " CONFIGURATION " + "-" * 20)
    output.append(f"TESSERACT_CMD: {os.getenv('TESSERACT_CMD', 'Not Set')}")
    output.append(f"POPPLER_PATH: {os.getenv('POPPLER_PATH', 'Not Set')}")
    output.append(f"MAX_WORKERS: {os.getenv('MAX_WORKERS', 'Not Set')}")
    output.append("")
    
    # Recent Logs
    output.append("-" * 20 + " RECENT LOGS " + "-" * 20)
    log_file = "app.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                # Get last 500 lines
                lines = f.readlines()[-500:]
                output.extend([l.strip() for l in lines])
        except Exception as e:
            output.append(f"Error reading log file: {e}")
    else:
        output.append("Log file not found.")
        
    # Create response
    content = "\n".join(output)
    filename = f"contracts_ai_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    return JSONResponse(
        content={"filename": filename, "content": content},
        status_code=200
    )

@app.get("/health")
def health_check():
    """Enhanced health check endpoint (no authentication required)."""
    from datetime import datetime
    
    # Check database
    try:
        db = next(get_db())
        db.execute("SELECT 1")
        db_status = "healthy"
        db_error = None
    except Exception as e:
        db_status = "unhealthy"
        db_error = str(e)
    
    # Check LLM connectivity
    try:
        from llm_client import LLMClient
        llm = LLMClient()
        llm_status = "connected" if llm.is_connected else "disconnected"
    except Exception as e:
        llm_status = "error"
    
    # Overall status
    overall_status = "healthy" if db_status == "healthy" and llm_status == "connected" else "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": {"status": db_status, "error": db_error},
            "llm": {"status": llm_status},
            "authentication": {"enabled": bool(CONFIGURED_API_KEY)}
        }
    }

@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    """
    Detailed metrics endpoint for monitoring (no authentication required for monitoring tools).
    Returns operational metrics about the application.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Job statistics
    total_jobs = db.query(AnalysisJob).count()
    completed_jobs = db.query(AnalysisJob).filter(AnalysisJob.status == "COMPLETED").count()
    failed_jobs = db.query(AnalysisJob).filter(AnalysisJob.status == "FAILED").count()
    running_jobs = db.query(AnalysisJob).filter(AnalysisJob.status == "RUNNING").count()
    cancelled_jobs = db.query(AnalysisJob).filter(AnalysisJob.status == "CANCELLED").count()
    
    # Contract statistics
    total_contracts = db.query(Contract).count()
    
    # Cache statistics (contracts with "Önbellekten Alındı" status)
    cached_contracts = db.query(Contract).filter(Contract.durum_notu == "Önbellekten Alındı").count()
    cache_hit_rate = (cached_contracts / total_contracts * 100) if total_contracts > 0 else 0
    
    # Recent activity (last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_jobs = db.query(AnalysisJob).filter(AnalysisJob.created_at >= yesterday).count()
    recent_contracts = db.query(Contract).filter(Contract.islenme_zamani >= yesterday).count()
    
    # Average processing metrics
    completed_job_ids = db.query(AnalysisJob.id).filter(AnalysisJob.status == "COMPLETED").all()
    if completed_job_ids:
        avg_contracts_per_job = db.query(func.count(Contract.id)).filter(
            Contract.job_id.in_([j.id for j in completed_job_ids])
        ).scalar() / len(completed_job_ids)
    else:
        avg_contracts_per_job = 0
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "jobs": {
            "total": total_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
            "running": running_jobs,
            "cancelled": cancelled_jobs,
            "success_rate": (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
        },
        "contracts": {
            "total": total_contracts,
            "cached": cached_contracts,
            "cache_hit_rate": round(cache_hit_rate, 2)
        },
        "recent_activity_24h": {
            "jobs": recent_jobs,
            "contracts": recent_contracts
        },
        "performance": {
            "avg_contracts_per_job": round(avg_contracts_per_job, 2)
        }
    }

# ============================================================================
# FEEDBACK & CORRECTION ENDPOINTS (NEW)
# ============================================================================

class CorrectionRequest(BaseModel):
    contract_id: int
    field_name: str
    old_value: str
    new_value: str
    corrected_by: Optional[str] = "user"
    reason: Optional[str] = None

class BulkCorrectionRequest(BaseModel):
    corrections: List[CorrectionRequest]

@app.post("/api/corrections")
def submit_correction(
    correction: CorrectionRequest,
    db: Session = Depends(get_db),
    authenticated: bool = Depends(verify_api_key)
):
    """
    Kullanıcının yaptığı manuel düzeltmeyi kaydeder.
    
    Bu endpoint, Excel'de veya UI'da yapılan düzeltmeleri
    sisteme öğretmek için kullanılır.
    """
    try:
        feedback_service = FeedbackService(db)
        
        result = feedback_service.record_correction(
            contract_id=correction.contract_id,
            field_name=correction.field_name,
            old_value=correction.old_value,
            new_value=correction.new_value,
            corrected_by=correction.corrected_by,
            reason=correction.reason
        )
        
        return {
            "success": True,
            "message": "Correction recorded successfully",
            "correction_id": result.id
        }
    
    except Exception as e:
        logger.error(f"Correction recording failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/corrections/bulk")
def submit_bulk_corrections(
    request: BulkCorrectionRequest,
    db: Session = Depends(get_db),
    authenticated: bool = Depends(verify_api_key)
):
    """Toplu düzeltme kaydı"""
    try:
        feedback_service = FeedbackService(db)
        
        corrections_data = [corr.dict() for corr in request.corrections]
        count = feedback_service.bulk_record_corrections(corrections_data)
        
        return {
            "success": True,
            "message": f"{count} corrections recorded",
            "count": count
        }
    
    except Exception as e:
        logger.error(f"Bulk correction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accuracy")
def get_accuracy_stats(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Sistem doğruluk istatistikleri.
    
    Query Params:
        days: Kaç günlük veriyi analiz et (default: 30)
    """
    try:
        feedback_service = FeedbackService(db)
        report = feedback_service.get_overall_accuracy(days=days)
        
        return report
    
    except Exception as e:
        logger.error(f"Accuracy stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accuracy/{field_name}")
def get_field_accuracy(
    field_name: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Belirli bir alanın doğruluk istatistikleri"""
    try:
        feedback_service = FeedbackService(db)
        stats = feedback_service.get_field_accuracy(field_name, days=days)
        
        return stats
    
    except Exception as e:
        logger.error(f"Field accuracy failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/common-mistakes/{field_name}")
def get_common_mistakes(
    field_name: str,
    limit: int = 10,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Belirli bir alanda en sık yapılan hataları listeler"""
    try:
        feedback_service = FeedbackService(db)
        mistakes = feedback_service.get_common_mistakes(field_name, limit=limit, days=days)
        
        return {"field": field_name, "mistakes": mistakes}
    
    except Exception as e:
        logger.error(f"Common mistakes query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reports/weekly")
def get_weekly_accuracy_report(
    db: Session = Depends(get_db),
    authenticated: bool = Depends(verify_api_key)
):
    """Haftalık doğruluk raporu (text format)"""
    try:
        feedback_service = FeedbackService(db)
        report_text = feedback_service.generate_weekly_report()
        
        return {
            "report": report_text,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Weekly report generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export/training-data")
def export_training_data(
    days: int = 90,
    min_corrections: int = 3,
    db: Session = Depends(get_db),
    authenticated: bool = Depends(verify_api_key)
):
    """
    Düzeltmeleri fine-tuning training data'ya export eder.
    
    Query Params:
        days: Kaç günlük veriyi al (default: 90)
        min_corrections: Minimum düzeltme sayısı filtresi (default: 3)
    """
    try:
        feedback_service = FeedbackService(db)
        
        output_path = os.path.join(
            "data",
            f"training_corrections_{datetime.utcnow().strftime('%Y%m%d')}.json"
        )
        
        count = feedback_service.export_corrections_to_training_data(
            output_path=output_path,
            days=days,
            min_corrections=min_corrections
        )
        
        return {
            "success": True,
            "message": f"Exported {count} training samples",
            "output_file": output_path,
            "sample_count": count
        }
    
    except Exception as e:
        logger.error(f"Training data export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# REVIEW & QA ENDPOINTS
# ============================================================================

class ReviewRequest(BaseModel):
    """Request model for reviewing a contract."""
    review_status: str  # approved, rejected, corrected
    reviewed_by: str
    notes: Optional[str] = None


class FieldCorrectionRequest(BaseModel):
    """Request model for correcting a field."""
    field_name: str
    new_value: str
    old_value: Optional[str] = None
    corrected_by: str
    reason: Optional[str] = None


@app.get("/api/review/pending")
async def get_pending_reviews(
    limit: int = 50,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Get contracts that need manual review."""
    verify_api_key(api_key)
    
    try:
        contracts = db.query(Contract).filter(
            Contract.needs_review == 1,
            Contract.review_status == "pending"
        ).order_by(Contract.islenme_zamani.desc()).limit(limit).all()
        
        results = []
        for c in contracts:
            results.append({
                "id": c.id,
                "dosya_adi": c.dosya_adi,
                "signing_party": c.signing_party,
                "contract_name": c.contract_name,
                "signed_date": c.signed_date,
                "address": c.address,
                "country": c.country,
                "confidence_score": c.confidence_score,
                "review_reason": c.review_reason,
                "validation_issues": c.validation_issues,
                "validation_warnings": c.validation_warnings,
                "islenme_zamani": c.islenme_zamani.isoformat() if c.islenme_zamani else None
            })
        
        return {
            "total": len(results),
            "contracts": results
        }
    
    except Exception as e:
        logger.error(f"Failed to get pending reviews: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/review/{contract_id}")
async def review_contract(
    contract_id: int,
    review: ReviewRequest,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Submit review decision for a contract."""
    verify_api_key(api_key)
    
    from audit import AuditLogger
    audit = AuditLogger(db, user_id=review.reviewed_by)
    
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        old_status = contract.review_status
        contract.review_status = review.review_status
        contract.reviewed_by = review.reviewed_by
        contract.reviewed_at = datetime.utcnow()
        
        if review.review_status == "approved":
            contract.needs_review = 0
        
        db.commit()
        
        # Audit log
        audit.log_review_action(
            contract_id=contract_id,
            filename=contract.dosya_adi,
            review_status=review.review_status,
            old_status=old_status
        )
        
        logger.info(f"Contract {contract_id} reviewed: {review.review_status} by {review.reviewed_by}")
        
        return {
            "success": True,
            "contract_id": contract_id,
            "review_status": review.review_status
        }
    
    except Exception as e:
        logger.error(f"Review submission failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/correct/{contract_id}")
async def correct_contract_field(
    contract_id: int,
    correction: FieldCorrectionRequest,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Correct a specific field in a contract."""
    verify_api_key(api_key)
    
    from audit import AuditLogger
    from models import Correction
    
    audit = AuditLogger(db, user_id=correction.corrected_by)
    
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        # Get old value
        old_value = getattr(contract, correction.field_name, None)
        
        # Update field
        setattr(contract, correction.field_name, correction.new_value)
        contract.review_status = "corrected"
        contract.reviewed_by = correction.corrected_by
        contract.reviewed_at = datetime.utcnow()
        
        # Store correction record
        correction_record = Correction(
            contract_id=contract_id,
            field_name=correction.field_name,
            old_value=str(old_value) if old_value else "",
            new_value=correction.new_value,
            corrected_by=correction.corrected_by,
            corrected_at=datetime.utcnow(),
            correction_reason=correction.reason,
            confidence_before=contract.confidence_score
        )
        db.add(correction_record)
        
        db.commit()
        
        # Audit log
        audit.log_field_correction(
            contract_id=contract_id,
            field_name=correction.field_name,
            old_value=str(old_value) if old_value else "",
            new_value=correction.new_value,
            correction_reason=correction.reason
        )
        
        logger.info(
            f"Field corrected: {correction.field_name} in contract {contract_id} "
            f"by {correction.corrected_by}"
        )
        
        return {
            "success": True,
            "contract_id": contract_id,
            "field_name": correction.field_name,
            "old_value": old_value,
            "new_value": correction.new_value
        }
    
    except Exception as e:
        logger.error(f"Field correction failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit/stats")
async def get_audit_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Get audit statistics for monitoring dashboard."""
    verify_api_key(api_key)
    
    from audit import get_audit_stats
    
    try:
        stats = get_audit_stats(db, days=days)
        return stats
    except Exception as e:
        logger.error(f"Failed to get audit stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit/logs")
async def get_audit_logs(
    limit: int = 50,
    action_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Get recent audit logs."""
    verify_api_key(api_key)
    
    from audit import get_recent_audit_logs
    
    try:
        logs = get_recent_audit_logs(
            db=db,
            limit=limit,
            action_type=action_type,
            entity_type=entity_type,
            user_id=user_id
        )
        return {"total": len(logs), "logs": logs}
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/exports/history")
async def get_export_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Get export version history."""
    verify_api_key(api_key)
    
    from deduplication import ExportVersionControl
    
    try:
        service = ExportVersionControl(db)
        history = service.get_export_history(limit=limit)
        return {"total": len(history), "versions": history}
    except Exception as e:
        logger.error(f"Failed to get export history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/exports/compare/{version1}/{version2}")
async def compare_export_versions(
    version1: int,
    version2: int,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Compare two export versions."""
    verify_api_key(api_key)
    
    from deduplication import ExportVersionControl
    
    try:
        service = ExportVersionControl(db)
        comparison = service.compare_versions(version1, version2)
        return comparison
    except Exception as e:
        logger.error(f"Failed to compare versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# A/B TESTING & FOLDER AUTOMATION ENDPOINTS
# ============================================================================

class OrganizeRequest(BaseModel):
    """Request model for folder organization."""
    method: str  # type, company, date, confidence, hierarchical
    output_dir: Optional[str] = "organized_contracts"


@app.post("/api/organize")
async def organize_contracts_endpoint(
    request: OrganizeRequest,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Organize processed contracts into folders."""
    verify_api_key(api_key)
    
    from folder_automation import organize_contracts
    
    try:
        # Get all contracts
        contracts = db.query(Contract).all()
        
        contract_dicts = [
            {
                'dosya_adi': c.dosya_adi,
                'contract_name': c.contract_name,
                'signing_party': c.signing_party,
                'signed_date': c.signed_date,
                'confidence_score': c.confidence_score
            }
            for c in contracts
        ]
        
        # Organize (assumes source PDFs still exist)
        # In production, you'd need to track original file locations
        result = organize_contracts(
            contract_dicts,
            source_folder="input_pdfs",  # Configure this
            method=request.method,
            output_dir=request.output_dir
        )
        
        return {
            "success": True,
            "method": request.method,
            "folders_created": len(result),
            "files_organized": sum(len(v) for v in result.values()),
            "output_dir": request.output_dir
        }
    
    except Exception as e:
        logger.error(f"Organization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ab-test/run")
async def run_ab_test_endpoint(
    days: int = 7,
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Run A/B test on prompt variants."""
    verify_api_key(api_key)
    
    from ab_testing import run_prompt_ab_test
    
    try:
        result = run_prompt_ab_test(db, days=days)
        
        if not result:
            return {
                "success": False,
                "message": "Need at least 2 active variants"
            }
        
        return {
            "success": True,
            "winner": result.winner,
            "confidence": result.confidence_level,
            "recommendation": result.recommendation,
            "test_duration_days": result.test_duration_days,
            "metrics": {
                variant_id: {
                    "total_contracts": m.total_contracts,
                    "avg_confidence": m.avg_confidence,
                    "correction_rate": m.correction_rate,
                    "review_rate": m.review_rate,
                    "field_accuracy": m.field_accuracy
                }
                for variant_id, m in result.metrics.items()
            }
        }
    
    except Exception as e:
        logger.error(f"A/B test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ab-test/variants")
async def get_ab_test_variants(
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Get list of prompt variants."""
    verify_api_key(api_key)
    
    from ab_testing import ABTestManager
    
    try:
        manager = ABTestManager(db)
        variants = manager.get_active_variants()
        
        return {
            "total": len(variants),
            "variants": [
                {
                    "id": v.id,
                    "name": v.name,
                    "description": v.description,
                    "is_active": v.is_active
                }
                for v in variants
            ]
        }
    
    except Exception as e:
        logger.error(f"Failed to get variants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ab-test/best-prompt")
async def get_best_prompt(
    db: Session = Depends(get_db),
    api_key: str = Security(api_key_header)
):
    """Get best performing prompt variant."""
    verify_api_key(api_key)
    
    from ab_testing import get_best_prompt_variant
    
    try:
        best = get_best_prompt_variant(db)
        return {"best_variant": best}
    except Exception as e:
        logger.error(f"Failed to get best prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
