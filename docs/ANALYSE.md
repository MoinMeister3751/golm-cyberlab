# Analyse: TryHackMe & HackerDNA → Golm CyberLab

Stand: November 2026. Grundlage sind die öffentlichen Seiten der Anbieter. Die Angaben dort
stammen von den Anbietern selbst.

## 1. Was die Plattformen ausmacht

| Baustein | TryHackMe | HackerDNA | Bedeutung fürs Institut |
|---|---|---|---|
| **Lerneinheit** | „Rooms“: geführte Aufgaben mit Text + Fragen | „Labs“ (live VM) + „Courses“ + CTF-„Challenges“ | Kurze, abgeschlossene Einheiten mit Fragen sind ideal – auch für Nicht-ITler |
| **Struktur** | Lernpfade nach Rolle (Pre Security, SOC L1, Jr. Pentester …) | Kurse „Fundamentals → Advanced“, Schwierigkeit Very Easy–Hard | Zwei Zielgruppen: **alle Beschäftigten** (Awareness) und **IT-Personal** (technisch) |
| **Praxis-Umgebung** | Ziel-VM pro Raum + „AttackBox“ (Angreifer-Desktop im Browser), alternativ VPN | Echte isolierte VMs pro Lab, nichts installieren | Kernstück: **Proxmox-Linked-Clones** pro Person, isoliertes Labornetz |
| **Gamification** | Punkte, Streaks, Abzeichen, Ligen, King of the Hill | Punkte/XP, Streaks, Bestenlisten nach Land/Uni, Uni-Wettbewerb, Daily Challenge | Punkte, Streak, Abzeichen, **Institutswertung** statt Länder-/Uni-Ranking, „Raum des Tages“ |
| **Werkzeuge** | AttackBox mit Kali-Tools | Kostenlose Browser-Tools (Base64, Hex, ROT13, JWT …), nmap-Spickzettel | **Toolbox im Browser** (rein clientseitig) |
| **Wettkampf** | King of the Hill (mehrere Personen auf einer VM) | Wettbewerbe zwischen Universitäten | Später: CTF-Event pro Semester, Institut gegen Institut |
| **Geschäftsmodell** | Free / Premium / Business | Free / Pro / Max | Entfällt – intern, keine Bezahlschranke |

## 2. Was für Golm anders sein muss

1. **Selbst betrieben im eigenen Netz.** Kein Cloud-Dienst, keine Daten bei Dritten. Läuft auf
   dem vorhandenen Proxmox-Host, Plattform auf **Windows Server 2025** (Vorgabe).
2. **Zwei sehr unterschiedliche Zielgruppen.** Wissenschaftler:innen, Doktorand:innen und
   Verwaltung brauchen 15-Minuten-Awareness-Räume ohne VM. Die IT braucht echte Hands-on-Labs.
3. **Anmeldung über das Institutskonto (AD/LDAP).** Keine weiteren Passwörter. Lokale Konten
   nur für Admins und Gäste.
4. **Datenschutz & Mitbestimmung.** Eine Lernplattform mit Fortschrittsdaten kann als technische
   Einrichtung zur Leistungs- und Verhaltenskontrolle gelten (§ 87 Abs. 1 Nr. 6 BetrVG;
   bei der MPG gilt das entsprechende Mitbestimmungsrecht). Deshalb:
   * Bestenliste ist **opt-out** (Profil → „In der Bestenliste anzeigen“).
   * Admin-Export ist **nur aggregiert** (Institut × Raum), keine Einzelpersonen.
   * Antworttexte werden **nicht** gespeichert, nur „richtig/falsch“ für das Rate-Limit.
   * **Vor dem Produktivstart:** Datenschutzbeauftragte und Betriebsrat einbinden,
     Verarbeitungsverzeichnis-Eintrag, Löschkonzept.
5. **Sicherheit der Übungsumgebung.** Verwundbare VMs dürfen das Campus-Netz nie erreichen:
   eigene Bridge ohne Uplink, Proxmox-Firewall, VPN nur in eine Richtung.
