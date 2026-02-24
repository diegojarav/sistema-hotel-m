# Remote Access Setup Guide — Tailscale + SSH

## Overview

This guide sets up secure remote access to the hotel PC from anywhere.
After setup, Diego can SSH into the hotel PC with: `ssh diego@hotel-monges`

**Tools used:**
- **Tailscale** — Free mesh VPN (works behind NAT, no port forwarding needed)
- **OpenSSH Server** — Built into Windows 10/11
- **RustDesk** — Backup remote desktop (emergency access if Tailscale is down)

---

## Step 1: Install Tailscale on BOTH Machines

### Dev Machine (Diego's PC)

1. Download from https://tailscale.com/download/windows
2. Install and run the installer
3. Click "Log in" in the system tray — authenticate with Google/GitHub account
4. Note your Tailscale IP: `tailscale ip -4` in PowerShell (will be `100.x.x.x`)

### Hotel PC

1. Download the same Tailscale installer
2. Install and log in with **the same account** as the dev machine
3. Both machines will now be on the same private network (tailnet)

### Assign a Friendly Hostname

In the Tailscale admin console (https://login.tailscale.com/admin/machines):
1. Find the hotel PC
2. Click "..." → "Edit machine name"
3. Set it to `hotel-monges`
4. Now the hotel PC is reachable as `hotel-monges` from any device on the tailnet

---

## Step 2: Enable SSH on Hotel PC

### Install OpenSSH Server (Windows)

Open **PowerShell as Administrator** and run:

```powershell
# Check if OpenSSH Server is available
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'

# Install it
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start the service
Start-Service sshd

# Set it to auto-start on boot
Set-Service -Name sshd -StartupType Automatic

# Verify it's running
Get-Service sshd
```

### Configure Firewall

```powershell
# Allow SSH through Windows Firewall
New-NetFirewallRule -Name "SSH" -DisplayName "OpenSSH Server (SSH)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

### Set Default Shell to PowerShell (optional but recommended)

```powershell
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
```

---

## Step 3: Test SSH Connection

From the **dev machine**, open a terminal:

```bash
# Connect via Tailscale hostname
ssh diego@hotel-monges

# Or via Tailscale IP (find it in admin console)
ssh diego@100.x.x.x
```

If asked about fingerprint, type `yes` to accept.

### SSH Key Setup (Optional but Recommended)

On the dev machine:

```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "diego@dev"

# Copy public key to hotel PC
# On Windows, manually append to C:\Users\diego\.ssh\authorized_keys on hotel PC
```

---

## Step 4: Install RustDesk (Emergency Backup)

In case Tailscale is down and you need visual remote desktop access:

1. Download RustDesk from https://rustdesk.com/
2. Install on **both** machines
3. Note the hotel PC's RustDesk ID and password
4. Save these credentials securely — use only if SSH is unreachable

---

## Step 5: Verify Everything Works

Run these checks from the dev machine:

```bash
# 1. Tailscale is connected
tailscale status

# 2. SSH works
ssh diego@hotel-monges "echo 'SSH OK'"

# 3. Can reach the API
ssh diego@hotel-monges "curl -s http://localhost:8000/health"

# 4. Can see service status
ssh diego@hotel-monges "sc query HotelMunich_Backend"
```

---

## Quick Reference — Remote Commands

```bash
# Connect to hotel PC
ssh diego@hotel-monges

# Check all services
ssh diego@hotel-monges "scripts\service_control.bat status"

# Deploy an update
ssh diego@hotel-monges "cd C:\path\to\hotel_munich && python scripts\deploy.py"

# View recent errors
ssh diego@hotel-monges "type backend\logs\hotel_munich_errors.log"

# Trigger manual backup
ssh diego@hotel-monges "cd backend && python backup_manager.py"

# View deployment history
ssh diego@hotel-monges "type logs\deployments.log"

# Restart all services
ssh diego@hotel-monges "scripts\service_control.bat restart-all"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ssh: connect to host hotel-monges: Connection refused` | SSH service not running. Call hotel staff to run: `net start sshd` |
| `tailscale status` shows hotel PC offline | PC is off or WiFi disconnected. Call hotel staff to check. |
| Can connect via Tailscale but not SSH | Firewall blocking port 22. Call hotel staff to run firewall rule command above. |
| Need emergency visual access | Use RustDesk with saved ID/password |
| Hotel internet down completely | System still works on LAN. Wait for internet to come back. |

---

## Security Notes

- Tailscale uses WireGuard encryption (military-grade)
- Only devices logged into YOUR Tailscale account can access the tailnet
- SSH should use key-based auth in production (disable password auth later)
- RustDesk password should be changed to a strong random one
- Never expose port 8000 directly to the internet — always go through Tailscale
