from celery_app import celery_app
from pipeline import PipelineManager
from database import get_db
from models import AnalysisJob
from logger import logger, set_job_context
import traceback
import os
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

# Initialize Sentry for Celery workers
SENTRY_DSN = os.getenv('SENTRY_DSN')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,  # 10% of tasks
        environment=ENVIRONMENT,
        attach_stacktrace=True,
    )
    logger.info("Sentry initialized for Celery worker")



@celery_app.task(bind=True, name='tasks.process_analysis_job')
def process_analysis_job(self, job_id: int, folder_path: str):
    """
    Celery task for processing analysis jobs.
    
    Args:
        self: Task instance (for updating state)
        job_id: Database job ID
        folder_path: Path to folder containing PDFs
    
    This task is restart-safe and can be distributed across multiple workers.
    """
    logger.info(f"Celery task started for job {job_id}")
    set_job_context(job_id)
    
    # Set Sentry context
    if SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("job_id", job_id)
            scope.set_tag("task_type", "analysis")
            scope.set_context("job", {"id": job_id, "folder": folder_path})
    
    # Update task state
    self.update_state(state='PROCESSING', meta={'job_id': job_id, 'folder': folder_path})
    
    try:
        # Initialize pipeline
        pipeline = PipelineManager()
        
        # Run the job (blocking operation)
        pipeline.run_job(job_id, folder_path)
        
        logger.info(f"Celery task completed successfully for job {job_id}")
        return {'status': 'SUCCESS', 'job_id': job_id}
        
    except Exception as e:
        logger.error(f"Celery task failed for job {job_id}: {e}")
        traceback.print_exc()
        
        # Capture in Sentry with extra context
        if SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        
        # Update database to reflect failure
        try:
            db = next(get_db())
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.message = f"Task error: {str(e)}"
                db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update job status: {db_error}")
        
        # Re-raise for Celery to handle
        raise


@celery_app.task(name='tasks.cleanup_old_jobs')
def cleanup_old_jobs():
    """
    Periodic task to clean up old completed/failed jobs.
    Run this with celery beat scheduler.
    """
    from datetime import datetime, timedelta
    
    try:
        db = next(get_db())
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        # Delete contracts older than 30 days
        deleted_count = db.query(AnalysisJob).filter(
            AnalysisJob.created_at < cutoff_date,
            AnalysisJob.status.in_(['COMPLETED', 'FAILED', 'CANCELLED'])
        ).delete()
        
        db.commit()
        logger.info(f"Cleaned up {deleted_count} old jobs")
        return {'deleted_count': deleted_count}
        
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise
