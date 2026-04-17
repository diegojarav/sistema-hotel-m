#!/bin/bash
# One-command staging deployment script
# Usage: npm run deploy:staging  (or: bash scripts/deploy_staging.sh)
set -e

ZONE="us-central1-a"
VM="hotel-munich-staging"

# Detect gcloud path (Windows Python workaround vs Linux)
if [ -f "C:/Users/diego/AppData/Local/Google/Cloud SDK/google-cloud-sdk/lib/gcloud.py" ]; then
    gcloud_cmd() {
        C:/Python314/python.exe "C:/Users/diego/AppData/Local/Google/Cloud SDK/google-cloud-sdk/lib/gcloud.py" "$@"
    }
elif command -v gcloud &> /dev/null; then
    gcloud_cmd() { gcloud "$@"; }
else
    echo "ERROR: gcloud CLI not found"
    exit 1
fi

gcloud_ssh() { gcloud_cmd compute ssh "$VM" --zone="$ZONE" --command="$1"; }

# Auto-detect VM external IP
IP=$(gcloud_cmd compute instances describe "$VM" --zone="$ZONE" --format="get(networkInterfaces[0].accessConfigs[0].natIP)" 2>/dev/null)
if [ -z "$IP" ]; then
    echo "ERROR: Could not detect VM IP. Is the VM running?"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     DEPLOYING TO STAGING                     ║"
echo "║     VM: $VM                                  ║"
echo "║     IP: $IP                                  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Step 1: Run tests locally
echo "=== Step 1: Running local tests ==="
(cd backend && python -m pytest tests/ -q --tb=short)
echo "  Tests passed"
echo ""

# Step 2: Push to public repo
echo "=== Step 2: Pushing to origin ==="
git push origin dev:main
echo "  Pushed dev -> origin/main"
echo ""

# Step 3: Deploy on VM
echo "=== Step 3: Deploying on VM ==="
gcloud_ssh "
  cd /opt/hotel_munich &&
  git fetch origin &&
  git reset --hard origin/main &&
  source venv/bin/activate &&
  pip install -r backend/requirements.txt -q &&
  echo 'NEXT_PUBLIC_API_URL=http://${IP}:8000' > frontend_mobile/.env.local &&
  sudo sed -i 's|CORS_ORIGINS=.*|CORS_ORIGINS=http://localhost:3000,http://localhost:8501,http://127.0.0.1:3000,http://127.0.0.1:8501,http://${IP}:3000,http://${IP}:8501|' backend/.env &&
  echo '--- Running DB migrations ---' &&
  python scripts/run_migrations.py &&
  cd frontend_mobile &&
  npm run build &&
  sudo systemctl restart hotel-backend hotel-mobile hotel-pc &&
  echo '' &&
  echo '=== Services restarted ===' &&
  echo ''
"

echo ""
echo "=== Deploy complete ==="
echo "  Mobile:  http://${IP}:3000"
echo "  PC:      http://${IP}:8501"
echo "  API:     http://${IP}:8000/docs"
echo ""
