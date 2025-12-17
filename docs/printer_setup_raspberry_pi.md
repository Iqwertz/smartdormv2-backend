# Raspberry Pi Setup-Anleitung: Drucker & Scan-Monitor

## Übersicht

Diese Anleitung führt Schritt für Schritt durch die Einrichtung des Raspberry Pi als Printserver für den Samsung Xpress C1860FW Drucker.

**Voraussetzungen:**
- ✅ Raspberry Pi 4 Model B mit Raspberry Pi OS
- ✅ CUPS installiert und konfiguriert
- ✅ Drucker per USB angeschlossen und in CUPS hinzugefügt
- ✅ Testdruck erfolgreich durchgeführt

---

## Schritt 1: CUPS Netzwerk-Zugriff prüfen und konfigurieren

### 1.1 CUPS-Printer-Name ermitteln

**Auf dem Raspberry Pi:**
```bash
lpstat -p
```

**Ausgabe notieren:** Der angezeigte Drucker-Name.  
**Beispiel:** `Samsung_C1860_Series`  
**⚠️ WICHTIG:** Dieser Name muss später in SmartDorm `.env` als `CUPS_PRINTER_NAME` verwendet werden.

### 1.2 Prüfen ob SmartDorm-Backend auf CUPS zugreifen kann

**Auf SmartDorm-Backend-Server (oder lokal, falls möglich):**
```bash
# Ersetze <pi-ip> mit der IP-Adresse deines Raspberry Pi
curl http://<pi-ip>:631

# Sollte CUPS Web-Interface HTML zurückgeben
```

**Falls nicht erreichbar:**

### 1.3 CUPS Remote-Zugriff aktivieren

**Auf dem Raspberry Pi:**
```bash
sudo nano /etc/cups/cupsd.conf
```

**Suche nach der Zeile `Listen localhost:631` und ändere zu:**
```ini
Listen *:631
```

**Füge nach der Zeile `<Location />` hinzu (im entsprechenden Block):**
```ini
<Location />
  Order allow,deny
  Allow localhost
  Allow @LOCAL
  # Ersetze 192.168.1.0/24 mit deinem Netzwerk
  Allow 192.168.1.0/24
</Location>
```

**Alternative (einfacher, weniger sicher):**
```bash
sudo cupsctl --share-printers --remote-any
```

**CUPS neu starten:**
```bash
sudo systemctl restart cups
```

**Test:**
```bash
# Erneut vom Backend-Server testen:
curl http://<pi-ip>:631
```

### 1.4 Firewall prüfen (falls aktiv)

**Auf dem Raspberry Pi:**
```bash
# Prüfen ob Firewall aktiv:
sudo ufw status

# Falls aktiv, CUPS-Port erlauben:
sudo ufw allow 631/tcp

# Optional: Nur aus bestimmten Netzwerk erlauben:
sudo ufw allow from 192.168.1.0/24 to any port 631
```

---

## Schritt 2: Samba (SMB) Installation und Konfiguration

### 2.1 Samba installieren

```bash
sudo apt update
sudo apt install -y samba samba-common-bin
```

### 2.2 Scan-Ordner erstellen

```bash
# Erstelle Ordner-Struktur:
sudo mkdir -p /srv/scans/{inbox,processed,unassigned}

# Setze Berechtigungen (ersetze 'pi' mit deinem User):
sudo chown -R $USER:$USER /srv/scans
sudo chmod -R 755 /srv/scans

# Prüfe:
ls -la /srv/scans/
# Sollte zeigen: inbox/, processed/, unassigned/
```

### 2.3 Samba-Freigabe konfigurieren

```bash
sudo nano /etc/samba/smb.conf
```

**Füge am Ende der Datei hinzu:**
```ini
[scans]
   comment = SmartDorm Scan Inbox
   path = /srv/scans/inbox
   browseable = yes
   writable = yes
   guest ok = yes
   create mask = 0666
   directory mask = 0777
   force user = pi
```

