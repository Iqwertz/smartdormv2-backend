# WSL2 Port Forwarding Script
# Führt Port 8000 vom Windows-Host zum WSL2 weiter
# Muss als Administrator ausgeführt werden!

Write-Host "========================================="
Write-Host "WSL2 Port Forwarding Setup"
Write-Host "========================================="
Write-Host ""

# Prüfe ob Admin-Rechte vorhanden sind
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "FEHLER: Dieses Script muss als Administrator ausgeführt werden!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Bitte:" -ForegroundColor Yellow
    Write-Host "1. PowerShell als Administrator öffnen (Rechtsklick -> 'Als Administrator ausführen')"
    Write-Host "2. Dieses Script erneut ausführen"
    Write-Host ""
    pause
    exit 1
}

Write-Host "Admin-Rechte bestätigt." -ForegroundColor Green
Write-Host ""

# WSL2 IP ermitteln
Write-Host "Ermittle WSL2 IP-Adresse..."
try {
    $WSL_IP = (wsl hostname -I).Trim()
    if ([string]::IsNullOrEmpty($WSL_IP)) {
        throw "WSL2 IP konnte nicht ermittelt werden"
    }
    Write-Host "WSL2 IP gefunden: $WSL_IP" -ForegroundColor Green
} catch {
    Write-Host "FEHLER: WSL2 IP konnte nicht ermittelt werden. Ist WSL2 gestartet?" -ForegroundColor Red
    Write-Host "Versuche WSL zu starten..."
    wsl --shutdown
    Start-Sleep -Seconds 2
    $WSL_IP = (wsl hostname -I).Trim()
    if ([string]::IsNullOrEmpty($WSL_IP)) {
        Write-Host "FEHLER: WSL2 konnte nicht gestartet werden." -ForegroundColor Red
        pause
        exit 1
    }
    Write-Host "WSL2 IP gefunden: $WSL_IP" -ForegroundColor Green
}

$WSL_PORT = 8000
$WIN_PORT = 8000

Write-Host ""
Write-Host "Richte Port-Forwarding ein..."
Write-Host "Windows Port $WIN_PORT -> WSL2 Port $WSL_PORT (IP: $WSL_IP)"

# Alte Port-Forwarding-Regeln entfernen (falls vorhanden)
Write-Host "Entferne alte Port-Forwarding-Regeln..."
netsh interface portproxy delete v4tov4 listenport=$WIN_PORT listenaddress=0.0.0.0 2>$null | Out-Null

# Neue Port-Forwarding-Regel hinzufügen
Write-Host "Erstelle neue Port-Forwarding-Regel..."
netsh interface portproxy add v4tov4 listenport=$WIN_PORT listenaddress=0.0.0.0 connectport=$WSL_PORT connectaddress=$WSL_IP

if ($LASTEXITCODE -eq 0) {
    Write-Host "Port-Forwarding erfolgreich eingerichtet!" -ForegroundColor Green
} else {
    Write-Host "FEHLER beim Einrichten des Port-Forwardings!" -ForegroundColor Red
    pause
    exit 1
}

# Firewall-Regel hinzufügen
Write-Host ""
Write-Host "Richte Firewall-Regel ein..."
$firewallRule = Get-NetFirewallRule -DisplayName "WSL2 Django Port 8000" -ErrorAction SilentlyContinue
if (-not $firewallRule) {
    try {
        New-NetFirewallRule -DisplayName "WSL2 Django Port 8000" -Direction Inbound -LocalPort $WIN_PORT -Protocol TCP -Action Allow | Out-Null
        Write-Host "Firewall-Regel erfolgreich erstellt!" -ForegroundColor Green
    } catch {
        Write-Host "FEHLER beim Erstellen der Firewall-Regel: $_" -ForegroundColor Red
    }
} else {
    Write-Host "Firewall-Regel existiert bereits." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================="
Write-Host "Port-Forwarding aktiviert!" -ForegroundColor Green
Write-Host "========================================="
Write-Host ""
Write-Host "Der Django-Server sollte jetzt erreichbar sein unter:" -ForegroundColor Cyan
Write-Host "  http://192.168.0.106:$WIN_PORT" -ForegroundColor White
Write-Host ""
Write-Host "Teste die Verbindung vom Pi mit:" -ForegroundColor Cyan
Write-Host "  curl http://192.168.0.106:$WIN_PORT/api/" -ForegroundColor White
Write-Host ""
Write-Host "HINWEIS: Das Port-Forwarding bleibt aktiv bis zum WSL2-Neustart." -ForegroundColor Yellow
Write-Host "Bei jedem WSL2-Neustart muss dieses Script erneut ausgeführt werden." -ForegroundColor Yellow
Write-Host ""
pause

