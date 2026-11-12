"""Standardkonfiguration. Überschreiben in instance/config.py (siehe config.example.py)."""
import os


class DefaultConfig:
    # --- Allgemein -------------------------------------------------------
    SECRET_KEY = os.environ.get("CYBERLAB_SECRET_KEY", "dev-only-change-me")
    PLATFORM_NAME = "Golm CyberLab"
    ORGANISATION = "Max-Planck-Campus Potsdam-Golm"
    CONTENT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "content")
    SQLALCHEMY_DATABASE_URI = None  # None => SQLite in instance/cyberlab.db

    # Institute / Abteilungen für Teamwertung (Bestenliste)
    DEPARTMENTS = [
        "MPI für Kolloid- und Grenzflächenforschung",
        "MPI für Molekulare Pflanzenphysiologie",
        "MPI für Gravitationsphysik (AEI)",
        "IT / Gemeinsame Dienste",
        "Gäste / Sonstige",
    ]

    # --- Registrierung / Anmeldung --------------------------------------
    ALLOW_REGISTRATION = True
    # Nur diese E-Mail-Domains dürfen sich registrieren (leer = alle)
    REGISTRATION_EMAIL_DOMAINS: list[str] = []

    # Active Directory / LDAP (optional, empfohlen im Institutsbetrieb)
    LDAP_ENABLED = False
    LDAP_SERVER = "ldaps://dc01.example.local"
    LDAP_UPN_SUFFIX = "example.local"        # user -> user@example.local
    LDAP_BASE_DN = "DC=example,DC=local"
    LDAP_ADMIN_GROUP_DN = ""                 # Mitglieder werden Plattform-Admins
    LDAP_VERIFY_CERT = True

    # --- Sicherheit ------------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("CYBERLAB_HTTPS", "0") == "1"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    MAX_WRONG_ANSWERS_PER_MINUTE = 10

    # --- Proxmox / Lab-Maschinen ----------------------------------------
    PROXMOX_MOCK = True              # True = keine echten VMs (Entwicklung/Demo)
    PROXMOX_HOST = "pve.example.local"
    PROXMOX_PORT = 8006
    PROXMOX_NODE = "pve"
    PROXMOX_TOKEN_ID = "cyberlab@pve!platform"   # user@realm!tokenname
    PROXMOX_TOKEN_SECRET = ""
    PROXMOX_VERIFY_SSL = True        # oder Pfad zur CA-Datei
    PROXMOX_POOL = "cyberlab"
    LAB_VMID_RANGE = (9100, 9999)
    LAB_IP_MODE = "agent"            # "agent" (qemu-guest-agent) oder "cloudinit"
    LAB_CLOUDINIT_PREFIX = "10.66"   # cloudinit: IP = 10.66.<x>.<y>/16
    LAB_CLOUDINIT_GATEWAY = "10.66.0.1"
    LAB_MAX_PER_USER = 1
    LAB_MAX_TOTAL = 20
    LAB_DEFAULT_MINUTES = 60
    LAB_EXTEND_MINUTES = 30
    LAB_MAX_MINUTES = 240
    LAB_ACCESS_INFO = (
        "Verbinde dich zuerst mit dem Lab-VPN (WireGuard-Profil unter "
        "'Profil → Lab-Zugang'). Die Ziel-IP ist nur über das VPN erreichbar."
    )
    LAB_VPN_CONFIG_DIR = None  # Ordner mit <username>.conf WireGuard-Profilen
