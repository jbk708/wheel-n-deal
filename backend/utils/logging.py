import sys
import os
from loguru import logger
from config import settings

# Remove default logger
logger.remove()

# Determine log level from environment or default to INFO
LOG_LEVEL = settings.LOG_LEVEL.upper() if hasattr(settings, "LOG_LEVEL") else "INFO"

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Add console logger
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)

# Add file logger for all logs
logger.add(
    "logs/wheel_n_deal.log",
    rotation="10 MB",
    retention="1 week",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level=LOG_LEVEL,
)

# Add file logger for errors only
logger.add(
    "logs/errors.log",
    rotation="10 MB",
    retention="1 month",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level="ERROR",
)

def get_logger(name):
    """
    Get a logger with the given name.
    
    Args:
        name (str): The name of the logger.
        
    Returns:
        logger: A logger instance with the given name.
    """
    return logger.bind(name=name)

# Initialize root logger
root_logger = get_logger("wheel_n_deal")
root_logger.info(f"Logging initialized at level {LOG_LEVEL}")

# Log startup information
root_logger.info(f"Starting Wheel-n-Deal application")
root_logger.debug(f"Debug logging is enabled")

# Export the logger
__all__ = ["get_logger"] 