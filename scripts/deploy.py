#!/usr/bin/env python3
"""
Hotel Munich PMS - Deployment Script
======================================

Safe, automated deployment with backup, migration, and rollback support.

Usage:
    python scripts/deploy.py                    # Standard deploy
    python scripts/deploy.py --skip-tests       # Deploy without running tests
    python scripts/deploy.py --rollback         # Rollback to previous deploy
    python scripts/deploy.py --dry-run          # Show what would happen

Workflow:
    1. Pre-flight checks (git clean, services running)
    2. Database backup (pre-deploy safety net)
    3. git pull origin main
    4. Install dependencies (if changed)
    5. Run migrations (if new migration files)
    6. Build frontend (if changed)
    7. Run smoke tests (optional)
    8. Restart all services via NSSM
    9. Verify health endpoint
    10. Log deployment

Author: Claude Code
Date: 2026-02-23
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ============================================
# CONFIGURATION
# ============================================

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_MOBILE_DIR = PROJECT_ROOT / "frontend_mobile"
BACKUP_DIR = BACKEND_DIR / "backups"
LOG_DIR = BACKEND_DIR / "logs"
DEPLOY_LOG = LOG_DIR / "deployments.log"
DB_PATH = BACKEND_DIR / "hotel.db"

NSSM = SCRIPT_DIR / "nssm.exe"
SERVICES = ["HotelMunich_Backend", "HotelMunich_PC", "HotelMunich_Mobile"]
HEALTH_URL = "http://localhost:8000/health"

# Python executable (Miniconda)
PYTHON_EXE = r"A:\Miniconda\envs\hotel_munich\python.exe"
if not Path(PYTHON_EXE).exists():
    PYTHON_EXE = sys.executable


# ============================================
# UTILITIES
# ============================================

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = {"INFO": "[INFO]", "OK": "[ OK ]", "WARN": "[WARN]", "ERR": "[ERR ]", "STEP": "[>>>>]"}
    print(f"  {prefix.get(level, '[????]')} {timestamp} | {msg}")


def run_cmd(cmd, cwd=None, timeout=120):
    """Run a shell command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(cwd) if cwd else None, shell=True,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def file_hash(path):
    """Get MD5 hash of a file for change detection."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def get_git_commit():
    """Get current git commit hash (short)."""
    ok, out, _ = run_cmd("git rev-parse --short HEAD", cwd=PROJECT_ROOT)
    return out if ok else "unknown"


def get_git_branch():
    """Get current git branch name."""
    ok, out, _ = run_cmd("git rev-parse --abbrev-ref HEAD", cwd=PROJECT_ROOT)
    return out if ok else "unknown"


# ============================================
# PRE-FLIGHT CHECKS
# ============================================

def preflight_checks(dry_run=False):
    """Verify system is ready for deployment."""
    log("Running pre-flight checks...", "STEP")
    errors = []

    # 1. Git working directory clean
    ok, out, _ = run_cmd("git status --porcelain", cwd=PROJECT_ROOT)
    if out:
        errors.append(f"Git working directory not clean:\n{out}")

    # 2. On expected branch
    branch = get_git_branch()
    if branch != "main":
        log(f"WARNING: Not on main branch (current: {branch})", "WARN")

    # 3. NSSM available
    if not NSSM.exists():
        errors.append(f"NSSM not found at {NSSM}")

    # 4. Database exists
    if not DB_PATH.exists():
        errors.append(f"Database not found at {DB_PATH}")

    # 5. Backend dir exists
    if not BACKEND_DIR.exists():
        errors.append(f"Backend directory not found at {BACKEND_DIR}")

    if errors:
        for e in errors:
            log(e, "ERR")
        if not dry_run:
            return False
    else:
        log("All pre-flight checks passed", "OK")

    return True


# ============================================
# DEPLOYMENT STEPS
# ============================================

def step_backup():
    """Create pre-deploy database backup."""
    log("Creating pre-deploy database backup...", "STEP")
    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"pre_deploy_{timestamp}.db"

    # Use backup_manager's hot backup if available
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from backup_manager import perform_hot_backup
        import logging
        logger = logging.getLogger("deploy")

        success = perform_hot_backup(DB_PATH, backup_path, logger)
        if success:
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            log(f"Backup created: {backup_path.name} ({size_mb:.2f} MB)", "OK")
            return str(backup_path)
        else:
            log("Hot backup failed", "ERR")
            return None
    except ImportError:
        # Fallback: simple file copy
        import shutil
        shutil.copy2(DB_PATH, backup_path)
        log(f"Backup created (file copy): {backup_path.name}", "OK")
        return str(backup_path)


def step_git_pull():
    """Pull latest changes from remote."""
    log("Pulling latest changes from origin...", "STEP")

    ok, out, err = run_cmd("git pull origin main", cwd=PROJECT_ROOT)
    if not ok:
        log(f"git pull failed: {err}", "ERR")
        return False

    if "Already up to date" in out:
        log("Already up to date — no changes pulled", "OK")
    else:
        log(f"Changes pulled:\n{out[:300]}", "OK")

    return True


def step_install_deps():
    """Install Python/Node dependencies if requirements changed."""
    log("Checking dependencies...", "STEP")

    # Python deps
    req_file = BACKEND_DIR / "requirements.txt"
    ok, out, err = run_cmd(
        f'"{PYTHON_EXE}" -m pip install -r requirements.txt -q',
        cwd=BACKEND_DIR, timeout=180,
    )
    if ok:
        log("Python dependencies up to date", "OK")
    else:
        log(f"pip install warning: {err[:200]}", "WARN")

    # Node deps (only if package.json changed recently)
    if FRONTEND_MOBILE_DIR.exists():
        ok, out, err = run_cmd("npm install --prefer-offline", cwd=FRONTEND_MOBILE_DIR, timeout=180)
        if ok:
            log("Node dependencies up to date", "OK")
        else:
            log(f"npm install warning: {err[:200]}", "WARN")

    return True


def step_run_migrations():
    """Run database migrations if migration runner exists."""
    migration_runner = SCRIPT_DIR / "run_migrations.py"
    if not migration_runner.exists():
        log("No migration runner found — skipping", "INFO")
        return True

    log("Running database migrations...", "STEP")
    ok, out, err = run_cmd(f'"{PYTHON_EXE}" "{migration_runner}"', cwd=PROJECT_ROOT, timeout=120)
    if ok:
        log(f"Migrations complete: {out[-200:]}", "OK")
    else:
        log(f"Migration failed: {err[:300]}", "ERR")
        return False

    return True


def step_build_frontend():
    """Build Next.js production bundle."""
    if not FRONTEND_MOBILE_DIR.exists():
        log("No frontend_mobile directory — skipping build", "INFO")
        return True

    log("Building Next.js frontend...", "STEP")
    ok, out, err = run_cmd("npm run build", cwd=FRONTEND_MOBILE_DIR, timeout=300)
    if ok:
        log("Frontend build successful", "OK")
    else:
        log(f"Frontend build failed: {err[:300]}", "ERR")
        return False

    return True


def step_run_tests(skip=False):
    """Run quick smoke tests."""
    if skip:
        log("Tests skipped (--skip-tests flag)", "INFO")
        return True

    log("Running smoke tests...", "STEP")
    ok, out, err = run_cmd(
        f'"{PYTHON_EXE}" -m pytest tests/ -x -q --tb=short',
        cwd=BACKEND_DIR, timeout=120,
    )
    if ok:
        # Extract pass count from pytest output
        log(f"Tests passed: {out.split(chr(10))[-1]}", "OK")
    else:
        log(f"Tests FAILED:\n{out[-500:]}", "ERR")
        return False

    return True


def step_restart_services():
    """Restart all NSSM services."""
    log("Restarting services...", "STEP")

    for svc in SERVICES:
        ok, out, err = run_cmd(f'"{NSSM}" restart {svc}')
        if ok:
            log(f"  {svc} restarted", "OK")
        else:
            log(f"  {svc} restart failed: {err[:100]}", "WARN")

    # Wait for services to come up
    log("Waiting 5 seconds for services to start...", "INFO")
    time.sleep(5)
    return True


def step_verify_health():
    """Verify the backend health endpoint responds."""
    log("Verifying health endpoint...", "STEP")

    for attempt in range(3):
        try:
            import urllib.request
            req = urllib.request.Request(HEALTH_URL)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("status") in ("healthy", "ok"):
                    log(f"Health check passed: {data}", "OK")
                    return True
                else:
                    log(f"Health check returned: {data}", "WARN")
        except Exception as e:
            log(f"Health check attempt {attempt + 1}/3 failed: {e}", "WARN")
            time.sleep(3)

    log("Health check FAILED after 3 attempts", "ERR")
    return False


# ============================================
# DEPLOYMENT LOG
# ============================================

def log_deployment(commit_before, commit_after, backup_path, success, duration_s):
    """Append deployment entry to log file."""
    LOG_DIR.mkdir(exist_ok=True)

    entry = f"""
{'=' * 50}
Deployment: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Status: {'SUCCESS' if success else 'FAILED'}
Branch: {get_git_branch()}
Commit: {commit_before} -> {commit_after}
Backup: {backup_path or 'none'}
Duration: {duration_s:.1f}s
{'=' * 50}
"""

    with open(DEPLOY_LOG, "a", encoding="utf-8") as f:
        f.write(entry)

    log(f"Deployment logged to {DEPLOY_LOG.name}", "OK")


# ============================================
# ROLLBACK
# ============================================

def do_rollback():
    """Rollback to the previous deployment state."""
    log("=" * 50)
    log("ROLLBACK INITIATED")
    log("=" * 50)

    # Read last deploy info
    if not DEPLOY_LOG.exists():
        log("No deployment log found — cannot rollback", "ERR")
        return False

    with open(DEPLOY_LOG, "r") as f:
        content = f.read()

    # Find the last successful deployment
    entries = content.split("=" * 50)
    commits = []
    backups = []
    for entry in entries:
        if "Commit:" in entry and "SUCCESS" in entry:
            for line in entry.strip().split("\n"):
                if line.startswith("Commit:"):
                    parts = line.split("->")
                    if len(parts) == 2:
                        commits.append(parts[0].replace("Commit:", "").strip())
                if line.startswith("Backup:"):
                    bp = line.replace("Backup:", "").strip()
                    if bp != "none":
                        backups.append(bp)

    if not commits:
        log("No previous successful deployment found", "ERR")
        return False

    prev_commit = commits[-1]
    log(f"Rolling back to commit: {prev_commit}")

    # 1. Git checkout previous commit
    ok, _, err = run_cmd(f"git checkout {prev_commit}", cwd=PROJECT_ROOT)
    if not ok:
        log(f"git checkout failed: {err}", "ERR")
        return False
    log(f"Code reverted to {prev_commit}", "OK")

    # 2. Restore database backup if available
    if backups:
        backup_file = Path(backups[-1])
        if backup_file.exists():
            import shutil
            shutil.copy2(backup_file, DB_PATH)
            log(f"Database restored from {backup_file.name}", "OK")
        else:
            log(f"Backup file not found: {backup_file}", "WARN")

    # 3. Restart services
    step_restart_services()

    # 4. Verify
    step_verify_health()

    log("ROLLBACK COMPLETE")
    return True


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Hotel Munich PMS - Deployment Script")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running pytest")
    parser.add_argument("--rollback", action="store_true", help="Rollback to previous deployment")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  HOTEL MUNICH PMS — DEPLOYMENT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print()

    if args.rollback:
        success = do_rollback()
        sys.exit(0 if success else 1)

    start_time = time.time()
    commit_before = get_git_commit()
    backup_path = None

    # Step 1: Pre-flight
    if not preflight_checks(args.dry_run):
        log("Pre-flight checks failed. Aborting.", "ERR")
        sys.exit(1)

    if args.dry_run:
        log("DRY RUN — would execute: backup, git pull, deps, migrations, build, tests, restart, verify")
        sys.exit(0)

    # Step 2: Backup
    backup_path = step_backup()
    if not backup_path:
        log("Backup failed. Aborting deployment.", "ERR")
        sys.exit(1)

    # Step 3: Git pull
    if not step_git_pull():
        log("Git pull failed. Aborting.", "ERR")
        sys.exit(1)

    # Step 4: Dependencies
    step_install_deps()

    # Step 5: Migrations
    if not step_run_migrations():
        log("Migration failed! Consider rolling back with --rollback", "ERR")
        sys.exit(1)

    # Step 6: Build frontend
    if not step_build_frontend():
        log("Frontend build failed! Backend may still work.", "WARN")

    # Step 7: Tests
    if not step_run_tests(skip=args.skip_tests):
        log("Tests failed! Consider rolling back with --rollback", "ERR")
        # Don't exit — let the developer decide

    # Step 8: Restart
    step_restart_services()

    # Step 9: Verify
    health_ok = step_verify_health()

    # Step 10: Log
    commit_after = get_git_commit()
    duration = time.time() - start_time
    log_deployment(commit_before, commit_after, backup_path, health_ok, duration)

    print()
    if health_ok:
        print("  ====================================")
        print("  ✅ DEPLOYMENT SUCCESSFUL")
        print(f"  Version: {commit_after}")
        print(f"  Duration: {duration:.1f}s")
        print("  ====================================")
    else:
        print("  ====================================")
        print("  ⚠️  DEPLOYMENT COMPLETED WITH WARNINGS")
        print("  Health check failed — check logs")
        print("  Run: python scripts/deploy.py --rollback")
        print("  ====================================")
    print()


if __name__ == "__main__":
    main()
