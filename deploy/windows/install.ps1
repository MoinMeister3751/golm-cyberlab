#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Installiert Golm CyberLab auf Windows Server 2025 als Windows-Dienst.

.DESCRIPTION
  - installiert Python 3.13 und NSSM (per winget), falls nicht vorhanden
  - kopiert die Anwendung nach $InstallDir, legt venv an, installiert Abhängigkeiten
  - erzeugt instance\config.py mit zufälligem SECRET_KEY (falls nicht vorhanden)
  - importiert die Inhalte und legt optional ein lokales Admin-Konto an
  - registriert den Dienst "GolmCyberLab" (waitress auf 127.0.0.1:$Port)
  - optional: IIS mit Reverse-Proxy (siehe deploy/windows/IIS.md)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\deploy\windows\install.ps1 -AdminUser admin
#>
param(
    [string]$InstallDir = "C:\CyberLab",
    [int]$Port = 8080,
    [string]$AdminUser = "",
    [switch]$InstallIIS
)

$ErrorActionPreference = "Stop"
$ServiceName = "GolmCyberLab"
$Source = (Resolve-Path "$PSScriptRoot\..\..").Path

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Green }

# --- 1. Voraussetzungen -------------------------------------------------
Step "Prüfe Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python -or -not ((& python --version 2>$null) -match "Python 3\.1[1-9]")) {
    Step "Installiere Python 3.13 (winget)"
    winget install -e --id Python.Python.3.13 --scope machine --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine")
}
$PythonExe = (Get-Command python).Source
Write-Host "    $PythonExe ($(& $PythonExe --version))"

Step "Prüfe NSSM"
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    winget install -e --id NSSM.NSSM --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine")
}

# --- 2. Dateien kopieren -------------------------------------------------
Step "Kopiere Anwendung nach $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir, "$InstallDir\instance", "$InstallDir\logs" | Out-Null
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) { nssm stop $ServiceName | Out-Null }
robocopy $Source $InstallDir /E /XD .venv instance logs .git __pycache__ tests /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null

# --- 3. venv + Abhängigkeiten -------------------------------------------
Step "Erzeuge virtuelle Umgebung"
if (-not (Test-Path "$InstallDir\.venv")) { & $PythonExe -m venv "$InstallDir\.venv" }
$VenvPy = "$InstallDir\.venv\Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install -r "$InstallDir\requirements.txt" --quiet

# --- 4. Konfiguration ----------------------------------------------------
$Cfg = "$InstallDir\instance\config.py"
if (-not (Test-Path $Cfg)) {
    Step "Erzeuge instance\config.py"
    $secret = & $VenvPy -c "import secrets; print(secrets.token_hex(32))"
    (Get-Content "$InstallDir\config.example.py" -Raw) `
        -replace 'HIER-EINEN-LANGEN-ZUFALLSWERT-EINTRAGEN', $secret `
        -replace 'PROXMOX_MOCK = False', 'PROXMOX_MOCK = True   # nach Proxmox-Einrichtung auf False setzen' `
        -replace 'LDAP_ENABLED = True', 'LDAP_ENABLED = False  # nach AD-Abstimmung auf True setzen' `
        -replace 'ALLOW_REGISTRATION = False', 'ALLOW_REGISTRATION = True' |
        Set-Content -Encoding UTF8 $Cfg
    Write-Host "    Bitte $Cfg anpassen (Proxmox, LDAP, HTTPS)." -ForegroundColor Yellow
}
# Nur SYSTEM und Administratoren dürfen Konfiguration (Secrets) lesen
icacls "$InstallDir\instance" /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null

# --- 5. Datenbank + Inhalte ---------------------------------------------
Step "Importiere Inhalte"
Push-Location $InstallDir
& $VenvPy -m flask --app cyberlab import-content
if ($AdminUser) {
    Step "Lege Admin '$AdminUser' an"
    & $VenvPy -m flask --app cyberlab create-admin $AdminUser
}
Pop-Location

# --- 6. Windows-Dienst ---------------------------------------------------
Step "Registriere Dienst $ServiceName"
if (-not (Get-Service $ServiceName -ErrorAction SilentlyContinue)) {
    nssm install $ServiceName $VenvPy "$InstallDir\run.py" | Out-Null
}
nssm set $ServiceName AppDirectory $InstallDir | Out-Null
nssm set $ServiceName DisplayName "Golm CyberLab" | Out-Null
nssm set $ServiceName Description "Interne IT-Security-Lernplattform" | Out-Null
nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
nssm set $ServiceName AppEnvironmentExtra "CYBERLAB_HOST=127.0.0.1" "CYBERLAB_PORT=$Port" "CYBERLAB_SCHEME=https" "CYBERLAB_TRUST_PROXY=1" | Out-Null
nssm set $ServiceName AppStdout "$InstallDir\logs\cyberlab.log" | Out-Null
nssm set $ServiceName AppStderr "$InstallDir\logs\cyberlab.log" | Out-Null
nssm set $ServiceName AppRotateFiles 1 | Out-Null
nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
nssm start $ServiceName | Out-Null
Start-Sleep 3
Write-Host "    Status: $((Get-Service $ServiceName).Status)"

# --- 7. Tägliches Backup der Datenbank ----------------------------------
Step "Richte tägliches DB-Backup ein (02:30)"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\deploy\windows\backup.ps1`" -InstallDir `"$InstallDir`""
$trigger = New-ScheduledTaskTrigger -Daily -At 2:30am
Register-ScheduledTask -TaskName "GolmCyberLab-Backup" -Action $action -Trigger $trigger `
    -User "SYSTEM" -RunLevel Highest -Force | Out-Null

# --- 8. IIS (optional) ---------------------------------------------------
if ($InstallIIS) {
    Step "Installiere IIS"
    Install-WindowsFeature Web-Server, Web-WebSockets -IncludeManagementTools | Out-Null
    Write-Host "    URL Rewrite + ARR manuell installieren und web.config übernehmen – siehe deploy\windows\IIS.md" -ForegroundColor Yellow
}

Step "Fertig. Lokal testen: http://127.0.0.1:$Port"
