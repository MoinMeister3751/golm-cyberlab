# Konsistentes Online-Backup der SQLite-Datenbank, behält die letzten 14 Stände.
param([string]$InstallDir = "C:\CyberLab", [int]$Keep = 14)
$ErrorActionPreference = "Stop"
$dir = Join-Path $InstallDir "backup"
New-Item -ItemType Directory -Force $dir | Out-Null
$target = Join-Path $dir ("cyberlab-{0:yyyy-MM-dd}.db" -f (Get-Date))
$py = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $py -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" `
    (Join-Path $InstallDir "instance\cyberlab.db") $target
Get-ChildItem (Join-Path $dir "cyberlab-*.db") | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep | Remove-Item
