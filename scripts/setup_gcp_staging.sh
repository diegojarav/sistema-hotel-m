#!/bin/bash
# ==========================================
# Hotel Munich PMS - GCP Staging VM Setup
# ==========================================
#
# Automated provisioning script for Ubuntu 22.04 LTS.
# Run this AFTER cloning the repo on the VM.
#
# Usage:
#   git clone https://github.com/diegojarav/sistema-hotel-m.git /opt/hotel_munich
#   cd /opt/hotel_munich
#   bash scripts/setup_gcp_staging.sh
#
# ==========================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==========================================
# Configuration
# ==========================================

PROJECT_DIR="/opt/hotel_munich"
VENV_DIR="${PROJECT_DIR}/venv"
LOGS_DIR="${PROJECT_DIR}/backend/logs"
BACKUPS_DIR="${PROJECT_DIR}/backend/backups"

# ==========================================
# Helpers
# ==========================================

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERR ]${NC} $1"; }

section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# ==========================================
# Pre-checks
# ==========================================

section "PRE-FLIGHT CHECKS"

if [ "$(id -u)" -eq 0 ]; then
    err "Do not run this script as root. Run as your normal user."
    err "The script will use sudo where needed."
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/backend/requirements.txt" ]; then
    err "Project not found at ${PROJECT_DIR}"
    err "Clone the repo first: git clone <url> ${PROJECT_DIR}"
    exit 1
fi

ok "Project found at ${PROJECT_DIR}"

# Detect external IP
EXTERNAL_IP=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || curl -s ifconfig.me 2>/dev/null || echo "UNKNOWN")
info "External IP: ${EXTERNAL_IP}"

# ==========================================
# Step 1: System packages
# ==========================================

section "STEP 1: SYSTEM PACKAGES"

sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential \
    software-properties-common \
    git \
    curl \
    wget \
    unzip \
    sqlite3 \
    libsqlite3-dev \
    libffi-dev \
    libssl-dev

ok "System packages installed"

# ==========================================
# Step 2: Python 3.12 (deadsnakes PPA)
# ==========================================

section "STEP 2: PYTHON 3.12"

if command -v python3.12 &>/dev/null; then
    ok "Python 3.12 already installed: $(python3.12 --version)"
else
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
    ok "Python 3.12 installed: $(python3.12 --version)"
fi

# ==========================================
# Step 3: Node.js 22 LTS
# ==========================================

section "STEP 3: NODE.JS 22 LTS"

if command -v node &>/dev/null; then
    NODE_VER=$(node --version)
    ok "Node.js already installed: ${NODE_VER}"
else
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
    ok "Node.js installed: $(node --version)"
fi

info "npm version: $(npm --version)"

# ==========================================
# Step 4: Python virtual environment
# ==========================================

section "STEP 4: PYTHON VIRTUAL ENVIRONMENT"

if [ ! -d "${VENV_DIR}" ]; then
    python3.12 -m venv "${VENV_DIR}"
    ok "Virtual environment created at ${VENV_DIR}"
else
    ok "Virtual environment already exists"
fi

source "${VENV_DIR}/bin/activate"
pip install --upgrade pip -q

info "Installing backend dependencies..."
pip install -r "${PROJECT_DIR}/backend/requirements.txt" -q
ok "Backend dependencies installed"

info "Installing frontend_pc dependencies..."
pip install -r "${PROJECT_DIR}/frontend_pc/requirements.txt" -q
ok "Frontend PC dependencies installed"

# ==========================================
# Step 5: Node.js frontend build
# ==========================================

section "STEP 5: NEXT.JS FRONTEND BUILD"

cd "${PROJECT_DIR}/frontend_mobile"
npm install --silent

info "Building Next.js with API URL: http://${EXTERNAL_IP}:8000"
NEXT_PUBLIC_API_URL="http://${EXTERNAL_IP}:8000" npm run build

ok "Next.js frontend built"

# ==========================================
# Step 6: Create directories
# ==========================================

section "STEP 6: DIRECTORIES"

mkdir -p "${LOGS_DIR}"
mkdir -p "${BACKUPS_DIR}"

ok "Directories created: logs, backups"

# ==========================================
# Step 7: Environment file
# ==========================================

section "STEP 7: ENVIRONMENT CONFIGURATION"

ENV_FILE="${PROJECT_DIR}/backend/.env"

if [ -f "${ENV_FILE}" ]; then
    warn ".env already exists — skipping"
else
    JWT_SECRET=$(python3.12 -c "import secrets; print(secrets.token_urlsafe(32))")

    cat > "${ENV_FILE}" << ENVEOF
# Hotel Munich PMS - Staging Environment
# Generated by setup_gcp_staging.sh on $(date)

DB_NAME=hotel.db

# Security — auto-generated JWT secret
JWT_SECRET_KEY=${JWT_SECRET}

# Google Gemini API (leave empty to disable AI features)
GOOGLE_API_KEY=

# CORS — includes VM external IP
CORS_ORIGINS=http://localhost:3000,http://localhost:8501,http://127.0.0.1:3000,http://127.0.0.1:8501,http://${EXTERNAL_IP}:3000,http://${EXTERNAL_IP}:8501

# Monitoring (optional)
HEALTHCHECK_PING_URL=
DISCORD_WEBHOOK_URL=
ENVEOF

    ok ".env created with auto-generated JWT secret"
    info "Edit ${ENV_FILE} to add your GOOGLE_API_KEY if needed"
fi

# ==========================================
# Step 8: Initialize database and seed data
# ==========================================

section "STEP 8: DATABASE INITIALIZATION"

cd "${PROJECT_DIR}"

