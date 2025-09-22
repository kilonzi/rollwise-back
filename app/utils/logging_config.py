import logging
import sys
from typing import Dict, Any, Optional


def setup_logging() -> logging.Logger:
    """Configure structured logging for the application"""

    # Create logger
    logger = logging.getLogger("rollwise")
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Create formatter for structured logging
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger


def log_request_info(
    logger: logging.Logger, endpoint: str, user_id: Optional[str] = None, **kwargs: Any
) -> None:
    """Log request information with context"""
    extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
    message = f"Request: {endpoint}"
    if user_id:
        message += f" | user_id={user_id}"
    if extra_info:
        message += f" | {extra_info}"
    logger.info(message)


def log_error_with_context(
    logger: logging.Logger, error: Exception, context: Dict[str, Any]
) -> None:
    """Log errors with contextual information"""
    context_str = " | ".join([f"{k}={v}" for k, v in context.items()])
    logger.error(f"Error: {str(error)} | Context: {context_str}")


def log_performance_metric(
    logger: logging.Logger, operation: str, duration_ms: float, **kwargs: Any
) -> None:
    """Log performance metrics"""
    extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
    message = f"Performance: {operation} | duration_ms={duration_ms:.2f}"
    if extra_info:
        message += f" | {extra_info}"
    logger.info(message)


# Create application-wide logger instance
app_logger = setup_logging()
