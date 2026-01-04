"""
Logging configuration for Polymarket Tracker

Provides structured logging with console and file output.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

# Default format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FORMAT_SIMPLE = "%(levelname)s: %(message)s"


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    name: str = "polymarket"
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional path to log file (enables file logging)
        name: Logger name

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with emoji-friendly format
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(ColoredFormatter(LOG_FORMAT_SIMPLE))
    logger.addHandler(console)

    # File handler (if log_file specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10_000_000,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)

    return logger


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output for terminal"""

    # ANSI color codes
    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    # Emoji prefixes for different levels
    EMOJI = {
        logging.DEBUG: "",
        logging.INFO: "",
        logging.WARNING: "",
        logging.ERROR: "",
        logging.CRITICAL: "",
    }

    def format(self, record):
        # Add color if terminal supports it
        color = self.COLORS.get(record.levelno, "")
        emoji = self.EMOJI.get(record.levelno, "")
        reset = self.RESET if color else ""

        # Format the message
        message = super().format(record)

        # Apply color and emoji
        if emoji:
            message = f"{emoji} {message}"

        return f"{color}{message}{reset}"


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (uses module name if None)

    Returns:
        Logger instance
    """
    return logging.getLogger(name or "polymarket")


# Convenience functions that match the print() patterns in the codebase
def log_success(message: str, logger: logging.Logger = None):
    """Log a success message with checkmark"""
    (logger or get_logger()).info(f"✅ {message}")


def log_warning(message: str, logger: logging.Logger = None):
    """Log a warning message"""
    (logger or get_logger()).warning(f"⚠️  {message}")


def log_error(message: str, logger: logging.Logger = None):
    """Log an error message"""
    (logger or get_logger()).error(f"❌ {message}")


def log_info(message: str, logger: logging.Logger = None):
    """Log an info message"""
    (logger or get_logger()).info(message)


def log_debug(message: str, logger: logging.Logger = None):
    """Log a debug message"""
    (logger or get_logger()).debug(message)