**⚠️ WICHTIG:** Falls du einen anderen User als `pi` verwendest, hier anpassen.

**Samba-Konfiguration testen:**
```bash
sudo testparm
# Sollte keine Fehler zeigen
```

**Samba Service starten:**
```bash
sudo systemctl start smbd
sudo systemctl enable smbd
sudo systemctl restart smbd
```

### 2.4 Samba-Freigabe testen

```bash
# Prüfe ob Freigabe sichtbar:
smbclient -L localhost -N

# Sollte "scans" in der Liste zeigen

# Test-Zugriff:
smbclient //localhost/scans -N

# In der SMB-Shell:
# ls          # Liste Dateien
# put test.txt  # Datei hochladen (Test)
# exit
```

**Test-Datei erstellen:**
```bash
echo "Test" > /srv/scans/inbox/test.txt
smbclient //localhost/scans -N -c "ls"
# Sollte test.txt zeigen
```

---

## Schritt 3: Drucker Scan-to-SMB konfigurieren

### 3.1 Drucker-IP-Adresse ermitteln

**Am Drucker-Display:**
- Menu → Netzwerk → Netzwerk-Status
- IP-Adresse notieren (z.B. `192.168.1.XXX`)

**Oder im Netzwerk-Router nachsehen (nach MAC-Adresse des Druckers)**

### 3.2 Drucker Web-Interface öffnen

**Im Browser (vom Pi oder einem Computer im Netzwerk):**
```
http://<drucker-ip>
```

**Beispiel:** `http://192.168.1.150`

### 3.3 SMB-Scan-Profil konfigurieren

**Im Drucker-Web-Interface:**
1. Navigiere zu: **Scan** → **Network Scan** → **SMB** (oder ähnlich)
2. Klicke auf **Add** oder **Neu hinzufügen**
3. Fülle folgende Felder aus:

   - **Server-Name / IP-Adresse:** IP des Raspberry Pi (z.B. `192.168.1.100`)
   - **Freigabename / Share Name:** `scans`
   - **Benutzername:** (leer lassen, da Guest-Zugriff)
   - **Passwort:** (leer lassen)
   - **Ordner / Folder:** (leer lassen oder `inbox` - je nach Drucker-Menü)
   - **Dateiformat:** `PDF`
   - **Dateiname:** Automatisch generiert

4. **Speichern** oder **OK**

### 3.4 Test-Scan durchführen

1. **Am Drucker:**
   - Dokument auf Scanner legen
   - Scan-Button drücken
   - **Network Scan** oder **Scan-to-Network** wählen
   - Gespeichertes SMB-Profil auswählen
   - Scan starten

2. **Auf dem Raspberry Pi prüfen:**
   ```bash
   ls -la /srv/scans/inbox/
   # Sollte eine neue PDF-Datei zeigen (z.B. scan_001.pdf)
   ```

**✅ Wenn Datei erscheint:** Scan-Konfiguration erfolgreich!  
**❌ Wenn keine Datei:** Troubleshooting (siehe unten)

---

## Schritt 4: Python-Umgebung für Scan-Monitor

### 4.1 Python prüfen

```bash
python3 --version
# Sollte Python 3.x zeigen
```

### 4.2 Virtual Environment erstellen

```bash
# Erstelle Verzeichnis für SmartDorm:
mkdir -p /srv/smartdorm
cd /srv/smartdorm

# Virtual Environment erstellen:
python3 -m venv venv

# Aktivieren:
source venv/bin/activate

# Prompt sollte jetzt (venv) zeigen
```

### 4.3 Dependencies installieren

```bash
# Noch im venv (Prompt zeigt (venv)):
pip install --upgrade pip
pip install requests watchdog

# Prüfe Installation:
pip list
# Sollte requests und watchdog zeigen
```

---

## Schritt 5: Scan-Monitor Script erstellen

### 5.1 Script erstellen