# Initialize DB tables (via SQLAlchemy create_all)
info "Creating database tables..."
PYTHONPATH="${PROJECT_DIR}/backend" "${VENV_DIR}/bin/python" -c "
import sys
sys.path.insert(0, 'backend')
from dotenv import load_dotenv
load_dotenv('backend/.env')
from database import init_db
init_db()
print('  [ OK ] Database tables created')
"

# Run base seed
info "Running seed_monges.py (property, rooms, categories)..."
"${VENV_DIR}/bin/python" scripts/seed_monges.py --db-path "${PROJECT_DIR}/backend/hotel.db"

# Run test data seed
info "Running seed_test_data.py (reservations, checkins, sessions)..."
"${VENV_DIR}/bin/python" scripts/seed_test_data.py --db-path "${PROJECT_DIR}/backend/hotel.db"

# Create default users
info "Creating default users..."
PYTHONPATH="${PROJECT_DIR}/backend" "${VENV_DIR}/bin/python" -c "
import sys, os
sys.path.insert(0, 'backend')
os.chdir('backend')
from dotenv import load_dotenv
load_dotenv('.env')
from database import SessionLocal, User
from api.core.security import get_password_hash
db = SessionLocal()
created = 0
for uname, pwd, role, rname in [
    ('admin', 'admin123', 'admin', 'Administrador'),
    ('recepcion', 'recep123', 'recepcionista', 'Recepcion'),
]:
    if not db.query(User).filter(User.username == uname).first():
        db.add(User(username=uname, password=get_password_hash(pwd), role=role, real_name=rname))
        created += 1
db.commit()
db.close()
print(f'  [ OK ] Users: {created} created')
"

ok "Database initialized and seeded"

# ==========================================
# Step 9: Install systemd services
# ==========================================

section "STEP 9: SYSTEMD SERVICES"

CURRENT_USER=$(whoami)

# Backend service
sudo tee /etc/systemd/system/hotel-backend.service > /dev/null << SVCEOF
[Unit]
Description=Hotel Munich PMS - Backend API (FastAPI)
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}/backend
Environment=PYTHONPATH=${PROJECT_DIR}/backend
ExecStart=${VENV_DIR}/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:${LOGS_DIR}/service_backend.log
StandardError=append:${LOGS_DIR}/service_backend_err.log

[Install]
WantedBy=multi-user.target
SVCEOF

# Streamlit PC frontend service
sudo tee /etc/systemd/system/hotel-pc.service > /dev/null << SVCEOF
[Unit]
Description=Hotel Munich PMS - PC Frontend (Streamlit)
After=hotel-backend.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}/frontend_pc
Environment=PYTHONPATH=${PROJECT_DIR}/backend
ExecStart=${VENV_DIR}/bin/python -m streamlit run app.py --server.port 8501 --server.headless true --server.address 0.0.0.0
Restart=always
RestartSec=5
StandardOutput=append:${LOGS_DIR}/service_pc.log
StandardError=append:${LOGS_DIR}/service_pc_err.log

[Install]
WantedBy=multi-user.target
SVCEOF

# Next.js mobile frontend service
sudo tee /etc/systemd/system/hotel-mobile.service > /dev/null << SVCEOF
[Unit]
Description=Hotel Munich PMS - Mobile Frontend (Next.js)
After=hotel-backend.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}/frontend_mobile
Environment=NODE_ENV=production
ExecStart=$(which npm) start -- --port 3000
Restart=always
RestartSec=5
StandardOutput=append:${LOGS_DIR}/service_mobile.log
StandardError=append:${LOGS_DIR}/service_mobile_err.log

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable hotel-backend hotel-pc hotel-mobile

ok "Systemd services installed and enabled"

# ==========================================
# Step 10: Start services
# ==========================================

section "STEP 10: START SERVICES"

sudo systemctl start hotel-backend
info "Waiting for backend to start..."
sleep 4

sudo systemctl start hotel-pc hotel-mobile
info "Waiting for all services..."
sleep 3

# Verify
echo ""
for svc in hotel-backend hotel-pc hotel-mobile; do
    STATUS=$(systemctl is-active ${svc} 2>/dev/null || echo "failed")
    if [ "${STATUS}" = "active" ]; then
        ok "${svc}: ${STATUS}"
    else
        err "${svc}: ${STATUS}"
    fi
done

# Health check
echo ""
info "Checking backend health..."
HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{"status":"error"}')
echo "  ${HEALTH}" | python3.12 -m json.tool 2>/dev/null || echo "  ${HEALTH}"

# ==========================================
# Summary
# ==========================================

section "SETUP COMPLETE"

echo -e "  ${GREEN}Backend API:${NC}     http://${EXTERNAL_IP}:8000"
echo -e "  ${GREEN}API Docs:${NC}        http://${EXTERNAL_IP}:8000/docs"
echo -e "  ${GREEN}PC Frontend:${NC}     http://${EXTERNAL_IP}:8501"
echo -e "  ${GREEN}Mobile Frontend:${NC} http://${EXTERNAL_IP}:3000"
echo ""
echo -e "  ${BLUE}Default users:${NC}"
echo "    admin / admin123"
echo "    recepcion / recep123"
echo ""
echo -e "  ${BLUE}Service control:${NC}"
echo "    bash scripts/service_control_linux.sh status"
echo "    bash scripts/service_control_linux.sh restart"
echo ""
echo -e "  ${BLUE}Logs:${NC}"
echo "    tail -f ${LOGS_DIR}/service_backend.log"
echo ""
echo -e "  ${YELLOW}Cost reminder:${NC}"
echo "    Stop VM when not testing: gcloud compute instances stop hotel-munich-staging"
echo "    Running: ~\$16/mo | Stopped: ~\$3.60/mo (disk only)"
echo ""
