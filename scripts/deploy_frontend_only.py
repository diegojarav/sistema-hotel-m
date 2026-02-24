#!/usr/bin/env python3
"""
Hotel Munich PMS - Frontend-Only Deployment
=============================================

Lightweight deploy for frontend changes only.
No database backup, no migrations, no backend restart.

Usage:
    python scripts/deploy_frontend_only.py           # Deploy both frontends
    python scripts/deploy_frontend_only.py --mobile   # Mobile only
    python scripts/deploy_frontend_only.py --pc       # PC only
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent
FRONTEND_MOBILE_DIR = PROJECT_ROOT / "frontend_mobile"
NSSM = SCRIPT_DIR / "nssm.exe"


def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "[INFO]", "OK": "[ OK ]", "WARN": "[WARN]", "ERR": "[ERR ]"}
    print(f"  {prefix.get(level, '[????]')} {timestamp} | {msg}")


def run_cmd(cmd, cwd=None, timeout=120):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(cwd) if cwd else None, shell=True,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def main():
    parser = argparse.ArgumentParser(description="Frontend-only deployment")
    parser.add_argument("--mobile", action="store_true", help="Deploy mobile only")
    parser.add_argument("--pc", action="store_true", help="Deploy PC only")
    args = parser.parse_args()

    # Default: deploy both
    deploy_mobile = args.mobile or (not args.mobile and not args.pc)
    deploy_pc = args.pc or (not args.mobile and not args.pc)

    print()
    print("  HOTEL MUNICH — FRONTEND DEPLOY")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Git pull
    log("Pulling latest changes...")
    ok, out, err = run_cmd("git pull origin main", cwd=PROJECT_ROOT)
    if not ok:
        log(f"git pull failed: {err}", "ERR")
        sys.exit(1)
    log(f"Git: {out.split(chr(10))[0]}", "OK")

    # Step 2: Build & restart mobile
    if deploy_mobile and FRONTEND_MOBILE_DIR.exists():
        log("Installing mobile dependencies...")
        run_cmd("npm install --prefer-offline", cwd=FRONTEND_MOBILE_DIR, timeout=120)

        log("Building Next.js production bundle...")
        ok, out, err = run_cmd("npm run build", cwd=FRONTEND_MOBILE_DIR, timeout=300)
        if ok:
            log("Mobile build successful", "OK")
        else:
            log(f"Mobile build failed: {err[:200]}", "ERR")
            sys.exit(1)

        log("Restarting mobile service...")
        run_cmd(f'"{NSSM}" restart HotelMunich_Mobile')
        time.sleep(3)
        log("HotelMunich_Mobile restarted", "OK")

    # Step 3: Restart PC frontend
    if deploy_pc:
        log("Restarting PC frontend service...")
        run_cmd(f'"{NSSM}" restart HotelMunich_PC')
        time.sleep(2)
        log("HotelMunich_PC restarted", "OK")

    print()
    print("  ✅ FRONTEND DEPLOY COMPLETE")
    print()


if __name__ == "__main__":
    main()
