<#
.SYNOPSIS
  Ein-Befehl-Installation von Golm CyberLab auf Windows Server 2025.

.DESCRIPTION
  Lädt das Repository als ZIP herunter (kein Git nötig) und führt deploy\windows\install.ps1 aus.
  Installiert Python und NSSM (per winget), richtet den Windows-Dienst "GolmCyberLab" ein,
  importiert die Inhalte und legt ein Admin-Konto an.

  Standard: direkter HTTP-Zugriff (Dienst an 0.0.0.0, Firewall offen) – sofort erreichbar.
  Mit -InstallIIS stattdessen hinter IIS mit HTTPS (TLS-Schritte danach gemäß IIS.md).

.NOTES
  In einer PowerShell ALS ADMINISTRATOR ausführen.
#>
param(
    [string]$Branch = "main",
    [string]$InstallDir = "C:\CyberLab",
    [int]$Port = 8080,
    [string]$AdminUser = "admin",
    [string]$BindHost = "0.0.0.0",
    [switch]$InstallIIS
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# Skriptausführung für DIESEN Prozess erlauben (ohne die Systemrichtlinie zu ändern)
Set-ExecutionPolicy -Scope Process Bypass -Force -ErrorAction SilentlyContinue
$Repo = "MoinMeister3751/golm-cyberlab"

function Step($m) { Write-Host "==> $m" -ForegroundColor Green }

# Administratorrechte prüfen (install.ps1 braucht sie)
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Bitte PowerShell ALS ADMINISTRATOR öffnen und den Befehl erneut ausführen."
}

$tmp = Join-Path $env:TEMP ("cyberlab-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
    $zip = Join-Path $tmp "src.zip"
    Step "Lade $Repo ($Branch) herunter"
    Invoke-WebRequest "https://codeload.github.com/$Repo/zip/refs/heads/$Branch" -OutFile $zip -UseBasicParsing
    Step "Entpacke"
    Expand-Archive $zip -DestinationPath $tmp -Force
    $src = Join-Path $tmp "golm-cyberlab-$Branch"
    if (-not (Test-Path $src)) { $src = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName }
    # "Mark of the Web" von den entpackten Skripten entfernen (sonst blockt RemoteSigned)
    Get-ChildItem $src -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

    Step "Starte Installation"
    $params = @{ InstallDir = $InstallDir; Port = $Port; AdminUser = $AdminUser }
    if ($InstallIIS) { $params.InstallIIS = $true }
    else { $params.BindHost = $BindHost; $params.OpenFirewall = $true }
    & (Join-Path $src "deploy\windows\install.ps1") @params
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