**⚠️ WICHTIG:** Die Backend-URL wird erst nach Implementierung der SmartDorm-API feststehen.  
**Für jetzt:** Verwende die Dev-URL. Die kann später angepasst werden.

**URLs basierend auf SmartDorm-Deployment:**
- **Dev:** `http://smartdormv2-api-dev.schollheim.net/api`
- **Prod:** `http://api-smartdorm-v2.schollheim.net/api`

```bash
# Noch im /srv/smartdorm Verzeichnis:
nano scan_monitor.py
```

**Füge folgenden Code ein:**
```python
#!/usr/bin/env python3
"""
SmartDorm Scan Monitor
Überwacht /srv/scans/inbox/ und lädt neue Scans zu SmartDorm hoch
"""
import os
import time
import requests
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ⚠️ KONFIGURATION: Backend-URL
# Diese URL wird nach Implementierung der SmartDorm-API funktionieren
# Aktuell: Dev-URL (für Tests)
# Später: Auf Prod umstellen wenn bereit
SMARTDORM_API_BASE = "http://smartdormv2-api-dev.schollheim.net/api"  # DEV
# SMARTDORM_API_BASE = "http://api-smartdorm-v2.schollheim.net/api"  # PROD (später)

SCAN_INBOX = Path("/srv/scans/inbox")
SCAN_PROCESSED = Path("/srv/scans/processed")
SCAN_UNASSIGNED = Path("/srv/scans/unassigned")
POLL_INTERVAL = 2  # Sekunden warten bis File vollständig geschrieben ist

class ScanHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Warte kurz, bis File vollständig geschrieben ist
        time.sleep(POLL_INTERVAL)
        
        if not file_path.exists():
            return
        
        print(f"[{datetime.now()}] Neue Datei erkannt: {file_path.name}")
        
        try:
            # Frage SmartDorm nach aktiver Session
            response = requests.get(
                f"{SMARTDORM_API_BASE}/printing/active-session/",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('active'):
                    session_id = data['session_id']
                    print(f"  → Aktive Session gefunden: {session_id}")
                    
                    # Upload zu SmartDorm
                    with open(file_path, 'rb') as f:
                        files = {'file': (file_path.name, f, 'application/pdf')}
                        data_upload = {'session_id': session_id}
                        
                        upload_resp = requests.post(
                            f"{SMARTDORM_API_BASE}/printing/scans/",
                            files=files,
                            data=data_upload,
                            timeout=30
                        )
                        
                        if upload_resp.status_code == 201:
                            # Erfolgreich → nach processed verschieben
                            target = SCAN_PROCESSED / file_path.name
                            file_path.rename(target)
                            print(f"  ✅ Scan erfolgreich zugeordnet: {file_path.name}")
                        else:
                            print(f"  ❌ Upload fehlgeschlagen: {upload_resp.status_code} - {upload_resp.text}")
                            self._move_to_unassigned(file_path)
                else:
                    # Keine aktive Session
                    print(f"  ⚠️ Keine aktive Session")
                    self._move_to_unassigned(file_path)
            else:
                print(f"  ❌ API-Fehler: {response.status_code}")
                self._move_to_unassigned(file_path)
                
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Netzwerk-Fehler: {e}")
            self._move_to_unassigned(file_path)
        except Exception as e:
            print(f"  ❌ Unerwarteter Fehler: {e}")
            self._move_to_unassigned(file_path)
    
    def _move_to_unassigned(self, file_path):
        """Verschiebt Scan in unassigned-Ordner mit Timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(file_path.name)
        new_filename = f"{timestamp}_{name}{ext}"
        target = SCAN_UNASSIGNED / new_filename
        
        # Falls Datei bereits existiert, nummerieren
        counter = 1
        original_target = target
        while target.exists():
            name_part, ext = os.path.splitext(original_target.name)
            target = SCAN_UNASSIGNED / f"{name_part}_{counter}{ext}"
            counter += 1
        
        file_path.rename(target)
        print(f"  ⚠️ Scan ohne Session zugeordnet: {new_filename} → unassigned/")

def main():
    print("=" * 60)
    print("SmartDorm Scan Monitor")
    print("=" * 60)
    print(f"API: {SMARTDORM_API_BASE}")
    print(f"Überwache: {SCAN_INBOX}")
    print("=" * 60)
    
    event_handler = ScanHandler()
    observer = Observer()
    observer.schedule(event_handler, str(SCAN_INBOX), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n" + "=" * 60)
        print("Scan Monitor beendet.")
        print("=" * 60)
    
    observer.join()

if __name__ == '__main__':
    main()
```

