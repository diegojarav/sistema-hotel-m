#!/bin/bash
# ==========================================
# Hotel Munich PMS - VM Disaster Recovery
# ==========================================
#
# Recreates the GCP VM from scratch and deploys everything.
# Run from your LOCAL machine (Windows Git Bash or WSL).
#
# Usage:
#   bash scripts/recreate_vm.sh
#
# What it does:
#   1. Deletes old VM (if exists)
#   2. Creates new e2-small VM (Ubuntu 22.04)
#   3. Opens firewall ports (3000, 8000, 8501)
#   4. SSHs in and runs full setup
#   5. Verifies all services are healthy
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - Project: gen-lang-client-0259000236
#
# ==========================================

set -euo pipefail

# ==========================================
# Configuration
# ==========================================

PROJECT="gen-lang-client-0259000236"
ZONE="us-central1-a"
VM_NAME="hotel-munich-staging"
MACHINE_TYPE="e2-small"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"
DISK_SIZE="20GB"
REPO_URL="https://github.com/diegojarav/sistema-hotel-m.git"
BRANCH="dev"

# Detect gcloud
if [ -f "C:/Users/diego/AppData/Local/Google/Cloud SDK/google-cloud-sdk/lib/gcloud.py" ]; then
    GCLOUD_PY="C:/Python314/python.exe"
    GCLOUD_LIB="C:/Users/diego/AppData/Local/Google/Cloud SDK/google-cloud-sdk/lib/gcloud.py"
    gcloud_cmd() { "$GCLOUD_PY" "$GCLOUD_LIB" "$@"; }
elif command -v gcloud &>/dev/null; then
    gcloud_cmd() { gcloud "$@"; }
else
    echo "ERROR: gcloud CLI not found"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  HOTEL MUNICH PMS - VM DISASTER RECOVERY    ║"
echo "║                                              ║"
echo "║  This will DELETE and RECREATE the VM.       ║"
echo "║  All data on the old VM will be LOST.        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# ==========================================
# Step 1: Delete old VM (if exists)
# ==========================================

echo ""
echo "=== Step 1: Checking for existing VM ==="

if gcloud_cmd compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "  Deleting existing VM: $VM_NAME..."
    gcloud_cmd compute instances delete "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT" \
        --quiet
    echo "  Old VM deleted."
else
    echo "  No existing VM found. Creating fresh."
fi

# ==========================================
# Step 2: Create new VM
# ==========================================

echo ""
echo "=== Step 2: Creating new VM ==="

gcloud_cmd compute instances create "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="$DISK_SIZE" \
    --tags=http-server,hotel-pms \
    --metadata=startup-script='#!/bin/bash
echo "VM started at $(date)" > /tmp/vm-ready.txt'

echo "  VM created. Waiting for SSH..."
sleep 20

# Get new external IP
NEW_IP=$(gcloud_cmd compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT" \
    --format="get(networkInterfaces[0].accessConfigs[0].natIP)")

echo "  New external IP: $NEW_IP"

# ==========================================
# Step 3: Firewall rules
# ==========================================

echo ""
echo "=== Step 3: Checking firewall rules ==="

if ! gcloud_cmd compute firewall-rules describe allow-hotel-pms --project="$PROJECT" &>/dev/null; then
    gcloud_cmd compute firewall-rules create allow-hotel-pms \
        --project="$PROJECT" \
        --allow=tcp:3000,tcp:8000,tcp:8501 \
        --target-tags=hotel-pms \
        --description="Hotel Munich PMS ports"
    echo "  Firewall rule created."
else
    echo "  Firewall rule already exists."
fi

# ==========================================
# Step 4: Clone repo and run setup
# ==========================================

echo ""
echo "=== Step 4: Deploying application ==="

gcloud_cmd compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT" --command="
set -e

echo '>>> Cloning repository...'
sudo git clone -b ${BRANCH} ${REPO_URL} /opt/hotel_munich
sudo chown -R \$(whoami):\$(whoami) /opt/hotel_munich
cd /opt/hotel_munich

echo '>>> Creating .env.local for mobile frontend...'
echo 'NEXT_PUBLIC_API_URL=http://${NEW_IP}:8000' > frontend_mobile/.env.local

echo '>>> Running setup script...'
bash scripts/setup_gcp_staging.sh

echo ''
echo '>>> DEPLOYMENT COMPLETE'
echo ''
"

# ==========================================
# Step 5: Smoke tests
# ==========================================

echo ""
echo "=== Step 5: Smoke tests ==="

sleep 5

# Test backend
BACKEND=$(curl -s -o /dev/null -w "%{http_code}" "http://${NEW_IP}:8000/health" 2>/dev/null || echo "000")
if [ "$BACKEND" = "200" ]; then
    echo "  [PASS] Backend API: http://${NEW_IP}:8000"
else
    echo "  [FAIL] Backend API: HTTP $BACKEND"
fi

# Test mobile
MOBILE=$(curl -s -o /dev/null -w "%{http_code}" "http://${NEW_IP}:3000" 2>/dev/null || echo "000")
if [ "$MOBILE" = "200" ] || [ "$MOBILE" = "307" ]; then
    echo "  [PASS] Mobile frontend: http://${NEW_IP}:3000"
else
    echo "  [FAIL] Mobile frontend: HTTP $MOBILE"
fi

# Test PC
PC=$(curl -s -o /dev/null -w "%{http_code}" "http://${NEW_IP}:8501" 2>/dev/null || echo "000")
if [ "$PC" = "200" ]; then
    echo "  [PASS] PC frontend: http://${NEW_IP}:8501"
else
    echo "  [FAIL] PC frontend: HTTP $PC"
fi

# Test login
LOGIN=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://${NEW_IP}:8000/api/v1/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin&password=admin123" 2>/dev/null || echo "000")
if [ "$LOGIN" = "200" ]; then
    echo "  [PASS] Auth login works"
else
    echo "  [FAIL] Auth login: HTTP $LOGIN"
fi

# ==========================================
# Summary
# ==========================================

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  RECOVERY COMPLETE                           ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  Backend:  http://${NEW_IP}:8000              "
echo "║  Mobile:   http://${NEW_IP}:3000              "
echo "║  PC:       http://${NEW_IP}:8501              "
echo "║  API Docs: http://${NEW_IP}:8000/docs         "
echo "║                                              ║"
echo "║  Credentials:                                ║"
echo "║    admin / admin123                          ║"
echo "║    recepcion / recep123                      ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "IMPORTANT: If the IP changed, update:"
echo "  1. deploy_staging.sh (IP variable)"
echo "  2. CLAUDE.md (if IP is referenced)"
echo "  3. Any DNS records pointing to the old IP"
echo ""
