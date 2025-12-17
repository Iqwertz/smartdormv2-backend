# Quick WSL2 Port Forwarding Setup
# Muss als Administrator ausgeführt werden!

$WSL_IP = (wsl hostname -I).Trim()
Write-Host "WSL2 IP: $WSL_IP"
Write-Host "Setting up port forwarding..."

netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0 2>$null
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$WSL_IP

Write-Host "Port forwarding configured: 0.0.0.0:8000 -> $WSL_IP:8000" -ForegroundColor Green
netsh interface portproxy show all

