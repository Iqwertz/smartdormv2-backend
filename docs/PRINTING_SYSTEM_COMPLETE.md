# SmartDorm Printing & Scanning System - Complete Documentation

Complete documentation for the SmartDorm printing and scanning system, including setup, configuration, maintenance, and troubleshooting.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Initial Setup](#initial-setup)
4. [Daily Startup](#daily-startup)
5. [Configuration](#configuration)
6. [Data Model](#data-model)
7. [Troubleshooting](#troubleshooting)
8. [Maintenance](#maintenance)

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

# Copy scan service script
# (From backend: scripts/pi_scan_service.py)
# Or create directly (see scripts/pi_scan_service.py)

# Make executable
chmod +x pi_scan_service.py

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
ExecStart=/srv/smartdorm/venv/bin/python /srv/smartdorm/pi_scan_service.py
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

# Pi Scan Service
PI_SCAN_SERVICE_URL=http://192.168.0.124:5000  # Scan service URL
```

#### 2.2 Install Dependencies

```bash
cd smartdormv2-backend
source venv/bin/activate
pip install pycups pypdf
```

**Important:** `pycups` requires CUPS development libraries:
```bash
sudo apt-get install -y libcups2-dev  # On WSL2/Server
```

#### 2.3 Database Migration

```bash
python manage.py migrate
```

#### 2.4 Create Device

```bash
python scripts/setup_device.py
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

---

## Daily Startup

After a restart, all components must be started:

### 1. Windows: Port Forwarding (PowerShell as Administrator)

**Using script:**
```powershell
cd C:\Users\Antonio\Tambaro\dev\schollheim\smartdormv2\smartdormv2-backend\scripts
.\wsl_port_forward.ps1
```

**Or manually:**
```powershell
$WSL_IP = (wsl hostname -I).Trim()
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$WSL_IP
```

**Note:** Must be executed again after each WSL2 restart!

### 2. WSL2: Django Backend

```bash
cd /home/tambaro/dev/schollheim/smartdormv2/smartdormv2-backend
./run-server.sh
# Or: source venv/bin/activate && python manage.py runserver 0.0.0.0:8000
```

### 3. Raspberry Pi: Services

```bash
ssh pi@192.168.0.124

# Start services (if not automatic)
sudo systemctl start cups smartdorm-scan-service

# Check status
sudo systemctl status cups smartdorm-scan-service
```

**Note:** Services start automatically on boot (after `enable`).

---

## Configuration

### CUPS Printer Configuration

#### Determine Printer Name
```bash
lpstat -p
# Output: Samsung_C1860_Series
```

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

**Using script (recommended):**
```bash
# Script automatically finds and configures scanner
cd /tmp
# Copy script from backend or create manually
chmod +x fix_scan_device_pi.sh
./fix_scan_device_pi.sh
```

### Backend Configuration

#### Environment Variables (`.env`)

```bash
# CUPS Server (Raspberry Pi)
CUPS_SERVER=192.168.0.124
CUPS_PRINTER_NAME=Samsung_C1860_Series

# Pi Scan Service
PI_SCAN_SERVICE_URL=http://192.168.0.124:5000
```

#### ALLOWED_HOSTS

In `settings.py`, the IP address of the Windows host must be included:
```python
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.0.106', ...]
```

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

**Important:** The data model development occurred in several steps:

1. **Migration 0006:** Initial creation (Device, PrintSession, PrintJob, Scan)
   - Created all four models
   - Device with single `price_per_page` field

2. **Migration 0007:** Translation
   - Translated all comments and help texts (German → English)
   - Translated status choices (German → English)
   - No structural changes

3. **Migration 0008:** Price model extension
   - Removed: `Device.price_per_page`
   - Added: `Device.price_per_page_color` (default 0.10 EUR)
   - Added: `Device.price_per_page_gray` (default 0.05 EUR)
   - Added: `PrintJob.color_mode` field (choices: 'Color', 'Gray', default: 'Color')

**Migration strategy:**
- First add new fields with defaults
- Then remove old field
- Existing jobs get `color_mode='Color'` (default)
- No automatic cost recalculation (preserves historical pricing)

---

## Troubleshooting

### Problem: Port Forwarding Not Working

**Symptoms:**
- Pi cannot reach backend
- `Connection timed out` errors

**Solution:**
1. PowerShell must be run as Administrator
2. Check if WSL2 is running: `wsl hostname -I`
3. Check if firewall rule exists: `Get-NetFirewallRule -DisplayName "*8000*"`
4. Verify port forwarding: `netsh interface portproxy show all`

**Windows Firewall Rule:**
```powershell
New-NetFirewallRule -DisplayName "Django Dev Server Port 8000" `
  -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Problem: Backend Not Reachable

**Check:**
```bash
# Backend running?
curl http://localhost:8000

# Backend listening on 0.0.0.0?
# In runserver: python manage.py runserver 0.0.0.0:8000
```

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

**Solution:**

1. **List available scanners:**
   ```bash
   scanimage -L
   ```

2. **Edit service file:**
   ```bash
   sudo nano /etc/systemd/system/smartdorm-scan-service.service
   ```

3. **Set `SCAN_DEVICE` to correct device** (from `scanimage -L`)

4. **Restart service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart smartdorm-scan-service
   ```

**Using script (recommended):**
```bash
# Script automatically finds and configures scanner
./fix_scan_device_pi.sh
```

**Common Issues:**

**USB device port changes:**
- Symptom: Device name changes after restart (e.g., `libusb:001:005` → `libusb:001:006`)
- Solution: Use network device instead (AirScan/WSD):
  ```bash
  scanimage -L | grep -i "samsung\|airscan"
  # Use the airscan:w0:... device
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
   - Use `scripts/clear_printing_data.py` to delete all printing data
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

**Reset all printing data:**
```bash
cd smartdormv2-backend
python scripts/clear_printing_data.py --yes
```

**Deletes:**
- All PrintSessions
- All PrintJobs (including costs)
- All Scans

**Preserves:**
- Device configuration (printer settings remain)

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

**Change prices:**
- Via admin interface: `/department/printing` → Tab "Einstellungen"
- Or directly in Django admin

**Disable printer:**
- Via admin interface: `/department/printing` → Tab "Übersicht" → "Deaktivieren"
- Or: `Device.is_active = False` in Django

### Database Backup

**Before major changes:**
```bash
python manage.py dumpdata smartdorm.PrintSession smartdorm.PrintJob smartdorm.Scan > printing_backup.json
```

**Restore:**
```bash
python manage.py loaddata printing_backup.json
```

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

# Create device
python scripts/setup_device.py

# Clear printing data
python scripts/clear_printing_data.py --yes

# Start server
./run-server.sh
```

### Windows

```powershell
# Port forwarding
.\scripts\wsl_port_forward.ps1

# Check port forwarding
netsh interface portproxy show all

# Check firewall rule
Get-NetFirewallRule -DisplayName "*8000*"
```

---

## API Endpoints

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

### Backend Scripts

- `scripts/clear_printing_data.py` - Delete all printing data
- `scripts/setup_device.py` - Create device in database
- `scripts/wsl_port_forward.ps1` - Port forwarding (Windows)
- `scripts/debug_printer_options.py` - Debug CUPS printer options

### Pi Scripts

- `scripts/pi_scan_service.py` - Scan service (HTTP server on Pi)
- `scripts/start_pi_services.sh` - Start all Pi services
- `scripts/fix_scan_device_pi.sh` - Fix scanner device configuration
- `scripts/fix_color_printing_pi.sh` - Fix color printing (PPD modification, deprecated)
- `scripts/switch_to_color_driver.sh` - Switch to Gutenprint driver (recommended)

### Important Files

**Backend:**
- `smartdorm/models.py` - Data model (Device, PrintSession, PrintJob, Scan)
- `smartdorm/views/printing_views.py` - API endpoints
- `smartdorm/utils/cups_utils.py` - CUPS communication
- `smartdorm/settings.py` - Configuration (CUPS_SERVER, CUPS_PRINTER_NAME)

**Pi:**
- `/etc/systemd/system/smartdorm-scan-service.service` - Scan service configuration
- `/etc/cups/ppd/Samsung_C1860_Series.ppd` - Printer PPD file (if using Generic PCL driver)

---

## Developer Checklist

- [ ] Raspberry Pi setup completed (CUPS, scanner, scan service)
- [ ] Backend configuration checked (`.env`, `ALLOWED_HOSTS`)
- [ ] Port forwarding configured (Windows)
- [ ] All services started (Backend, CUPS, scan service)
- [ ] Test print performed
- [ ] Test scan performed
- [ ] Logs understood (Backend, CUPS, scan service)
- [ ] Data model understood (Device, PrintSession, PrintJob, Scan)
- [ ] API endpoints known
- [ ] Cost calculation logic understood (no recalculation, only stored values)
- [ ] Page count extraction understood (PDF on upload, CUPS on completion)

---

**Last Updated:** 2025-12-18  
**Version:** 1.0
