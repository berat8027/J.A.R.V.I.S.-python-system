"""
core/logger.py
──────────────
Centralised logging powered by loguru.
- Rotating file log in logs/
- Console output coloured
- NEVER logs secrets or API keys
"""

import sys
from pathlib import Path
from loguru import logger
from config.settings import settings


def setup_logging() -> None:
    logger.remove()

    # Console
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=False,  # Never diagnose – might expose locals
    )

    # File
    log_file = settings.logs_dir / "jarvis_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        backtrace=True,
        diagnose=False,
        encoding="utf-8",
    )

    logger.info("Logging initialised – level={}", settings.log_level)


# Run at import
setup_logging()
