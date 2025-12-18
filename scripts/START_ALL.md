# SmartDorm System - Komplette Start-Anleitung

Nach einem Neustart müssen alle Komponenten in dieser Reihenfolge gestartet werden:

---

##  Übersicht

1. **Windows:** Port-Forwarding einrichten (PowerShell als Admin)
2. **WSL2:** Django Backend starten
3. **Raspberry Pi:** CUPS & Scan-Service starten

---

## Schritt 1: Port-Forwarding (Windows PowerShell als Administrator)

** WICHTIG:** PowerShell **als Administrator** öffnen!

**Option A: Script ausführen (empfohlen)**
```powershell
cd C:\Users\Antonio\Tambaro\dev\schollheim\smartdormv2\smartdormv2-backend\scripts
.\wsl_port_forward.ps1
```

**Option B: Manuell**
```powershell
# WSL2 IP ermitteln
wsl hostname -I

# Port-Forwarding einrichten (ersetze 172.23.236.174 mit deiner WSL2 IP)
$WSL_IP = (wsl hostname -I).Trim()
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$WSL_IP

# Prüfen
netsh interface portproxy show all
```

** Erfolg:** Port-Forwarding ist aktiv (bleibt bis zum nächsten WSL2-Neustart)

---

## Schritt 2: Django Backend starten (WSL2)

**Terminal in WSL2 öffnen:**

```bash
cd /home/tambaro/dev/schollheim/smartdormv2/smartdormv2-backend

# Option A: Script verwenden
./run-server.sh

# Option B: Manuell
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

**Erfolg:** Backend läuft und ist erreichbar unter `http://localhost:8000` (in WSL) und `http://192.168.0.106:8000` (vom Pi aus)

---

##  Schritt 3: Raspberry Pi Services starten

**SSH zum Pi:**
```bash
ssh pi@192.168.0.124
```

**Option A: Script verwenden (empfohlen)**
```bash
# Script auf den Pi kopieren (einmalig) oder direkt ausführen:
cd /srv/smartdorm
# Falls das Script dort nicht existiert, von WSL2 kopieren:
# scp /home/tambaro/dev/schollheim/smartdormv2/smartdormv2-backend/scripts/start_pi_services.sh pi@192.168.0.124:/tmp/
# Dann auf dem Pi:
chmod +x /tmp/start_pi_services.sh
/tmp/start_pi_services.sh
```

**Option B: Manuell**
```bash
# CUPS starten (Print-Server)
sudo systemctl start cups
sudo systemctl enable cups

# Scanner-Gerät prüfen/korrigieren (falls Scan nicht funktioniert)
# Verfügbare Scanner auflisten:
scanimage -L

# Falls Gerät nicht korrekt ist, Service-Datei bearbeiten:
sudo nano /etc/systemd/system/smartdorm-scan-service.service
# Zeile finden: Environment="SCAN_DEVICE=..."
# Ändern zu einem Gerät aus scanimage -L
# Dann: sudo systemctl daemon-reload && sudo systemctl restart smartdorm-scan-service

# Scan-Service starten
sudo systemctl start smartdorm-scan-service
sudo systemctl enable smartdorm-scan-service

# Status prüfen
sudo systemctl status cups
sudo systemctl status smartdorm-scan-service
```

** Erfolg:** Beide Services laufen (`active (running)`)

---

##  System testen

### 1. Backend-Verbindung vom Pi testen:
```bash
# Auf dem Pi ausführen:
curl http://192.168.0.106:8000/api/printing/devices/
```

### 2. Frontend öffnen:
- Im Browser: `http://localhost:3000/print` (oder entsprechende URL)
- Scan-Funktion testen
- Druck-Funktion testen

### 3. Logs überwachen:

**Backend-Logs (WSL2):**
```bash
# Im Terminal wo Django läuft
```

**Pi-Scan-Service-Logs:**
```bash
# Auf dem Pi:
sudo journalctl -u smartdorm-scan-service -f
```

**CUPS-Logs:**
```bash
# Auf dem Pi:
sudo tail -f /var/log/cups/error_log
```

---

##  Bei Problemen

### Port-Forwarding funktioniert nicht:
- PowerShell wirklich als Administrator ausgeführt?
- WSL2 läuft? (`wsl hostname -I` sollte eine IP zurückgeben)
- Firewall-Regel vorhanden? (`Get-NetFirewallRule -DisplayName "*8000*"`)

### Backend nicht erreichbar:
- Django läuft? (`http://localhost:8000` im Browser testen)
- Port-Forwarding eingerichtet? (`netsh interface portproxy show all`)
- Backend hört auf `0.0.0.0:8000`? (nicht nur `127.0.0.1:8000`)

### Pi-Services starten nicht:
- Scan-Service-Logs prüfen: `sudo journalctl -u smartdorm-scan-service -n 50`
- CUPS-Logs prüfen: `sudo tail -50 /var/log/cups/error_log`
- Service-Datei prüfen: `sudo systemctl cat smartdorm-scan-service`

### Scanner funktioniert nicht:
- Verfügbare Scanner-Geräte auflisten: `scanimage -L`
- Service-Datei bearbeiten: `sudo nano /etc/systemd/system/smartdorm-scan-service.service`
  - Zeile finden: `Environment="SCAN_DEVICE=..."`
  - Ändern zu einem Gerät aus `scanimage -L`
  - Service neu starten: `sudo systemctl daemon-reload && sudo systemctl restart smartdorm-scan-service`

### Farbdruck funktioniert nicht:
- Prüfe welcher Treiber verwendet wird: `sudo grep "*PCFileName\|*ModelName" /etc/cups/ppd/Samsung_C1860_Series.ppd`
- Falls "Generic PCL" → Treiber wechseln zu Gutenprint:
  ```bash
  sudo apt install -y printer-driver-gutenprint
  lpadmin -x Samsung_C1860_Series
  lpadmin -p Samsung_C1860_Series \
    -E \
    -v usb://Samsung/C1860%20Series \
    -m "gutenprint.5.3://samsung-clp-660n/expert" \
    -L "SmartDorm Printer"
  ```
- Prüfe Color-Optionen: `lpoptions -p Samsung_C1860_Series -l | grep -i color`

---

## Quick-Start (alle Schritte in einem)

**Windows (PowerShell als Admin):**
```powershell
cd C:\Users\Antonio\Tambaro\dev\schollheim\smartdormv2\smartdormv2-backend\scripts
.\wsl_port_forward.ps1
```

**WSL2:**
```bash
cd /home/tambaro/dev/schollheim/smartdormv2/smartdormv2-backend
./run-server.sh
```

**Pi (SSH):**
```bash
sudo systemctl start cups smartdorm-scan-service
sudo systemctl status cups smartdorm-scan-service
```

---

##  Wichtige Hinweise

- **Port-Forwarding muss nach jedem WSL2-Neustart erneut eingerichtet werden**
- **Pi-Services starten automatisch beim Boot** (nach `enable`-Befehlen)
- **Backend muss manuell gestartet werden** (oder als Systemd-Service einrichten)
- **Alle IPs können sich ändern** (WSL2 IP ändert sich bei jedem Neustart)

---

**Viel Erfolg! 🚀**

