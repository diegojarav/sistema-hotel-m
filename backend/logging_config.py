"""
Hotel PMS - Configuración Centralizada de Logging
=========================================================

Proporciona un sistema de logging profesional con:
- RotatingFileHandler para evitar llenado de disco
- Formato estructurado con timestamp, nivel, módulo
- Separación de handlers para consola (dev) y archivo (prod)
- Discord webhook alerting para errores (opcional)

Uso:
    from logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Mensaje de ejemplo")
"""

import json
import logging
import os
import threading
import time
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


# ============================================
# DISCORD WEBHOOK HANDLER
# ============================================

class DiscordWebhookHandler(logging.Handler):
    """
    Sends ERROR+ log messages to a Discord channel via webhook.

    Features:
    - 5-minute deduplication (same message won't spam)
    - Non-blocking (sends in background thread)
    - Rich embed format with red sidebar for errors
    - Graceful failure (never crashes the app)
    """

    def __init__(self, webhook_url: str, dedup_seconds: int = 300):
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url
        self.dedup_seconds = dedup_seconds
        self._recent_messages = {}  # hash -> timestamp
        self._lock = threading.Lock()

    def _is_duplicate(self, message: str) -> bool:
        """Check if this message was sent recently."""
        msg_hash = hash(message)
        now = time.time()

        with self._lock:
            # Clean old entries
            self._recent_messages = {
                h: t for h, t in self._recent_messages.items()
                if now - t < self.dedup_seconds
            }

            if msg_hash in self._recent_messages:
                return True

            self._recent_messages[msg_hash] = now
            return False

    def emit(self, record: logging.LogRecord):
        """Send log record to Discord webhook."""
        try:
            message = self.format(record)
            if self._is_duplicate(message):
                return

            # Build Discord embed
            color = 0xFF0000 if record.levelno >= logging.CRITICAL else 0xE74C3C  # Dark red for CRITICAL

            # Truncate message for Discord (max 4096 chars in embed description)
            description = message[:2000]
            if record.exc_text:
                description += f"\n```\n{record.exc_text[:1500]}\n```"

            payload = {
                "embeds": [{
                    "title": f"🚨 {record.levelname}: {record.name}",
                    "description": description,
                    "color": color,
                    "footer": {"text": f"Hotel Munich PMS | {record.funcName}"},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
                }]
            }

            # Send in background thread to not block the app
            thread = threading.Thread(target=self._send, args=(payload,), daemon=True)
            thread.start()

        except Exception:
            # Never let webhook errors crash the app
            pass

    def _send(self, payload: dict):
        """Actually send the webhook (runs in background thread)."""
        try:
            import urllib.request
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # Silently fail — don't cascade errors


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

    # === Discord Webhook Handler (errores en tiempo real) ===
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if discord_url:
        discord_handler = DiscordWebhookHandler(webhook_url=discord_url)
        discord_handler.setLevel(logging.ERROR)
        discord_handler.setFormatter(formatter)
        root_logger.addHandler(discord_handler)

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
