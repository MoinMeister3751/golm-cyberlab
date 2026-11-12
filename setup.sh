#!/usr/bin/env bash
# Golm CyberLab – Ein-Befehl-Einrichtung auf Ubuntu mit Docker.
#
# Direkt aus dem Internet:
#   curl -fsSL https://raw.githubusercontent.com/MoinMeister3751/golm-cyberlab/main/setup.sh | bash
# Oder im ausgecheckten Repo:
#   ./setup.sh
#
# Das Skript installiert bei Bedarf Docker, holt den Code, erzeugt eine .env mit
# zufälligem SECRET_KEY und startet die Container.
set -euo pipefail

REPO_URL="${CYBERLAB_REPO_URL:-https://github.com/MoinMeister3751/golm-cyberlab.git}"
TARGET_DIR="${CYBERLAB_DIR:-$HOME/golm-cyberlab}"

info() { printf '\033[32m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[33m!!\033[0m %s\n' "$1"; }
die()  { printf '\033[31mFehler:\033[0m %s\n' "$1" >&2; exit 1; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 && SUDO="sudo" || die "Bitte als root ausführen oder sudo installieren."
fi

# --- 1. Docker sicherstellen -------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    info "Docker wird installiert (get.docker.com)"
    curl -fsSL https://get.docker.com | $SUDO sh
    $SUDO usermod -aG docker "$(id -un)" || true
    warn "Docker installiert. Für docker ohne sudo ggf. neu anmelden."
fi
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    die "Docker Compose Plugin fehlt. 'apt-get install docker-compose-plugin' nachholen."
fi
# docker ohne Gruppenmitgliedschaft ggf. mit sudo
DOCKER="docker"
docker info >/dev/null 2>&1 || { DOCKER="$SUDO docker"; COMPOSE="$SUDO $COMPOSE"; }

# --- 2. Code holen/aktualisieren ---------------------------------------
if [ -f "docker-compose.yml" ] && [ -d "cyberlab" ]; then
    info "Starte im vorhandenen Projektverzeichnis ($(pwd))"
elif [ -d "$TARGET_DIR/.git" ]; then
    info "Aktualisiere vorhandenes Repository in $TARGET_DIR"
    git -C "$TARGET_DIR" pull --ff-only
    cd "$TARGET_DIR"
else
    command -v git >/dev/null 2>&1 || { info "git wird installiert"; $SUDO apt-get update -qq && $SUDO apt-get install -y -qq git; }
    info "Klone $REPO_URL nach $TARGET_DIR"
    git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
    cd "$TARGET_DIR"
fi

# --- 3. Konfiguration (.env) -------------------------------------------
if [ ! -f ".env" ]; then
    info "Erzeuge .env mit zufälligem SECRET_KEY"
    cp .env.example .env
    SECRET="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    # SECRET_KEY ersetzen (| als Trenner, da Hex keine | enthält)
    sed -i "s|^CYBERLAB_SECRET_KEY=.*|CYBERLAB_SECRET_KEY=${SECRET}|" .env
    ADMPW="$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    sed -i "s|^CYBERLAB_ADMIN_PASSWORD=.*|CYBERLAB_ADMIN_PASSWORD=${ADMPW}|" .env
    warn "Erzeugtes Admin-Passwort (bitte notieren und in der .env ändern):"
    printf '    Benutzer: admin\n    Passwort: %s\n' "$ADMPW"
    GENERATED_PW="$ADMPW"
else
    info "Vorhandene .env wird verwendet"
fi

# --- 4. Starten ---------------------------------------------------------
info "Baue und starte Container"
$COMPOSE up -d --build

echo
info "Fertig. Status:"
$COMPOSE ps
ADDR="$(grep -E '^CYBERLAB_SITE_ADDRESS=' .env | cut -d= -f2-)"
case "$ADDR" in
    :80|"") URL="http://<server-ip>" ;;
    http*)  URL="$ADDR" ;;
    *)      URL="https://$ADDR" ;;
esac
echo
info "Aufruf im Browser: ${URL}"
[ -n "${GENERATED_PW:-}" ] && warn "Admin-Login: admin / ${GENERATED_PW}"
info "Logs: ${COMPOSE} logs -f app   |   Stoppen: ${COMPOSE} down"
