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
    # Netzwerk-Interface, an das der Dienst bindet. Standard 127.0.0.1 (nur hinter IIS).
    # Für direkten HTTP-Zugriff ohne IIS: "0.0.0.0" (öffnet zugleich die Firewall).
    [string]$BindHost = "127.0.0.1",
    [switch]$OpenFirewall,
    [switch]$InstallIIS
)

$ErrorActionPreference = "Stop"
$ServiceName = "GolmCyberLab"
$Source = (Resolve-Path "$PSScriptRoot\..\..").Path

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Green }

# --- 1. Voraussetzungen -------------------------------------------------
function Update-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}
function Find-Python {
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c -and ((& $c.Source --version 2>$null) -match "Python 3\.1[1-9]")) { return $c.Source }
    foreach ($p in @("$env:ProgramFiles\Python313\python.exe", "$env:ProgramFiles\Python312\python.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
$HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

Step "Prüfe Python"
$PythonExe = Find-Python
if (-not $PythonExe) {
    if ($HasWinget) {
        Step "Installiere Python 3.13 (winget)"
        winget install -e --id Python.Python.3.13 --scope machine `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
    } else {
        Step "Installiere Python 3.13 (Direkt-Download)"
        $pyInst = Join-Path $env:TEMP "python-3.13-amd64.exe"
        Invoke-WebRequest "https://www.python.org/ftp/python/3.13.1/python-3.13.1-amd64.exe" `
            -OutFile $pyInst -UseBasicParsing
        Start-Process $pyInst -Wait -ArgumentList `
            "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_launcher=1"
    }
    Update-Path
    $PythonExe = Find-Python
}
if (-not $PythonExe) { throw "Python 3.12+ nicht gefunden – bitte manuell installieren und erneut starten." }
Write-Host "    $PythonExe ($(& $PythonExe --version))"

Step "Prüfe NSSM"
$Nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $Nssm -and $HasWinget) {
    winget install -e --id NSSM.NSSM --accept-package-agreements --accept-source-agreements --disable-interactivity
    Update-Path
    $Nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
}
if (-not $Nssm) {
    Step "Installiere NSSM (Direkt-Download)"
    $nz = Join-Path $env:TEMP "nssm.zip"; $nd = Join-Path $env:TEMP "nssm-extract"
    Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $nz -UseBasicParsing
    Expand-Archive $nz -DestinationPath $nd -Force
    New-Item -ItemType Directory -Force "$InstallDir\bin" | Out-Null
    Copy-Item "$nd\nssm-2.24\win64\nssm.exe" "$InstallDir\bin\nssm.exe" -Force
    $Nssm = "$InstallDir\bin\nssm.exe"
}
Write-Host "    NSSM: $Nssm"

# --- 2. Dateien kopieren -------------------------------------------------
Step "Kopiere Anwendung nach $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir, "$InstallDir\instance", "$InstallDir\logs" | Out-Null
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) { & $Nssm stop $ServiceName | Out-Null }
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
    & $Nssm install $ServiceName $VenvPy "$InstallDir\run.py" | Out-Null
}
& $Nssm set $ServiceName AppDirectory $InstallDir | Out-Null
& $Nssm set $ServiceName DisplayName "Golm CyberLab" | Out-Null
& $Nssm set $ServiceName Description "Interne IT-Security-Lernplattform" | Out-Null
& $Nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
if ($InstallIIS) {
    # Hinter IIS: nur lokal binden, HTTPS-Cookies, Forwarded-Header auswerten
    $envExtra = @("CYBERLAB_HOST=127.0.0.1", "CYBERLAB_PORT=$Port", "CYBERLAB_SCHEME=https",
                  "CYBERLAB_HTTPS=1", "CYBERLAB_TRUST_PROXY=1")
} else {
    # Direkter Zugriff ohne Reverse-Proxy: reines HTTP, Cookies nicht TLS-pflichtig
    $envExtra = @("CYBERLAB_HOST=$BindHost", "CYBERLAB_PORT=$Port", "CYBERLAB_SCHEME=http",
                  "CYBERLAB_HTTPS=0", "CYBERLAB_TRUST_PROXY=0")
}
& $Nssm set $ServiceName AppEnvironmentExtra $envExtra | Out-Null
& $Nssm set $ServiceName AppStdout "$InstallDir\logs\cyberlab.log" | Out-Null
& $Nssm set $ServiceName AppStderr "$InstallDir\logs\cyberlab.log" | Out-Null
& $Nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $Nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
& $Nssm start $ServiceName | Out-Null
Start-Sleep 3
Write-Host "    Status: $((Get-Service $ServiceName).Status)"

# Firewall: Port freigeben, wenn direkt (ohne IIS) und nicht nur lokal gebunden
if (-not $InstallIIS -and ($OpenFirewall -or $BindHost -ne "127.0.0.1")) {
    Step "Firewall-Regel für TCP $Port"
    if (-not (Get-NetFirewallRule -DisplayName "Golm CyberLab HTTP" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "Golm CyberLab HTTP" -Direction Inbound -Protocol TCP `
            -LocalPort $Port -Action Allow -Profile Domain, Private | Out-Null
    }
    Write-Host "    Hinweis: Zugriff erfolgt unverschlüsselt (HTTP). Für TLS bitte mit -InstallIIS betreiben." -ForegroundColor Yellow
}

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

if ($InstallIIS) {
    Step "Fertig. TLS/IIS gemäß deploy\windows\IIS.md abschließen. Lokal: http://127.0.0.1:$Port"
} elseif ($BindHost -ne "127.0.0.1") {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.254\.' } |
           Select-Object -First 1).IPAddress
    Step "Fertig. Aufruf im Browser: http://$($ip):$Port  (unverschlüsselt)"
} else {
    Step "Fertig. Lokal testen: http://127.0.0.1:$Port"
}