**Speichern:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 5.2 Script ausführbar machen

```bash
chmod +x scan_monitor.py
```

### 5.3 Script manuell testen

```bash
# Virtual Environment aktivieren (falls nicht mehr aktiv):
source venv/bin/activate

# Script starten:
python scan_monitor.py
```

**In einem zweiten Terminal:**
```bash
# Test-Datei in inbox/ erstellen:
echo "test" > /srv/scans/inbox/test_manual.txt
```

**Im ersten Terminal sollte erscheinen:**
- `[Zeitstempel] Neue Datei erkannt: test_manual.txt`
- `⚠️ Keine aktive Session` (da noch keine Session aktiv)
- Datei sollte nach `unassigned/` verschoben werden

**Script beenden:** `Ctrl+C`

---

## Schritt 6: Systemd-Service für Scan-Monitor

### 6.1 Service-Datei erstellen

```bash
sudo nano /etc/systemd/system/smartdorm-scan-monitor.service
```

**Füge ein:**
```ini
[Unit]
Description=SmartDorm Scan Monitor
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/srv/smartdorm
Environment="PATH=/srv/smartdorm/venv/bin"
ExecStart=/srv/smartdorm/venv/bin/python /srv/smartdorm/scan_monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Service ist für User `pi` konfiguriert**

### 6.2 Service aktivieren

```bash
# Systemd neu laden:
sudo systemctl daemon-reload

# Service aktivieren (startet automatisch bei Boot):
sudo systemctl enable smartdorm-scan-monitor

# Service starten:
sudo systemctl start smartdorm-scan-monitor

# Status prüfen:
sudo systemctl status smartdorm-scan-monitor
```

**Sollte `active (running)` zeigen**

### 6.3 Logs anschauen

```bash
# Live-Logs:
sudo journalctl -u smartdorm-scan-monitor -f

# Letzte 50 Zeilen:
sudo journalctl -u smartdorm-scan-monitor -n 50
```

---

## Schritt 7: Vollständiger Test

### 7.1 ⚠️ WICHTIG: SmartDorm-API muss implementiert sein

**Bevor du diesen Test durchführen kannst, müssen die folgenden API-Endpunkte in SmartDorm implementiert sein:**
- `GET /api/printing/active-session/` (für Pi, ohne Authentifizierung)
- `POST /api/printing/scans/` (für Pi, ohne Authentifizierung)

**Diese Endpunkte werden im nächsten Schritt (SmartDorm-Implementierung) erstellt.**

**Du kannst die Schritte 1-6 bereits durchführen, aber der vollständige Test (Schritt 7) muss warten, bis die API implementiert ist.**

### 7.2 Test-Workflow (nach API-Implementierung)

1. **In SmartDorm-Web:** Session starten
2. **Am Drucker:** Test-Scan durchführen
3. **Auf Pi prüfen:**
   ```bash
   # Logs anschauen:
   sudo journalctl -u smartdorm-scan-monitor -f
   
   # Sollte zeigen:
   # - Neue Datei erkannt
   # - Aktive Session gefunden
   # - Upload erfolgreich
   # - Datei nach processed/ verschoben
   ```
4. **In SmartDorm-Web:** Scan sollte in der Session-Liste erscheinen

---

## Troubleshooting

### Problem: CUPS nicht vom Backend erreichbar

**Prüfen:**
```bash
# Auf Pi:
sudo systemctl status cups
sudo netstat -tlnp | grep 631

