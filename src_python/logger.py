import logging
import sys
import os
from pathlib import Path
from pythonjsonlogger import jsonlogger
from contextvars import ContextVar
from typing import Optional

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
job_id_var: ContextVar[Optional[int]] = ContextVar('job_id', default=None)


class ContextualJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that includes context variables."""
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add context variables if available
        request_id = request_id_var.get()
        if request_id:
            log_record['request_id'] = request_id
        
        job_id = job_id_var.get()
        if job_id:
            log_record['job_id'] = job_id
        
        # Add environment info
        log_record['environment'] = os.getenv('ENVIRONMENT', 'development')
        
        # Ensure level name is included
        if not log_record.get('level'):
            log_record['level'] = record.levelname


def setup_logger(name="ContractsAI", log_file="app.log", level=logging.INFO, use_json=True):
    """
    Sets up a logger with structured JSON logging.
    
    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level
        use_json: If True, use JSON formatter; if False, use plain text
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding handlers multiple times
    if logger.hasHandlers():
        return logger

    # Choose formatter based on use_json flag
    if use_json:
        # JSON formatter for production
        json_formatter = ContextualJsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            rename_fields={'asctime': 'timestamp', 'levelname': 'level', 'name': 'logger'}
        )
        file_formatter = json_formatter
        console_formatter = json_formatter
    else:
        # Plain text formatter for development
        plain_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_formatter = plain_formatter
        console_formatter = plain_formatter

    # File Handler (always JSON for production compatibility)
    log_path = Path(log_file)
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    if use_json:
        file_handler.setFormatter(json_formatter)
    else:
        file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


def set_request_context(request_id: str):
    """Set request ID in context for all subsequent logs."""
    request_id_var.set(request_id)


def set_job_context(job_id: int):
    """Set job ID in context for all subsequent logs."""
    job_id_var.set(job_id)


def clear_context():
    """Clear all context variables."""
    request_id_var.set(None)
    job_id_var.set(None)


# Default logger instance
# Use JSON logging if ENVIRONMENT is production, otherwise plain text
use_json_logs = os.getenv('ENVIRONMENT', 'development') == 'production'
logger = setup_logger(use_json=use_json_logs)
