"""
Hotel Munich LMS - Configuración Centralizada de Logging
=========================================================

Proporciona un sistema de logging profesional con:
- RotatingFileHandler para evitar llenado de disco
- Formato estructurado con timestamp, nivel, módulo
- Separación de handlers para consola (dev) y archivo (prod)

Uso:
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Mensaje de ejemplo")
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Directorio base del proyecto
BASE_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
LOG_DIR = BASE_DIR / "logs"

# Configuración de rotación
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

# Formato estructurado
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ensure_log_directory():
    """Crea el directorio de logs si no existe."""
    if not LOG_DIR.exists():
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Crear .gitkeep para que git trackee el directorio vacío
        gitkeep = LOG_DIR / ".gitkeep"
        gitkeep.touch(exist_ok=True)


def setup_logging(environment: str = "development") -> logging.Logger:
    """
    Configura el sistema de logging para toda la aplicación.
    
    Args:
        environment: "development" o "production"
        
    Returns:
        Logger raíz configurado
    """
    _ensure_log_directory()
    
    # Obtener logger raíz de la aplicación
    root_logger = logging.getLogger("hotel_munich")
    
    # Evitar duplicación de handlers si ya está configurado
    if root_logger.handlers:
        return root_logger
    
    root_logger.setLevel(logging.DEBUG)
    
    # Formatter común
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    # === Console Handler ===
    # Siempre activo, nivel depende del ambiente
    console_handler = logging.StreamHandler()
    console_level = logging.INFO if environment == "production" else logging.DEBUG
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # === File Handler con Rotación ===
    log_file = LOG_DIR / "hotel_munich.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # === Error File Handler (solo errores) ===
    error_log_file = LOG_DIR / "hotel_munich_errors.log"
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger hijo del logger principal.
    
    Args:
        name: Nombre del módulo (usar __name__)
        
    Returns:
        Logger configurado para el módulo
        
    Ejemplo:
        logger = get_logger(__name__)
        logger.info("Operación completada")
    """
    # Inicializar logging si no está configurado
    root = logging.getLogger("hotel_munich")
    if not root.handlers:
        setup_logging()
    
    # Crear logger hijo
    return logging.getLogger(f"hotel_munich.{name}")


# Inicializar automáticamente al importar
_root_logger = setup_logging()
