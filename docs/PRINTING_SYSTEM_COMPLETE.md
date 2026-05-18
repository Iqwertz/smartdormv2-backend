# SmartDorm Printing & Scanning System - Complete Documentation

Complete documentation for the SmartDorm printing and scanning system, including setup, configuration, maintenance, and troubleshooting.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Initial Setup](#initial-setup)
4. [Daily Startup](#daily-startup)
5. [Production Deployment](#production-deployment)
6. [Configuration](#configuration)
7. [Data Model](#data-model)
8. [Troubleshooting](#troubleshooting)
9. [Maintenance](#maintenance)

---

## System Overview

The SmartDorm Printing & Scanning System consists of three main components:

1. **Django Backend** (WSL2/Server)
   - Manages sessions, print jobs, and scans
   - Communicates with CUPS on the Raspberry Pi
   - Provides REST API for frontend

2. **Raspberry Pi** (Print Server)
   - **CUPS** (Common Unix Printing System) - Print server
   - **Scan Service** (Python) - Monitors scanner and sends scans to backend
   - Connected to Samsung Xpress C1860FW (printer/scanner)

3. **Frontend** (React)
   - Tenant interface: Print, scan, cost overview
   - Admin interface: Device management, billing

---

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Frontend │ ────────> │ Django       │ ───────> │ CUPS        │
│   (React)   │  HTTP    │ Backend      │  IPP     │ (Raspberry  │
│             │          │ (WSL2/Server)│          │  Pi)        │
└─────────────┘          └──────────────┘          └─────────────┘
                               │                          │
                               │                          │
                               │ HTTP                     │ USB/Network
                               │                          │
                               ▼                          ▼
                        ┌──────────────┐         ┌─────────────┐
                        │ Scan-Service  │ <──────> │ Samsung      │
                        │ (Raspberry Pi)│  HTTP   │ C1860FW      │
                        └──────────────┘          └─────────────┘
```

**Data Flow:**
- **Printing:** Frontend → Backend → CUPS → Printer
- **Scanning:** Scanner → Scan Service → Backend → Frontend

---

## Initial Setup

### Prerequisites

- Windows with WSL2
- Raspberry Pi with Raspberry Pi OS
- Samsung Xpress C1860FW printer/scanner
- Network connection between all components

### Step 1: Raspberry Pi Setup

#### 1.1 CUPS Installation and Printer Configuration

```bash
# On Raspberry Pi:
sudo apt update
sudo apt install -y cups

# Configure CUPS for network access
sudo cupsctl --share-printers --remote-any
sudo systemctl restart cups

# Connect printer via USB and add to CUPS
# Via web interface: http://<pi-ip>:631
# Or via command line:
lpadmin -p Samsung_C1860_Series \
  -E \
  -v usb://Samsung/C1860%20Series \
  -m "gutenprint.5.3://samsung-clp-660n/expert" \
  -L "SmartDorm Printer"

# Note printer name (needed for CUPS_PRINTER_NAME)
lpstat -p
```

**Important:** Use the **Gutenprint driver** for color printing support!

#### 1.2 Scanner Configuration

```bash
# Install SANE (scanner backend)
sudo apt install -y sane sane-utils

# List available scanners
scanimage -L

# Test scan
scanimage -d "xerox_mfp:libusb:001:005" --test
# (Replace with device from scanimage -L)
```

#### 1.3 Scan Service Installation

```bash
# Create directory
sudo mkdir -p /srv/smartdorm
cd /srv/smartdorm

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install requests flask

# Copy scan service from Pi repo (smartdorm-print-server): scan_service.py
# See Pi repo for the file and install instructions.

chmod +x scan_service.py

# Create systemd service
sudo nano /etc/systemd/system/smartdorm-scan-service.service
```

**Service file content:**
```ini
[Unit]
Description=SmartDorm Scan Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/srv/smartdorm
Environment="PATH=/srv/smartdorm/venv/bin"
Environment="SMARTDORM_API_BASE=http://192.168.0.106:8000/api"
Environment="SCAN_DEVICE=xerox_mfp:libusb:001:005"
ExecStart=/srv/smartdorm/venv/bin/python /srv/smartdorm/scan_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Activate service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable smartdorm-scan-service
sudo systemctl start smartdorm-scan-service
```

### Step 2: Backend Configuration

#### 2.1 Environment Variables

**In `smartdormv2-backend/.env`:**
```bash
# CUPS configuration
CUPS_SERVER=192.168.0.124  # IP address of Raspberry Pi
CUPS_PRINTER_NAME=Samsung_C1860_Series  # Name from lpstat -p
# Pi Scan Service (for scan uploads)
PI_SCAN_SERVICE_URL=http://192.168.0.124:5000
```

#### 2.2 Install Dependencies

```bash
cd smartdormv2-backend
source venv/bin/activate
pip install pycups pypdf
```

**Important:** `pycups` requires CUPS development libraries on WSL2/Server:
```bash
sudo apt-get install -y libcups2-dev
```

#### 2.3 Database Migration

```bash
python manage.py migrate
```

#### 2.4 Create Device

```bash
python scripts_printing_system/setup_device.py
```

Or manually in Django Admin/Shell:
- Name: "Samsung Xpress C1860FW"
- Location: "Creative Department Room"
- Department: Select corresponding department
- CUPS Printer Name: `Samsung_C1860_Series`
- Price per page (Color): 0.10 EUR
- Price per page (Gray): 0.05 EUR

### Step 3: Frontend Configuration

No special configuration needed - frontend uses the backend API.

## Daily Startup

After a restart, all components must be started:

### 1. Windows: Port Forwarding (PowerShell as Administrator)

**Manually (or run a port-forward script if you have one):**
```powershell
$WSL_IP = (wsl hostname -I).Trim()
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$WSL_IP
```

**Note:** Must be executed again after each WSL2 restart!

### 2. WSL2: Django Backend

```bash
cd smartdormv2-backend   # or your backend project path
./run-server.sh
# Or: source venv/bin/activate && python manage.py runserver 0.0.0.0:8000
```

### 3. Raspberry Pi: Services

On the Pi, ensure CUPS and the scan service are running (they start automatically if you ran `systemctl enable` during setup):

```bash
ssh pi@<pi-ip>

# Start services if not automatic
sudo systemctl start cups smartdorm-scan-service

# Check status
sudo systemctl status cups smartdorm-scan-service
```

---

## API Endpoints (Reference)

### Tenant Endpoints

- `GET /api/tenants/printing/device-status/` - Device status
- `GET /api/tenants/printing/my-costs/` - My costs
- `GET /api/tenants/printing/my-sessions/` - My sessions
- `GET /api/tenants/printing/my-scans/` - My scans
- `POST /api/tenants/printing/sessions/start/` - Start session
- `POST /api/tenants/printing/sessions/{id}/end/` - End session
- `POST /api/tenants/printing/sessions/{id}/print/` - Create print job
  - Requires: `multipart/form-data` with `file`, `color_mode`, `copies`
- `POST /api/tenants/printing/sessions/{id}/scan/start/` - Start scan
- `GET /api/tenants/printing/sessions/{id}/` - Session details (with jobs and scans)
- `GET /api/tenants/printing/scans/{id}/download/` - Download scan

### Admin Endpoints

- `GET /api/printing/device/{id}/overview/` - Device overview (status, active session, statistics)
- `GET /api/printing/device/{id}/statistics/` - Detailed statistics
- `PUT /api/printing/device/{id}/settings/` - Update settings (prices, max session duration)
- `POST /api/printing/device/{id}/toggle-active/` - Toggle device active/inactive
- `POST /api/printing/device/{id}/terminate-session/` - Terminate active session
- `GET /api/printing/device/{id}/history/` - Device history (sessions, jobs)
- `GET /api/printing/tenant-billing-overview/` - Billing overview (all tenants with costs)

### Pi Endpoints (No Authentication Required)

- `GET /api/printing/active-session/` - Query active session
- `POST /api/printing/scans/` - Upload scan (from Pi scan service)

---

## Files and Scripts

### Backend (this repo)

- `scripts_printing_system/setup_device.py` - Create print device in database (run once per environment)
- Port forwarding: use the manual `netsh` commands in "Daily Startup" (or your own script if you have one)

### Pi (separate repo: smartdorm-print-server)

The Pi runs only the scan service. The Pi repo contains:
- `scan_service.py` - HTTP service that receives scan requests and uploads PDFs to the backend (deployed to `/srv/smartdorm/scan_service.py` on the Pi)
- systemd unit file - installed as `/etc/systemd/system/smartdorm-scan-service.service`
- `install.sh` and README - for setting up a fresh Pi

On the Pi you will only have: `/srv/smartdorm/scan_service.py`, `/srv/smartdorm/venv/`, and the systemd unit. No other SmartDorm scripts on the Pi.

### Important code (backend)

- `smartdorm/models.py` - Data model (Device, PrintSession, PrintJob, Scan)
- `smartdorm/views/printing_views.py` - API endpoints
- `smartdorm/utils/cups_utils.py` - CUPS communication
- `smartdorm/settings.py` - Configuration (CUPS_SERVER, CUPS_PRINTER_NAME, PI_SCAN_SERVICE_URL)

---

## Developer Checklist

- [ ] Raspberry Pi setup completed (CUPS, scanner, scan service)
- [ ] Backend configuration checked (`.env`, `ALLOWED_HOSTS`)
- [ ] Port forwarding configured (Windows, development only)
- [ ] All services started (Backend, CUPS, scan service)
- [ ] Test print performed
- [ ] Test scan performed
- [ ] Logs understood (Backend, CUPS, scan service)
- [ ] Data model understood (Device, PrintSession, PrintJob, Scan)
- [ ] API endpoints known
- [ ] Cost calculation logic understood (no recalculation, only stored values)
- [ ] Page count extraction understood (PDF on upload, CUPS on completion)
- [ ] Production deployment steps understood (Pi static IP, backend URL on Pi, backend .env with Pi IP, SSH via main network)

---

**Last Updated:** 2026-02-14 · **Version:** 1.1

## Production Deployment

This section describes how to deploy the printing system in a live environment (e.g. a dorm) where the backend runs on a server and the Pi is placed in a dedicated printing room, both on the same building network.

### Production Overview

- **Network:** The building has a main network. Each room has a LAN port with a **static IP** assigned to that port (typically provided on a sheet when the room is assigned).
- **Backend:** Runs on a server on the main network (reachable from the building and possibly from outside).
- **Pi:** Placed in the printing room, connected to the room's LAN port. The Pi must use the **static IP of that room** so the backend can reach it (CUPS, scan service). No port forwarding is needed; Pi and server are on the same LAN.
- **Configuration:** The Pi is prepared (at home or in your room); then moved to the printing room and connected. The production backend's `.env` is set to the Pi's IP (the room's static IP).

### Part 1: Prepare the Pi (Before Moving to the Printing Room)

Do this with the Pi on your desk (e.g. connected to your router), as during initial setup.

#### 1.1 Set Backend URL to Production

The scan service on the Pi uploads scans to the backend. It must use the **production backend URL**.

**On the Pi:**
```bash
sudo nano /etc/systemd/system/smartdorm-scan-service.service
```

Set the line:
```ini
Environment="SMARTDORM_API_BASE=https://YOUR-PROD-BACKEND-URL/api"
```
Example: `https://smartdorm-api.example.org/api`. Use the URL reachable from the building network. Then: `sudo systemctl daemon-reload && sudo systemctl restart smartdorm-scan-service`.

#### Enable Color Printing

**Important:** Use the **Gutenprint driver** for color printing!

```bash
# Install Gutenprint
sudo apt install -y printer-driver-gutenprint

# Add printer with Gutenprint driver
lpadmin -x Samsung_C1860_Series
lpadmin -p Samsung_C1860_Series \
  -E \
  -v usb://Samsung/C1860%20Series \
  -m "gutenprint.5.3://samsung-clp-660n/expert" \
  -L "SmartDorm Printer"

# Check color options
lpoptions -p Samsung_C1860_Series -l | grep -i color
# Should show: ColorModel/Color Model: Gray Black *RGB CMY CMYK ...
```

#### Check Printer Options
```bash
lpoptions -p Samsung_C1860_Series -l
```

**Available color options:**
- `ColorModel` with values: `Gray`, `Black`, `RGB`, `CMY`, `CMYK`
- Default: Usually `RGB` or `CMYK` for color

**Backend sends both options for maximum compatibility:**
- `print-color-mode=color` (IPP standard)
- `ColorModel=CMYK` (PPD-specific)

### Scanner Configuration

#### List Available Scanners
```bash
scanimage -L
```

**Example output:**
```
device `xerox_mfp:libusb:001:005' is a Xerox WorkCentre MFP Scanner
device `airscan:w0:Samsung C1860 Series (SEC8425192A15C2)' is a Samsung C1860 Series ip
```

**Device Types:**
- **USB Scanner:** `xerox_mfp:libusb:001:005` - Direct USB connection, stable but port may change
- **Network Scanner:** `airscan:w0:Samsung C1860 Series (SEC8425192A15C2)` - Network device, more stable

**Recommendation:** Use network device (AirScan) if available for better stability.

#### Configure Scanner Device in Service

**Edit service file:**
```bash
sudo nano /etc/systemd/system/smartdorm-scan-service.service
```

**Find line:**
```ini
Environment="SCAN_DEVICE=xerox_mfp:libusb:001:005"
```

**Change to desired device** (from `scanimage -L`)

**Restart service:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart smartdorm-scan-service
```

#### 1.2 Scanner Device (SCAN_DEVICE)

Ensure `SCAN_DEVICE` in the same service file matches the output of `scanimage -L` (with the printer/scanner connected). If you move the Pi and the USB port changes, you may need to run `scanimage -L` again on site and update `SCAN_DEVICE` (see [Scanner Configuration](#scanner-configuration)).

#### 1.3 Optional: Preconfigure Static IP for the Printing Room

If you already know the **printing room's static IP** (from a sheet or admin), you can set it on the Pi now so that when you plug the Pi into that room's port, it uses the correct IP immediately. If you do not know it yet, configure the static IP on site (Part 3). For how to set the static IP, see [Part 2: Static IP on the Pi](#part-2-static-ip-on-the-pi).

#### 1.4 Verify Before Moving

```bash
sudo systemctl status cups smartdorm-scan-service
lpstat -p
scanimage -L
```
All should show the printer and scanner correctly.

---

### Part 2: Static IP on the Pi

In the live environment, the Pi is connected to a room LAN port that has a **fixed static IP**. The Pi must be configured to use that IP; the building network often does not provide DHCP for that port, or expects the device to use the assigned static IP.

#### Which Networking Stack Does the Pi Use?

Raspberry Pi OS can use different networking stacks. Check on the Pi:

```bash
systemctl is-active NetworkManager
systemctl is-active dhcpcd
ls /etc/netplan/
```

- **NetworkManager active** → Use **nmtui** (below).
- **dhcpcd active** (and NetworkManager not active) → Edit `/etc/dhcpcd.conf`: add `interface eth0`, `static ip_address=.../24`, `static routers=...`, then `sudo systemctl restart dhcpcd`.
- **Netplan config present** (`/etc/netplan/*.yaml`) → Edit the YAML file with `addresses`, `routes`, then `sudo netplan apply`.

#### Setting Static IP with NetworkManager (nmtui)

If `systemctl is-active NetworkManager` prints `active`:

1. Run:
   ```bash
   sudo nmtui
   ```
2. Choose **Edit a connection** → select the **Ethernet** connection (e.g. eth0) → **Edit**.
3. Set **IPv4 CONFIGURATION** to **Manual**.
4. Under **Addresses**, add the room's static IP with prefix, e.g. `10.50.2.15/24` (use the IP from the room's sheet; `/24` is typical for subnet 255.255.255.0).
5. Set **Gateway** to the value from the sheet (e.g. `10.50.2.1`).
6. **OK** → **Back** → **Quit**.
7. If needed, activate the connection:
   ```bash
   sudo nmcli connection up "eth0"
   ```
   (Connection name may differ; check in nmtui.)
8. Verify:
   ```bash
   ip addr show eth0
   ```

---

### Part 3: On Site (Printing Room)

Get the printing room sheet (static IP, gateway). Connect the Pi to the room LAN port and the printer via USB. On the Pi: set the static IP (see Part 2), run `scanimage -L` and update `SCAN_DEVICE` in the scan service file if the device string changed, then restart the scan service. Note the Pi’s IP for the backend `.env` (Part 4).

### Part 4: Backend Production Configuration

On the **server** where the SmartDorm backend runs:

1. **Environment variables:** In the backend's `.env` (or equivalent), set:
   ```bash
   CUPS_SERVER=<printing-room-static-IP>
   CUPS_PRINTER_NAME=Samsung_C1860_Series
   PI_SCAN_SERVICE_URL=http://<printing-room-static-IP>:5000
   ```
   Replace `<printing-room-static-IP>` with the IP from the printing room sheet (the same IP configured on the Pi).
2. **ALLOWED_HOSTS:** Ensure the Django `ALLOWED_HOSTS` includes the server's hostname/IP as used in production.
3. **Restart the backend** so the new environment variables are loaded.

---

### Part 5: SSH Access When the Pi Is in Another Room

During development the Pi and your laptop are often on the same router (same subnet). In production the Pi is in the printing room with a static IP on the **main network**. To SSH into the Pi from your laptop, the **laptop must also be on the main network**; otherwise it cannot reach the Pi's IP.

- **Correct:** Plug the **laptop** into a **room LAN port** (e.g. in your room) and configure the laptop with **that room's static IP** (as on your room's sheet). Then the laptop is on the main network. You can run:
  ```bash
  ssh pi@<printing-room-static-IP>
  ```
- **Wrong:** Using the laptop over **Wi‑Fi or cable via your room's router** usually puts the laptop in a private subnet (e.g. 192.168.x.x). The Pi is on the main network (e.g. 10.50.x.x). From that private subnet you typically cannot reach the Pi unless the network explicitly allows it (e.g. special routing). So for reliable SSH, use the laptop on the main network via the wall port.

**Summary:** Laptop on main network (wall port + room's static IP) → SSH to Pi's IP works. Laptop behind room router → often no route to Pi.

---

### Part 6: Optional – Access Point in the Printing Room

If the printing room has **only one LAN port** and you want both the Pi and your laptop connected (e.g. to configure or SSH from the same room), an **access point (AP)** at that port can help.

**Requirements:**

- The AP must operate in **bridge / AP mode** (no NAT, no separate subnet). It should only extend the main network so that devices connected to it receive IPs from the main network (or you assign the static IP manually on the Pi). If the AP acts as a router (NAT), the Pi would get a private IP and the backend on the main network could not reach it.
- **Pi and laptop must have different IPs.** The Pi uses the room's static IP (for the backend). The laptop needs another IP (e.g. from building DHCP via the AP, or another assigned address). Never assign the same IP to two devices.
- **Client-to-client traffic:** For SSH from laptop to Pi, the main network must allow communication between clients (laptop and Pi). Some networks block this; if you can reach other services on the main network from your laptop, client-to-client is often allowed. Test with `ssh pi@<pi-ip>`.

**Typical setup:** Wall port → AP (bridge mode) → Pi connected to AP's LAN port (static IP set on Pi); laptop connected via Wi‑Fi to AP (gets an IP from main network). Then SSH from laptop to Pi works if the network allows it.

---

### Production Deployment Checklist

| Step | Where | Action |
|------|--------|--------|
| 1 | Pi (at home/your room) | Set `SMARTDORM_API_BASE` to production backend URL in scan service file; verify `SCAN_DEVICE`; optionally set static IP for printing room if known. |
| 2 | Pi (at home/your room) | Confirm CUPS and scan service run; test printer and scanner. |
| 3 | On site | Get printing room sheet (static IP, gateway). Connect Pi to room LAN port and printer USB. |
| 4 | Pi (on site) | Set static IP (nmtui or other method) to room's static IP; run `scanimage -L` and update `SCAN_DEVICE` if needed; note Pi IP. |
| 5 | Backend server | Set `CUPS_SERVER` and `PI_SCAN_SERVICE_URL` in `.env` to Pi IP; restart backend. |
| 6 | Laptop | For SSH to Pi: connect laptop to main network (wall port + room static IP), then `ssh pi@<pi-ip>`. |

---

## Configuration

### Backend (`.env`)

```bash
CUPS_SERVER=192.168.0.124
CUPS_PRINTER_NAME=Samsung_C1860_Series
PI_SCAN_SERVICE_URL=http://192.168.0.124:5000
```

In `settings.py`, ensure **ALLOWED_HOSTS** includes the host used to reach the backend (e.g. Windows host IP in development: `'192.168.0.106'`).

### CUPS Printer Name

On the Pi, the name used in CUPS (and in `CUPS_PRINTER_NAME`) is shown by:
```bash
lpstat -p
```

### Scanner Device (SCAN_DEVICE)

The scan service reads the device from the systemd file: `/etc/systemd/system/smartdorm-scan-service.service` → `Environment="SCAN_DEVICE=..."`. Get the value from `scanimage -L` (use the quoted device string).

**When to update:** After a Pi reboot or after unplugging the scanner USB, the device string often changes. Update `SCAN_DEVICE` in the service file, then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart smartdorm-scan-service
```

Full procedure is in [Production Deployment](#scanner-configuration) (Scanner Configuration) and [Troubleshooting](#problem-scanner-not-working).

### Backend URL on the Pi (SMARTDORM_API_BASE)

Set in the same systemd file on the Pi. **Development:** URL the Pi can reach (e.g. Windows host LAN IP): `http://192.168.0.106:8000/api`. Port forwarding on Windows must be active. **Production:** Backend server URL (e.g. `https://smartdorm-api.example.org/api`). After changes: `sudo systemctl daemon-reload && sudo systemctl restart smartdorm-scan-service`.

---

## Data Model

### Models

#### Device
Represents a printer/scanner.

**Fields:**
- `name` - Display name (e.g., "Samsung Xpress C1860FW")
- `location` - Physical location
- `department` - Responsible department (ForeignKey)
- `is_active` - Global on/off switch
- `allow_new_sessions` - Allow new sessions (deprecated, use `is_active`)
- `price_per_page_color` - Price per color page (Decimal, default 0.10 EUR)
- `price_per_page_gray` - Price per black & white page (Decimal, default 0.05 EUR)
- `max_session_duration_minutes` - Maximum session duration (default 30)
- `cups_printer_name` - CUPS printer name (e.g., "Samsung_C1860_Series")

#### PrintSession
Container for print and scan activities.

**Fields:**
- `tenant` - Tenant who owns the session (ForeignKey)
- `device` - Device used (ForeignKey)
- `started_at` - Session start time (auto)
- `ended_at` - Session end time (nullable)
- `status` - Session status: `ACTIVE`, `COMPLETED`, `EXPIRED`, `TERMINATED`
- `external_id` - Unique identifier for API

#### PrintJob
Individual print job.

**Fields:**
- `session` - Associated session (ForeignKey)
- `tenant` - Tenant who printed (ForeignKey)
- `device` - Device used (ForeignKey)
- `filename` - Name of printed file
- `color_mode` - `'Color'` or `'Gray'` (default: `'Color'`)
- `pages` - Number of printed pages (nullable, updated after printing)
- `cost` - Cost in EUR (Decimal, nullable, calculated automatically)
- `status` - Job status: `PENDING`, `PRINTING`, `COMPLETED`, `FAILED`, `CANCELLED`
- `created_at` - Creation timestamp
- `completed_at` - Completion timestamp (nullable)
- `error_message` - Error message if failed (nullable)
- `cups_job_id` - CUPS job ID for status queries (nullable)
- `external_id` - Unique identifier for API

**Cost Calculation:**
- Automatically calculated in `save()` method
- Only for `COMPLETED` jobs
- Formula: `pages × price_per_page_color` (if `color_mode='Color'`) or `pages × price_per_page_gray` (if `color_mode='Gray'`)
- **Important:** Only stored costs are summed (no recalculation when prices change)

**Page Count:**
- Extracted from PDF on upload: `PDF pages × copies`
- Updated from CUPS when job completes: `job-impressions-completed` (preferred) or `job-media-sheets-completed`
- PDF value serves as fallback if CUPS doesn't provide page count

#### Scan
Scanned document (temporarily stored).

**Fields:**
- `session` - Associated session (ForeignKey)
- `tenant` - Tenant who scanned (ForeignKey)
- `device` - Device used (ForeignKey)
- `filename` - Scan filename
- `file_path` - Relative path to stored file
- `scanned_at` - Scan timestamp
- `external_id` - Unique identifier for API

### Migrations

The model evolved over migrations: 0006 (initial Device, PrintSession, PrintJob, Scan); 0007 (translations); 0008 (price_per_page_color / price_per_page_gray, PrintJob.color_mode). Costs are not recalculated when prices change.

---

## Troubleshooting

### Problem: Port Forwarding Not Working (Development)

**Symptoms:** Pi cannot reach backend; `Connection timed out` when uploading scans.

**Checks:**
1. Run PowerShell **as Administrator** for port forwarding.
2. WSL2 running: `wsl hostname -I`
3. Port forwarding: `netsh interface portproxy show all`
4. Windows firewall: allow inbound TCP 8000, e.g. `Get-NetFirewallRule -DisplayName "*8000*"` or create:
   ```powershell
   New-NetFirewallRule -DisplayName "Django Dev Server Port 8000" `
     -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
   ```
5. Backend listening on `0.0.0.0:8000`: `curl http://localhost:8000`

### Problem: CUPS Not Reachable

**Check:**
```bash
# On Pi:
sudo systemctl status cups
sudo netstat -tlnp | grep 631

# From backend:
curl http://<pi-ip>:631
```

**Solution:**
- Configure CUPS for network access: `sudo cupsctl --share-printers --remote-any`
- Firewall rule on Pi: `sudo ufw allow 631/tcp`

### Problem: Scanner Not Working

**Symptom:**
```
scanimage: open of device ... failed: Invalid argument
```
Or: Pi returns 500 and the scan never starts.

**Solution:**

1. **List available scanners:**
   ```bash
   scanimage -L
   ```
   If nothing is listed, check cable and port; wait a few seconds and try again.

2. **Edit service file:**
   ```bash
   sudo nano /etc/systemd/system/smartdorm-scan-service.service
   ```

3. **Set `SCAN_DEVICE`** to the device string from step 1 (the quoted part, e.g. `xerox_mfp:libusb:001:021`).

4. **Restart service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart smartdorm-scan-service
   ```

**When to update SCAN_DEVICE:** After a Pi reboot or unplugging the scanner USB, the device string often changes. See [Configuration – Scanner Device](#scanner-device-scan_device) for the procedure.

**Common issues:**

**USB device port changes:**
- Symptom: Device name changes after restart (e.g., `libusb:001:005` → `libusb:001:006`)
- Solution: Run `scanimage -L` and update `SCAN_DEVICE` in the service file as above. Alternatively use the network device (AirScan) if available for a stable name:
  ```bash
  scanimage -L | grep -i "samsung\|airscan"
  # Use the airscan:w0:... device in SCAN_DEVICE
  ```

**Permission denied:**
```bash
# Add user to scanner group
sudo usermod -a -G scanner pi
sudo systemctl restart smartdorm-scan-service
```

**Scanner not found:**
```bash
# Check USB devices
lsusb | grep -i "samsung\|xerox"

# Check SANE backends
sane-find-scanner

# Test scanner
scanimage --test
```

### Problem: Scan works but upload fails (No route to host)

**Symptom:** Backend log shows `Pi-Service error: 502` with a message like: upload failed, `Failed to establish a new connection: [Errno 113] No route to host` to `host='192.168.0.106', port=8000`. The scan runs on the Pi, but the Pi cannot reach the backend to upload the scan.

**Cause:** The scan service on the Pi calls the backend (e.g. `http://<backend-host>:8000/api/printing/scans/`). If that host is unreachable from the Pi, the upload fails.

**Development (backend on PC/WSL2):** Ensure port forwarding is set up so that traffic to the PC's IP on port 8000 reaches the backend in WSL2. Ensure the Windows firewall allows inbound connections on port 8000. The Pi's `SMARTDORM_API_BASE` (in the systemd service file) must be the URL the Pi can use to reach the backend (typically the PC's LAN IP, e.g. `http://192.168.0.106:8000/api`). Test from the Pi: `curl -s -o /dev/null -w "%{http_code}" http://<backend-ip>:8000/` should return 200 or 301/302.

**Production (backend on a server in the same network):** No port forwarding is needed. On the Pi, set `SMARTDORM_API_BASE` in `/etc/systemd/system/smartdorm-scan-service.service` to the server's URL (e.g. `http://192.168.1.10:8000/api`). Ensure the server allows connections from the Pi (firewall, `ALLOWED_HOSTS`). Then run `sudo systemctl daemon-reload` and `sudo systemctl restart smartdorm-scan-service`.

### Problem: Color Printing Not Working

**Symptom:** Printer prints in black & white despite "Color" selection in frontend

**Solution:**

1. **Check which driver is used:**
   ```bash
   sudo grep "*PCFileName\|*ModelName" /etc/cups/ppd/Samsung_C1860_Series.ppd
   ```

2. **If "Generic PCL" → Switch driver:**
   ```bash
   sudo apt install -y printer-driver-gutenprint
   lpadmin -x Samsung_C1860_Series
   lpadmin -p Samsung_C1860_Series \
     -E \
     -v usb://Samsung/C1860%20Series \
     -m "gutenprint.5.3://samsung-clp-660n/expert" \
     -L "SmartDorm Printer"
   ```

3. **Check color options:**
   ```bash
   lpoptions -p Samsung_C1860_Series -l | grep -i color
   # Should show: ColorModel/Color Model: Gray Black *RGB CMY CMYK ...
   ```

4. **Backend already sends both options:**
   - `print-color-mode=color` (IPP standard)
   - `ColorModel=CMYK` (PPD-specific)

**Alternative: PPD File Modification (Not Recommended)**

If driver switch is not possible, PPD file can be modified, but this is less reliable:
```bash
# Backup
sudo cp /etc/cups/ppd/Samsung_C1860_Series.ppd /etc/cups/ppd/Samsung_C1860_Series.ppd.backup

# Edit
sudo nano /etc/cups/ppd/Samsung_C1860_Series.ppd

# Change:
# *ColorDevice: False → True
# *DefaultColorSpace: Gray → RGB
# /cupsColorSpace 3/ → /cupsColorSpace 1/ (for RGB)

# Restart CUPS
sudo systemctl restart cups
```

**However, driver switch (Gutenprint) is the recommended solution.**

### Problem: Page Count Incorrect (1 instead of 2)

**Symptom:** 2-page document is counted as 1 page

**Solution:**
- Backend now extracts PDF page count on upload
- CUPS uses `job-impressions-completed` (logical pages) instead of `job-media-sheets-completed` (physical sheets)
- If CUPS doesn't provide page count, PDF-extracted value is used
- Page count calculation: `PDF pages × copies` (set on upload, updated from CUPS when job completes)

**Check:**
- Backend logs show: `PDF has X pages, copies=Y, total pages=X*Y`
- CUPS logs show: `Job X: sheets=Y, impressions=Z, using pages=Z`

**CUPS Page Count Details:**
- `job-media-sheets-completed` - Physical sheets of paper (may be less with duplex printing)
- `job-impressions-completed` - Logical pages printed (includes copies, preferred)

### Problem: Costs Incorrectly Calculated

**Symptom:** Costs don't match page count

**Check:**

1. **Color mode correct?**
   - Backend logs: `color_mode=Color` or `color_mode=Gray`
   - Price should be accordingly (0.10 EUR for Color, 0.05 EUR for Gray)

2. **Page count correct?**
   - Backend logs: `pages=X`
   - Cost = `pages × price_per_page_color/gray`

3. **Old jobs with incorrect costs?**
   - Delete printing data via Django admin or shell (PrintSession, PrintJob, Scan). A dedicated script is optional.
   - **Important:** Only stored costs are used (no recalculation)

**Cost Calculation Logic:**
- Costs are calculated when job status changes to `COMPLETED`
- Formula: `pages × price_per_page_color` (if `color_mode='Color'`) or `pages × price_per_page_gray` (if `color_mode='Gray'`)
- Costs are stored in database and never recalculated (preserves historical pricing)

### Problem: Billing Table Shows Duplicates

**Symptom:** Tenant appears multiple times in billing table

**Solution:**
- Already fixed: Billing table now aggregates all jobs per tenant
- Each tenant appears only once with total sum

### Problem: Scan Service Won't Start

**Check:**
```bash
# Service status
sudo systemctl status smartdorm-scan-service

# Logs
sudo journalctl -u smartdorm-scan-service -n 50

# Service file
sudo systemctl cat smartdorm-scan-service
```

**Common Problems:**
- Wrong `SCAN_DEVICE` → See "Scanner Not Working"
- Backend not reachable → Check `SMARTDORM_API_BASE` in service file
- Wrong Python path → Check `ExecStart` in service file

**Fix Scanner Device:**
```bash
# List available scanners
scanimage -L

# Edit service file
sudo nano /etc/systemd/system/smartdorm-scan-service.service
# Change SCAN_DEVICE environment variable

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart smartdorm-scan-service
```

### Problem: "Not Found" Error for /api/tenants/printing/device-status/

**Symptom:** 404 error when accessing device status endpoint

**Solution:**
- Endpoint now returns 200 OK with null/default values if no active device
- URL pattern moved before `sessions/<str:session_id>` to prevent conflicts
- Frontend handles "no device" state gracefully

---

## Maintenance

### Clear Printing Data

**Reset all printing data** (e.g. via Django shell):
```bash
cd smartdormv2-backend
python manage.py shell
```
```python
from smartdorm.models import PrintSession, PrintJob, Scan
PrintSession.objects.all().delete()
PrintJob.objects.all().delete()
Scan.objects.all().delete()
```

**Deletes:** All PrintSessions, PrintJobs, Scans. **Preserves:** Device configuration.

### Database Backup

Before major changes: `python manage.py dumpdata smartdorm.PrintSession smartdorm.PrintJob smartdorm.Scan > printing_backup.json`. Restore: `python manage.py loaddata printing_backup.json`.

### Monitor Logs

**Backend Logs (WSL2):**
```bash
# In terminal where Django is running
# Or: tail -f logs/django.log
```

**Pi Scan Service:**
```bash
sudo journalctl -u smartdorm-scan-service -f
```

**CUPS Logs:**
```bash
sudo tail -f /var/log/cups/error_log
```

### Change Device Settings

Change prices or disable the printer via the admin interface: `/department/printing` → "Einstellungen" (Settings) tab for prices; "Übersicht" (Overview) → "Deaktivieren" to disable. Or in Django admin: edit the Device.

---

## Important Commands

### Raspberry Pi

```bash
# CUPS status
sudo systemctl status cups
lpstat -p

# Scanner devices
scanimage -L

# Scan service
sudo systemctl status smartdorm-scan-service
sudo journalctl -u smartdorm-scan-service -f

# Printer options
lpoptions -p Samsung_C1860_Series -l | grep -i color

# Test print
echo "Test" | lp -d Samsung_C1860_Series -o ColorModel=CMYK
```

### Backend

```bash
# Migrations
python manage.py migrate

# Create device (once per environment)
python scripts_printing_system/setup_device.py

# Start server
./run-server.sh
```

For API endpoints, see [API Endpoints (Reference)](#api-endpoints-reference) above.
