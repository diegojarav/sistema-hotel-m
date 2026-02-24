# GCP Staging VM - Quick Setup Guide

## Prerequisites

- Google Cloud SDK (`gcloud`) installed on your dev machine
- GCP project with billing enabled (use $300 free credit)

## 1. Create the VM

```bash
# Authenticate (first time only)
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Create VM in Sao Paulo region
gcloud compute instances create hotel-munich-staging \
  --zone=southamerica-east1-b \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --boot-disk-type=pd-balanced \
  --tags=hotel-pms
```

## 2. Open Firewall Ports

```bash
gcloud compute firewall-rules create hotel-allow-ports \
  --allow=tcp:22,tcp:8000,tcp:8501,tcp:3000 \
  --target-tags=hotel-pms \
  --description="Hotel PMS staging ports"
```

## 3. SSH Into the VM

```bash
gcloud compute ssh hotel-munich-staging --zone=southamerica-east1-b
```

## 4. Clone and Setup

```bash
# Clone the repository
sudo mkdir -p /opt/hotel_munich
sudo chown $USER:$USER /opt/hotel_munich
git clone https://github.com/diegojarav/sistema-hotel-m.git /opt/hotel_munich

# Run the automated setup (installs everything)
cd /opt/hotel_munich
bash scripts/setup_gcp_staging.sh
```

The setup script handles:
- Python 3.12, Node.js 22 LTS
- Backend + frontend dependencies
- Next.js production build (with VM's external IP)
- Database initialization + seed data (property, rooms, 80-100 reservations, etc.)
- Default users (admin/admin123, recepcion/recep123)
- systemd services (auto-start, auto-restart)

## 5. Verify

After setup completes, access:

| Service | URL |
|---------|-----|
| Backend API | `http://<EXTERNAL_IP>:8000` |
| API Docs | `http://<EXTERNAL_IP>:8000/docs` |
| PC Frontend | `http://<EXTERNAL_IP>:8501` |
| Mobile Frontend | `http://<EXTERNAL_IP>:3000` |

Get external IP:
```bash
gcloud compute instances describe hotel-munich-staging \
  --zone=southamerica-east1-b \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

## Service Management

```bash
# On the VM:
bash scripts/service_control_linux.sh status
bash scripts/service_control_linux.sh restart
bash scripts/service_control_linux.sh logs              # all services
bash scripts/service_control_linux.sh logs hotel-backend # specific service
```

## Cost Control

```bash
# Stop VM when not testing (~$3.60/mo for disk only)
gcloud compute instances stop hotel-munich-staging --zone=southamerica-east1-b

# Resume when needed
gcloud compute instances start hotel-munich-staging --zone=southamerica-east1-b
```

| State | Monthly Cost |
|-------|-------------|
| Running 24/7 | ~$16/mo |
| Stopped | ~$3.60/mo |
| With $300 free credit | $0 for ~18 months |

## Updating After Code Changes

```bash
# SSH into VM
gcloud compute ssh hotel-munich-staging --zone=southamerica-east1-b

# Pull latest code
cd /opt/hotel_munich
git pull origin main

# Reinstall deps if changed
source venv/bin/activate
pip install -r backend/requirements.txt -q

# Rebuild Next.js if frontend changed
cd frontend_mobile
NEXT_PUBLIC_API_URL=http://<EXTERNAL_IP>:8000 npm run build

# Restart services
bash scripts/service_control_linux.sh restart
```

## Teardown

```bash
# Delete VM completely (stops all billing)
gcloud compute instances delete hotel-munich-staging --zone=southamerica-east1-b

# Delete firewall rules
gcloud compute firewall-rules delete hotel-allow-ports
```