# Vom Backend-Server:
curl http://<pi-ip>:631
```

**Lösung:**
- Firewall-Regel prüfen
- CUPS `cupsd.conf` prüfen (Listen *:631)

### Problem: SMB-Freigabe nicht erreichbar

**Prüfen:**
```bash
# Auf Pi:
sudo systemctl status smbd
smbclient -L localhost -N
```

**Lösung:**
- Samba-Konfiguration prüfen (`sudo testparm`)
- Berechtigungen prüfen (`ls -la /srv/scans/inbox/`)

### Problem: Scan landet nicht in inbox/

**Prüfen:**
- Drucker-IP korrekt?
- SMB-Freigabename korrekt? (sollte `scans` sein)
- Drucker kann Netzwerk-Freigaben erreichen?

**Test:**
```bash
# Von einem anderen Computer im Netzwerk:
# Windows: \\<pi-ip>\scans
# Linux: smbclient //<pi-ip>/scans -N
```

### Problem: Scan-Monitor erkennt Dateien nicht

**Prüfen:**
```bash
# Service-Status:
sudo systemctl status smartdorm-scan-monitor

# Logs:
sudo journalctl -u smartdorm-scan-monitor -n 100
```

**Lösung:**
- Berechtigungen prüfen (User sollte auf `/srv/scans/inbox/` schreiben können)
- Python-Script manuell testen

### Problem: Upload zu SmartDorm fehlgeschlagen

**Prüfen:**
```bash
# API-Endpunkt testen (nach Implementierung):
curl http://smartdormv2-api-dev.schollheim.net/api/printing/active-session/

# Sollte JSON zurückgeben (nicht 404)
```

**Lösung:**
- Prüfen ob API-Endpunkte implementiert sind (siehe SmartDorm-Code)
- Backend-URL in `scan_monitor.py` prüfen (Dev vs. Prod)
- Netzwerk-Verbindung prüfen (Pi kann Backend erreichen?):
  ```bash
  ping smartdormv2-api-dev.schollheim.net
  curl http://smartdormv2-api-dev.schollheim.net/api/
  ```

---

## Checkliste

- [x] CUPS-Printer-Name: `Samsung_C1860_Series` ✅
- [ ] CUPS Netzwerk-Zugriff konfiguriert und getestet
- [ ] Samba installiert und konfiguriert
- [ ] Scan-Ordner erstellt (`/srv/scans/{inbox,processed,unassigned}`)
- [ ] SMB-Freigabe getestet
- [ ] Drucker Scan-to-SMB konfiguriert
- [ ] Test-Scan erfolgreich (Datei in inbox/)
- [ ] Python-Umgebung erstellt (venv)
- [ ] Dependencies installiert (requests, watchdog)
- [ ] Scan-Monitor Script erstellt (mit korrekter Backend-URL)
- [ ] Script manuell getestet
- [ ] Systemd-Service erstellt und aktiviert
- [ ] Service läuft (`systemctl status`)
- [ ] Vollständiger Test erfolgreich (Scan → SmartDorm)

---

## Wichtige Informationen für SmartDorm-Konfiguration

**Notiere dir diese Werte für die SmartDorm `.env` Datei:**

1. **CUPS_SERVER:** IP-Adresse deines Raspberry Pi (z.B. `192.168.1.100`)
   - Prüfen mit: `hostname -I` auf dem Pi

2. **CUPS_PRINTER_NAME:** Name des Druckers in CUPS
   - **Aktuell:** `Samsung_C1860_Series` (aus deinem `lpstat -p`)

**Beispiel `.env` Eintrag:**
```bash
CUPS_SERVER=192.168.1.100
CUPS_PRINTER_NAME=Samsung_C1860_Series
```

**Diese Werte werden für die SmartDorm-Implementierung benötigt.**

