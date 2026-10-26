@echo off
setlocal
cd /d "%~dp0"
echo Run this file as Administrator on the HOST PC only.
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $s=Get-Content -LiteralPath 'host_settings.json' -Raw | ConvertFrom-Json; $rule=Get-NetFirewallRule -Name 'PortraitStudio-LAN-Updates' -ErrorAction SilentlyContinue; if ($rule) { $rule | Remove-NetFirewallRule }; New-NetFirewallRule -Name 'PortraitStudio-LAN-Updates' -DisplayName 'IDFrame LAN Updates' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress Any -LocalPort $s.port -RemoteAddress LocalSubnet -Profile Any"
if errorlevel 1 (
    echo Firewall rule failed. Run as Administrator and check the host IP in host_settings.json.
    pause
    exit /b 1
)
echo Allowed local subnet clients to reach the configured host IP and port.
pause
