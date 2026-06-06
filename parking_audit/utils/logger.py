import logging
import os
from datetime import datetime
from pathlib import Path

from parking_audit.config import LOG_DIR

_logger_instance = None


def get_logger(name="parking_audit"):
    global _logger_instance
    if _logger_instance is not None:
        return _logger_instance

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        _logger_instance = logger
        return logger

    log_file = LOG_DIR / f"audit_{datetime.now().strftime('%Y%m%d')}.log"
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    _logger_instance = logger
    return logger


def log_operation(operation, details=None):
    logger = get_logger()
    msg = f"OPERATION: {operation}"
    if details:
        msg += f" | DETAILS: {details}"
    logger.info(msg)


def log_error(error, context=None):
    logger = get_logger()
    msg = f"ERROR: {error}"
    if context:
        msg += f" | CONTEXT: {context}"
    logger.error(msg)


def get_recent_logs(days=1, level=None):
    logs = []
    today = datetime.now()
    for i in range(days):
        log_date = today.replace(day=today.day - i)
        log_file = LOG_DIR / f"audit_{log_date.strftime('%Y%m%d')}.log"
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if level:
                        if f"- {level} -" in line:
                            logs.append(line.strip())
                    else:
                        logs.append(line.strip())
    return logs
