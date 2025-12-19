#!/usr/bin/env python3
"""
Hotel Munich LMS - Backup Manager
=================================
Script portable para backups automáticos de SQLite.

Características:
- Hot Backup: Copia segura sin detener la aplicación (usa sqlite3.backup API)
- Rotación automática: Mantiene últimos 7 días + 4 semanas
- Portable: Detecta rutas automáticamente usando __file__
- Logging: Registra todas las operaciones en logs/

Uso:
    python backup_manager.py
"""

import os
import sys
import sqlite3
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path

# ============================================
# CONFIGURACIÓN (Portable - Sin rutas hardcodeadas)
# ============================================

# Detectar directorio donde está este script
SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))

# Rutas relativas al script
DB_NAME = "hotel.db"
DB_PATH = SCRIPT_DIR / DB_NAME
BACKUP_DIR = SCRIPT_DIR / "backups"
LOG_DIR = SCRIPT_DIR / "logs"

# Configuración de retención
DAILY_RETENTION_DAYS = 7      # Mantener backups diarios de los últimos 7 días
WEEKLY_RETENTION_WEEKS = 4    # Mantener 4 backups semanales (uno por domingo)

# ============================================
# LOGGING
# ============================================

def setup_logging():
    """Configura el sistema de logs."""
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file = LOG_DIR / f"backup_{datetime.now().strftime('%Y-%m')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# ============================================
# FUNCIONES DE BACKUP
# ============================================

def perform_hot_backup(source_path: Path, dest_path: Path, logger) -> bool:
    """
    Realiza un Hot Backup usando la API nativa de sqlite3.
    Esto permite copiar la base de datos mientras la app está corriendo.
    
    Args:
        source_path: Ruta a la base de datos origen
        dest_path: Ruta donde guardar el backup
        logger: Logger para registrar operaciones
        
    Returns:
        True si el backup fue exitoso, False en caso contrario
    """
    try:
        logger.info(f"Iniciando hot backup: {source_path} -> {dest_path}")
        
        # Verificar que la DB origen existe
        if not source_path.exists():
            logger.error(f"Base de datos no encontrada: {source_path}")
            return False
        
        # Crear directorio destino si no existe
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Conectar a la base de datos origen (solo lectura)
        source_conn = sqlite3.connect(str(source_path), timeout=30)
        
        # Conectar a la base de datos destino (se creará)
        dest_conn = sqlite3.connect(str(dest_path))
        
        # Realizar el backup usando la API nativa
        # Esto es seguro incluso si hay transacciones activas
        source_conn.backup(dest_conn, pages=100, progress=lambda status, remaining, total: 
            logger.debug(f"Progreso: {total - remaining}/{total} páginas")
        )
        
        # Cerrar conexiones
        dest_conn.close()
        source_conn.close()
        
        # Verificar integridad del backup
        verify_conn = sqlite3.connect(str(dest_path))
        cursor = verify_conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        verify_conn.close()
        
        if result != "ok":
            logger.error(f"Verificación de integridad falló: {result}")
            return False
        
        # Obtener tamaño del archivo
        size_mb = dest_path.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Backup completado: {dest_path.name} ({size_mb:.2f} MB)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error durante backup: {e}")
        return False

def get_backup_filename(backup_type: str = "daily") -> str:
    """Genera nombre de archivo para el backup."""
    timestamp = datetime.now()
    
    if backup_type == "weekly":
        # Para semanales, usar número de semana
        return f"hotel_weekly_{timestamp.strftime('%Y-W%W')}.db"
    else:
        # Para diarios, usar fecha completa
        return f"hotel_daily_{timestamp.strftime('%Y-%m-%d_%H%M%S')}.db"

