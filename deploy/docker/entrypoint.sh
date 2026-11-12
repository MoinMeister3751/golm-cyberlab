#!/bin/sh
# Startet den Container: Datenbank anlegen/migrieren, Inhalte importieren,
# optional ein Admin-Konto erzeugen, dann das eigentliche Kommando ausführen.
set -e

echo "==> Inhalte importieren (Räume & Lernpfade)"
python -m flask --app cyberlab import-content

# Optionales Erst-Admin-Konto per Umgebungsvariablen (nur lokaler Login).
# Bei gesetztem CYBERLAB_LDAP_ENABLED meist nicht nötig.
if [ -n "$CYBERLAB_ADMIN_USER" ] && [ -n "$CYBERLAB_ADMIN_PASSWORD" ]; then
    echo "==> Admin-Konto '$CYBERLAB_ADMIN_USER' sicherstellen"
    python -m flask --app cyberlab create-admin "$CYBERLAB_ADMIN_USER" \
        --email "${CYBERLAB_ADMIN_EMAIL:-}" --password "$CYBERLAB_ADMIN_PASSWORD"
fi

exec "$@"
