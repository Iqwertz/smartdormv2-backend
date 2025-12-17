# Start-Anleitung: Printing System

## 1. Port-Forwarding einrichten (Windows PowerShell als Admin)

```powershell
wsl hostname -I
$WSL_IP = (wsl hostname -I).Trim()
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$WSL_IP
netsh interface portproxy show all
```

## 2. Backend-Server starten (WSL)

```bash
cd /home/tambaro/dev/schollheim/smartdormv2/smartdormv2-backend
./run-server.sh
```

## 3. Pi-Service prüfen/starten (SSH zum Pi)

```bash
# Status prüfen
sudo systemctl status smartdorm-scan-service

# Starten falls nicht aktiv
sudo systemctl start smartdorm-scan-service

# Logs ansehen
sudo journalctl -u smartdorm-scan-service -f
```

## 4. Testen

- Frontend öffnen: `/print` Seite
- Scan starten
- Logs prüfen

## Hinweis

Das Port-Forwarding muss nach jedem WSL2-Neustart erneut eingerichtet werden!