def cleanup_old_backups(logger):
    """
    Elimina backups antiguos según la política de retención.
    - Diarios: Mantener últimos 7 días
    - Semanales: Mantener últimos 4 domingos
    """
    try:
        if not BACKUP_DIR.exists():
            return
        
        now = datetime.now()
        daily_cutoff = now - timedelta(days=DAILY_RETENTION_DAYS)
        weekly_cutoff = now - timedelta(weeks=WEEKLY_RETENTION_WEEKS)
        
        deleted_count = 0
        
        for backup_file in BACKUP_DIR.glob("hotel_*.db"):
            try:
                # Extraer fecha del nombre del archivo
                name = backup_file.stem
                
                if "daily" in name:
                    # Formato: hotel_daily_2024-12-19_030000
                    date_str = name.replace("hotel_daily_", "").split("_")[0]
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if file_date < daily_cutoff:
                        backup_file.unlink()
                        logger.info(f"🗑️ Eliminado backup diario antiguo: {backup_file.name}")
                        deleted_count += 1
                        
                elif "weekly" in name:
                    # Formato: hotel_weekly_2024-W50
                    # Extraer año y semana
                    parts = name.replace("hotel_weekly_", "").split("-W")
                    year = int(parts[0])
                    week = int(parts[1])
                    
                    # Calcular fecha aproximada de esa semana
                    file_date = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
                    
                    if file_date < weekly_cutoff:
                        backup_file.unlink()
                        logger.info(f"🗑️ Eliminado backup semanal antiguo: {backup_file.name}")
                        deleted_count += 1
                        
            except (ValueError, IndexError) as e:
                logger.warning(f"No se pudo parsear fecha de: {backup_file.name}")
                continue
        
        if deleted_count > 0:
            logger.info(f"Limpieza completada: {deleted_count} backups eliminados")
        else:
            logger.debug("No hay backups antiguos para eliminar")
            
    except Exception as e:
        logger.error(f"Error durante limpieza: {e}")

def run_backup():
    """Función principal que ejecuta el proceso de backup."""
    logger = setup_logging()
    
    logger.info("=" * 50)
    logger.info("🔄 INICIANDO PROCESO DE BACKUP")
    logger.info(f"📁 Directorio de trabajo: {SCRIPT_DIR}")
    logger.info("=" * 50)
    
    # Verificar que existe la base de datos
    if not DB_PATH.exists():
        logger.error(f"❌ No se encontró la base de datos: {DB_PATH}")
        logger.error("Asegúrate de que hotel.db existe en el mismo directorio que este script.")
        return False
    
    # Crear directorio de backups si no existe
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Determinar tipo de backup (semanal los domingos, diario el resto)
    today = datetime.now()
    is_sunday = today.weekday() == 6  # 6 = Domingo
    
    success = True
    
    # 1. Siempre hacer backup diario
    daily_filename = get_backup_filename("daily")
    daily_path = BACKUP_DIR / daily_filename
    
    if not perform_hot_backup(DB_PATH, daily_path, logger):
        success = False
    
    # 2. Si es domingo, también hacer backup semanal
    if is_sunday:
        logger.info("📅 Es domingo - Creando backup semanal adicional")
        weekly_filename = get_backup_filename("weekly")
        weekly_path = BACKUP_DIR / weekly_filename
        
        # Copiar el backup diario como semanal (más eficiente que hacer otro hot backup)
        if daily_path.exists():
            shutil.copy2(daily_path, weekly_path)
            logger.info(f"✅ Backup semanal creado: {weekly_filename}")
        else:
            if not perform_hot_backup(DB_PATH, weekly_path, logger):
                success = False
    
    # 3. Limpiar backups antiguos
    logger.info("🧹 Ejecutando limpieza de backups antiguos...")
    cleanup_old_backups(logger)
    
    # Resumen final
    logger.info("=" * 50)
    if success:
        logger.info("✅ PROCESO DE BACKUP COMPLETADO EXITOSAMENTE")
    else:
        logger.error("⚠️ PROCESO DE BACKUP COMPLETADO CON ERRORES")
    logger.info("=" * 50)
    
    return success

# ============================================
# PUNTO DE ENTRADA
# ============================================

if __name__ == "__main__":
    try:
        success = run_backup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("Backup cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error fatal en backup: {e}")
        sys.exit(1)
