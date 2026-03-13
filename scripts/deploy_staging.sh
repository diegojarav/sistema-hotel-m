#!/bin/bash
# One-command staging deployment script
# Usage: npm run deploy:staging  (or: bash scripts/deploy_staging.sh)
set -e

ZONE="southamerica-east1-a"
VM="hotel-munich-staging"
IP="34.151.217.242"

# Detect gcloud path (Windows vs Linux)
if [ -f "C:/Users/diego/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd" ]; then
    GCLOUD="C:/Users/diego/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
elif command -v gcloud &> /dev/null; then
    GCLOUD="gcloud"
else
    echo "ERROR: gcloud CLI not found"
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
"$GCLOUD" compute ssh "$VM" --zone="$ZONE" --command="
  cd /opt/hotel_munich &&
  git fetch origin &&
  git reset --hard origin/main &&
  source venv/bin/activate &&
  pip install -r backend/requirements.txt -q &&
  cd frontend_mobile &&
  NEXT_PUBLIC_API_URL='http://${IP}:8000' npm run build &&
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
