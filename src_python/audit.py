"""
Audit logging service for tracking all system actions.
"""

import json
import time
from typing import Dict, Optional, Any
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy.orm import Session
from models import AuditLog
from logger import logger


class AuditLogger:
    """Service for audit logging."""
    
    def __init__(self, db: Session, user_id: str = "system", ip_address: str = None):
        self.db = db
        self.user_id = user_id
        self.ip_address = ip_address
    
    def log_action(
        self,
        action_type: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        action_details: Optional[Dict] = None,
        old_values: Optional[Dict] = None,
        new_values: Optional[Dict] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        session_id: Optional[str] = None,
        duration_ms: Optional[int] = None
    ):
        """
        Log an action to the audit trail.
        
        Args:
            action_type: Type of action (process, review, correct, export, delete)
            entity_type: Type of entity affected (contract, job, user)
            entity_id: ID of the affected entity
            action_details: Additional details about the action
            old_values: Previous values (for updates)
            new_values: New values (for updates)
            status: success, failed, warning
            error_message: Error message if status is failed
            session_id: User session ID
            duration_ms: Action duration in milliseconds
        """
        try:
            audit_log = AuditLog(
                action_type=action_type,
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=self.user_id,
                ip_address=self.ip_address,
                action_details=json.dumps(action_details) if action_details else None,
                old_values=json.dumps(old_values) if old_values else None,
                new_values=json.dumps(new_values) if new_values else None,
                status=status,
                error_message=error_message,
                session_id=session_id,
                duration_ms=duration_ms,
                timestamp=datetime.utcnow()
            )
            
            self.db.add(audit_log)
            self.db.commit()
            
            logger.debug(f"Audit log: {action_type} on {entity_type} #{entity_id} by {self.user_id}")
        
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            self.db.rollback()
    
    def log_contract_processed(
        self,
        contract_id: int,
        filename: str,
        confidence: float,
        processing_time_ms: int
    ):
        """Log contract processing."""
        self.log_action(
            action_type="process",
            entity_type="contract",
            entity_id=contract_id,
            action_details={
                "filename": filename,
                "confidence": confidence
            },
            status="success",
            duration_ms=processing_time_ms
        )
    
    def log_review_action(
        self,
        contract_id: int,
        filename: str,
        review_status: str,
        old_status: str = "pending"
    ):
        """Log review action (approve/reject/correct)."""
        self.log_action(
            action_type="review",
            entity_type="contract",
            entity_id=contract_id,
            action_details={
                "filename": filename,
                "review_decision": review_status
            },
            old_values={"review_status": old_status},
            new_values={"review_status": review_status},
            status="success"
        )
    
    def log_field_correction(
        self,
        contract_id: int,
        field_name: str,
        old_value: str,
        new_value: str,
        correction_reason: Optional[str] = None
    ):
        """Log field correction."""
        self.log_action(
            action_type="correct",
            entity_type="contract",
            entity_id=contract_id,
            action_details={
                "field_name": field_name,
                "reason": correction_reason
            },
            old_values={field_name: old_value},
            new_values={field_name: new_value},
            status="success"
        )
    
    def log_export(
        self,
        export_path: str,
        total_records: int,
        export_format: str = "excel"
    ):
        """Log data export."""
        self.log_action(
            action_type="export",
            entity_type="system",
            action_details={
                "export_path": export_path,
                "total_records": total_records,
                "format": export_format
            },
            status="success"
        )
    
    def log_delete(
        self,
        entity_type: str,
        entity_id: int,
        details: Optional[Dict] = None
    ):
        """Log deletion."""
        self.log_action(
            action_type="delete",
            entity_type=entity_type,
            entity_id=entity_id,
            action_details=details,
            status="success"
        )
    
    def log_error(
        self,
        action_type: str,
        entity_type: str,
        error_message: str,
        entity_id: Optional[int] = None,
        details: Optional[Dict] = None
    ):
        """Log error."""
        self.log_action(
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            action_details=details,
            status="failed",
            error_message=error_message
        )
    
    @contextmanager
    def track_action(
        self,
        action_type: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        details: Optional[Dict] = None
    ):
        """
        Context manager to track action duration and auto-log.
        
        Usage:
            with audit_logger.track_action("process", "contract", contract_id):
                # Do processing
                pass
        """
        start_time = time.time()
        error = None
        
        try:
            yield
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            
            self.log_action(
                action_type=action_type,
                entity_type=entity_type,
                entity_id=entity_id,
                action_details=details,
                status="failed" if error else "success",
                error_message=error,
                duration_ms=duration_ms
            )


def get_audit_stats(db: Session, days: int = 7) -> Dict[str, Any]:
    """
    Get audit statistics for dashboard.
    
    Args:
        db: Database session
        days: Number of days to look back
    
    Returns:
        Dictionary with audit statistics
    """
    from datetime import timedelta
    from sqlalchemy import func
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Total actions
    total_actions = db.query(func.count(AuditLog.id)).filter(
        AuditLog.timestamp >= cutoff_date
    ).scalar()
    
    # Actions by type
    actions_by_type = db.query(
        AuditLog.action_type,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.timestamp >= cutoff_date
    ).group_by(AuditLog.action_type).all()
    
    # Failed actions
    failed_actions = db.query(func.count(AuditLog.id)).filter(
        AuditLog.timestamp >= cutoff_date,
        AuditLog.status == "failed"
    ).scalar()
    
    # Top users
    top_users = db.query(
        AuditLog.user_id,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.timestamp >= cutoff_date
    ).group_by(AuditLog.user_id).order_by(func.count(AuditLog.id).desc()).limit(5).all()
    
    # Average duration
    avg_duration = db.query(func.avg(AuditLog.duration_ms)).filter(
        AuditLog.timestamp >= cutoff_date,
        AuditLog.duration_ms.isnot(None)
    ).scalar()
    
    return {
        "total_actions": total_actions,
        "actions_by_type": {action: count for action, count in actions_by_type},
        "failed_actions": failed_actions,
        "success_rate": (total_actions - failed_actions) / total_actions * 100 if total_actions > 0 else 0,
        "top_users": [{"user": user, "count": count} for user, count in top_users],
        "avg_duration_ms": round(avg_duration, 2) if avg_duration else 0,
        "period_days": days
    }


def get_recent_audit_logs(
    db: Session,
    limit: int = 50,
    action_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None
) -> list:
    """
    Get recent audit logs with optional filters.
    
    Returns:
        List of audit log dictionaries
    """
    query = db.query(AuditLog)
    
    if action_type:
        query = query.filter(AuditLog.action_type == action_type)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    
    return [
        {
            "id": log.id,
            "action_type": log.action_type,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "user_id": log.user_id,
            "details": json.loads(log.action_details) if log.action_details else {},
            "status": log.status,
            "timestamp": log.timestamp.isoformat(),
            "duration_ms": log.duration_ms
        }
        for log in logs
    ]
