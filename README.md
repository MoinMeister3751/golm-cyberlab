# Golm CyberLab

Interne, selbst gehostete IT-Security-Lernplattform für den Max-Planck-Campus Potsdam-Golm.
Funktional angelehnt an TryHackMe/HackerDNA (Analyse: [`docs/ANALYSE.md`](docs/ANALYSE.md)),
betrieben auf **Proxmox VE** mit der Plattform auf **Windows Server 2025**.

**Funktionen:** Räume mit Aufgaben/Fragen/Flaggen · Lernpfade · Übungs-VMs pro Person
(Proxmox Linked Clones, Zeitlimit, automatisches Aufräumen) · Punkte, Streaks, Abzeichen ·
Bestenliste inkl. Institutswertung · Browser-Toolbox · Admin-Bereich mit Lab-Übersicht und
aggregiertem Export · AD/LDAP-Anmeldung · CSRF-Schutz, strikte CSP, Rate-Limit.

## Schnellstart (Entwicklung, macOS/Linux/Windows)

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # Windows: .venv\Scripts\pip ...
.venv/bin/flask --app cyberlab import-content
.venv/bin/flask --app cyberlab create-admin admin
.venv/bin/flask --app cyberlab run --debug          # http://127.0.0.1:5000
.venv/bin/python -m pytest -q                       # Tests
```

Ohne Proxmox läuft alles im **Mock-Modus** (`PROXMOX_MOCK = True`): Lab-Starts werden simuliert.

## Produktion

1. Proxmox vorbereiten (Labornetz, API-Token, Windows-Server-VM, Gateway):
   [`deploy/proxmox/README.md`](deploy/proxmox/README.md)
2. Auf der Windows-Server-2025-VM:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\deploy\windows\install.ps1 -AdminUser admin -InstallIIS
   ```
3. HTTPS über IIS: [`deploy/windows/IIS.md`](deploy/windows/IIS.md)
4. `C:\CyberLab\instance\config.py` anpassen (Vorlage: `config.example.py`), `Restart-Service GolmCyberLab`
5. Lab-Templates bauen: [`deploy/proxmox/lab-templates.md`](deploy/proxmox/lab-templates.md)

## Inhalte pflegen

Räume sind YAML-Dateien in `content/rooms/`, Lernpfade in `content/paths.yaml`.
Nach Änderungen: Admin → *Inhalte neu importieren* (oder `flask --app cyberlab import-content`).
Lösungen bleiben erhalten, solange der `key` einer Frage gleich bleibt.

```yaml
slug: mein-raum
title: Mein Raum
summary: Kurzbeschreibung
category: Web                 # frei wählbar
difficulty: leicht            # sehr-leicht | leicht | mittel | schwer
estimated_minutes: 30
lab:                          # optional
  template_vmid: 9004
  minutes: 60
  info: "SSH: `ssh student@<IP>`"
tasks:
  - title: Aufgabe 1
    body: |
      Markdown-Text …
    questions:
      - key: mein-raum-1      # stabil lassen!
        prompt: Frage?
        answer: [antwort, alternative]     # oder answer_sha256: <hash>
        case_sensitive: false
        format: "GOLM{...}"
        points: 20
        hint: optionaler Tipp (halbe Punkte)
        explanation: wird nach dem Lösen angezeigt
```

Antworten werden beim Import gehasht (SHA-256) in der Datenbank gespeichert. Das Verzeichnis
`content/` enthält Lösungen im Klartext und darf nicht öffentlich zugänglich sein.

## Struktur

```
cyberlab/            Flask-Anwendung (Modelle, Routen, Proxmox-Client, Templates, CSS/JS)
content/             Räume & Lernpfade (YAML)
deploy/windows/      install.ps1, backup.ps1, IIS-Reverse-Proxy (web.config)
deploy/proxmox/      Netz, API-Token, Gateway/VPN, Lab-Templates
docs/ANALYSE.md      Analyse der Vorbilder, Architektur, Datenschutz, Roadmap
tests/               Pytest-Smoke-Tests
run.py               Produktionsstart (waitress + Lab-Reaper)
```

## Vor dem Produktivbetrieb

- [ ] Datenschutzbeauftragte und Betriebsrat einbinden (Fortschrittsdaten, Bestenliste)
- [ ] IT-Sicherheit: Freigabe des Labornetz-Konzepts, Proxmox-Firewall testen (Lab → Campus muss scheitern)
- [ ] AD-Anbindung mit der IT abstimmen (`LDAP_*`, Admin-Gruppe)
- [ ] Alle Lab-Flaggen einmal selbst durchspielen
- [ ] Backup der Windows-VM (Proxmox Backup Server) + tägliches DB-Backup (wird per install.ps1 eingerichtet)
