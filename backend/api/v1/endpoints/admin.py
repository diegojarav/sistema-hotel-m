"""
Hotel PMS API - Admin Endpoints
===================================

Remote management endpoints for monitoring and maintenance.
All endpoints require admin role.

Endpoints:
- GET  /admin/backups          — List recent backups with sizes
- POST /admin/backups/trigger  — Trigger manual backup
- GET  /admin/logs/errors      — Last N error log lines
- GET  /admin/deploy-log       — Last 10 deployment entries
- GET  /admin/system-info      — System info (disk, uptime, version)
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import require_role
from api.core.config import APP_VERSION

router = APIRouter()

# Resolve paths relative to backend/
BACKEND_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent.parent
BACKUP_DIR = BACKEND_DIR / "backups"
LOG_DIR = BACKEND_DIR / "logs"
PROJECT_ROOT = BACKEND_DIR.parent


# ==========================================
# BACKUP MANAGEMENT
# ==========================================

@router.get(
    "/backups",
    summary="List recent backups",
    dependencies=[Depends(require_role("admin"))],
)
def list_backups(limit: int = 20):
    """List recent database backups with file sizes."""
    if not BACKUP_DIR.exists():
        return {"backups": [], "backup_dir": str(BACKUP_DIR)}

    backups = []
    for f in sorted(BACKUP_DIR.glob("hotel_*.db"), key=os.path.getmtime, reverse=True)[:limit]:
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {"backups": backups, "total": len(backups), "backup_dir": str(BACKUP_DIR)}


@router.post(
    "/backups/trigger",
    summary="Trigger manual backup",
    dependencies=[Depends(require_role("admin"))],
)
def trigger_backup():
    """Run backup_manager.py to create an immediate database backup."""
    backup_script = BACKEND_DIR / "backup_manager.py"

    if not backup_script.exists():
        return {"success": False, "error": f"backup_manager.py not found at {backup_script}"}

    try:
        result = subprocess.run(
            [sys.executable, str(backup_script)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(BACKEND_DIR),
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Backup script timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==========================================
# LOG ACCESS
# ==========================================

@router.get(
    "/logs/errors",
    summary="Recent error log lines",
    dependencies=[Depends(require_role("admin"))],
)
def get_error_logs(lines: int = 50):
    """Read the last N lines from the error log file."""
    error_log = LOG_DIR / "hotel_munich_errors.log"

    if not error_log.exists():
        return {"lines": [], "file": str(error_log), "exists": False}

    try:
        with open(error_log, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {
            "lines": [line.rstrip() for line in recent],
            "total_lines": len(all_lines),
            "showing": len(recent),
            "file": error_log.name,
        }
    except Exception as e:
        return {"lines": [], "error": str(e)}


@router.get(
    "/logs/app",
    summary="Recent application log lines",
    dependencies=[Depends(require_role("admin"))],
)
def get_app_logs(lines: int = 50, search: Optional[str] = None):
    """Read the last N lines from the main application log. Optionally filter by search term."""
    app_log = LOG_DIR / "hotel_munich.log"

    if not app_log.exists():
        return {"lines": [], "file": str(app_log), "exists": False}

    try:
        with open(app_log, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        if search:
            all_lines = [l for l in all_lines if search.lower() in l.lower()]

        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {
            "lines": [line.rstrip() for line in recent],
            "total_lines": len(all_lines),
            "showing": len(recent),
            "file": app_log.name,
            "filter": search,
        }
    except Exception as e:
        return {"lines": [], "error": str(e)}


# ==========================================
# DEPLOYMENT LOG
# ==========================================

@router.get(
    "/deploy-log",
    summary="Recent deployments",
    dependencies=[Depends(require_role("admin"))],
)
def get_deploy_log(limit: int = 10):
    """Read the last N entries from the deployment log."""
    deploy_log = LOG_DIR / "deployments.log"

    if not deploy_log.exists():
        return {"entries": [], "file": str(deploy_log), "exists": False}

    try:
        with open(deploy_log, "r", encoding="utf-8") as f:
            content = f.read()

        # Each deployment entry is separated by a line of "="
        entries = [e.strip() for e in content.split("=" * 50) if e.strip()]
        recent = entries[-limit:] if len(entries) > limit else entries
        recent.reverse()  # Most recent first

        return {
            "entries": recent,
            "total": len(entries),
            "showing": len(recent),
        }
    except Exception as e:
        return {"entries": [], "error": str(e)}


# ==========================================
# SYSTEM INFO
# ==========================================

@router.get(
    "/system-info",
    summary="System information",
    dependencies=[Depends(require_role("admin"))],
)
def get_system_info():
    """System info: version, disk space, Python version, database size."""
    import shutil
    import platform

    # Disk space
    try:
        disk = shutil.disk_usage(str(BACKEND_DIR))
        disk_info = {
            "total_gb": round(disk.total / (1024 ** 3), 1),
            "used_gb": round(disk.used / (1024 ** 3), 1),
            "free_gb": round(disk.free / (1024 ** 3), 1),
            "usage_percent": round(disk.used / disk.total * 100, 1),
        }
    except Exception:
        disk_info = {"error": "Could not read disk info"}

    # Database size
    db_path = BACKEND_DIR / "hotel.db"
    db_size_mb = round(db_path.stat().st_size / (1024 * 1024), 2) if db_path.exists() else 0

    # Git info
    try:
        git_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        git_commit = git_result.stdout.strip() if git_result.returncode == 0 else "unknown"
    except Exception:
        git_commit = "unknown"

    return {
        "version": APP_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "disk": disk_info,
        "database_size_mb": db_size_mb,
        "git_commit": git_commit,
        "backend_dir": str(BACKEND_DIR),
    }