6. **Rechtlicher Rahmen.** Räume weisen auf § 202a–c StGB hin. Gescannt wird nur im Labornetz.

## 3. Übernommen, angepasst, weggelassen

| Funktion | Entscheidung |
|---|---|
| Räume mit Aufgaben, Fragen, Flaggen | ✅ übernommen, Inhalte als **YAML-Dateien** (versionierbar, ohne Web-Editor pflegbar) |
| Lernpfade | ✅ „Security-Awareness für alle“ + „Einstieg Offensive Security“ |
| Live-VMs pro Person | ✅ Proxmox-API, Linked Clones, Zeitlimit + Verlängern, automatisches Löschen |
| Punkte, Streak, Abzeichen | ✅ |
| Tipps | ✅ mit Punktabzug (halbe Punkte), wie bei den Vorbildern üblich |
| Erklärung nach dem Lösen | ➕ neu: jede Frage kann eine Erklärung haben. Für Awareness wichtiger als Punkte |
| Bestenliste | ✅ gesamt / 30 Tage / pro Institut, **Institutswertung** als Mittelwert pro Kopf |
| Browser-Toolbox | ✅ Base64, Hex, URL, ROT13, Binär, JWT, SHA-1/256, Hash-Erkennung |
| Raum des Tages | ✅ statt „Daily Challenge“ |
| AttackBox im Browser | ⏳ Roadmap (Guacamole + Kali-VM), zunächst WireGuard-VPN |
| King of the Hill | ⏳ Roadmap |
| Bezahlmodell, Zertifikate | ❌ nicht nötig |
| Markenname, Design, Inhalte der Vorbilder | ❌ bewusst nicht übernommen. Eigene Inhalte mit Campus-Bezug |

## 4. Architektur

```
Browser ──HTTPS──► IIS (WS2025, :443) ──► waitress/Flask (127.0.0.1:8080)
                                            │   SQLite (instance/cyberlab.db)
                                            │   content/*.yaml
                                            └──► Proxmox-API (:8006, Token, minimale Rechte)
                                                    └─ Linked Clones im Pool „cyberlab“ auf vmbr1
Teilnehmende ──WireGuard──► lab-gw ──► vmbr1 (10.66.0.0/16)
```

* **Python/Flask** statt .NET: läuft nativ auf Windows Server 2025, ist klein und gut wartbar,
  und die meisten Security-Leute können Python lesen.
* **SQLite** reicht für einige hundert Nutzer. Wechsel auf PostgreSQL/SQL Server durch
  `SQLALCHEMY_DATABASE_URI` möglich.
* **Kein CDN, keine externen Ressourcen.** Funktioniert auch in abgeschotteten Netzen, CSP ist strikt.

## 5. Roadmap

1. **Pilot** (IT-Abteilung, 4 Wochen): Templates 9001–9003 bauen, Flaggen verifizieren, Feedback.
2. **Awareness-Rollout** für alle drei Institute, Datenschutz/Betriebsrat vorher abstimmen.
3. **AttackBox im Browser:** Apache Guacamole + Kali-Template, Verbindung pro Lab automatisch anlegen.
4. **Weitere Räume:** Windows/AD-Grundlagen (Windows-Server-Template), Log-Analyse/Blue Team,
   sichere Forschungssoftware (Python-Secrets, Jupyter-Notebooks absichern).
5. **CTF-Event pro Semester** mit Institutswertung.
6. **Phishing-Simulation** (z. B. GoPhish) mit Verlinkung auf den Phishing-Raum als Lernangebot.

## Quellen

* TryHackMe – Preise/Funktionen: <https://tryhackme.com/pricing>
* TryHackMe – llms.txt (Plattformbeschreibung): <https://tryhackme.com/llms.txt>
* HackerDNA – Startseite: <https://hackerdna.com>
* HackerDNA – Funktionsweise: <https://hackerdna.com/how-it-works>
* HackerDNA – Plattformbeschreibung: <https://hackerdna.com/llms.txt>
