"""Konfiguration aus Umgebungsvariablen (für Docker/Ubuntu-Betrieb).

Alle Variablen beginnen mit CYBERLAB_ und überschreiben die Werte aus config.py
bzw. instance/config.py. Nur gesetzte Variablen wirken – leere/fehlende werden ignoriert.
"""
import os


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on", "ja")


def _list(v):
    return [x.strip() for x in v.split(",") if x.strip()]


def _verify_ssl(v):
    # True/False oder Pfad zu einer CA-Datei
    low = v.strip().lower()
    if low in ("1", "true", "yes", "on"):
        return True
    if low in ("0", "false", "no", "off"):
        return False
    return v  # Dateipfad


# Name der Umgebungsvariable (ohne Präfix) -> (Config-Schlüssel, Konverter)
_MAPPING = {
    "SECRET_KEY": ("SECRET_KEY", str),
    "PLATFORM_NAME": ("PLATFORM_NAME", str),
    "ORGANISATION": ("ORGANISATION", str),
    "DATABASE_URI": ("SQLALCHEMY_DATABASE_URI", str),
    "DEPARTMENTS": ("DEPARTMENTS", _list),

    "ALLOW_REGISTRATION": ("ALLOW_REGISTRATION", _bool),
    "REGISTRATION_EMAIL_DOMAINS": ("REGISTRATION_EMAIL_DOMAINS", _list),

    "LDAP_ENABLED": ("LDAP_ENABLED", _bool),
    "LDAP_SERVER": ("LDAP_SERVER", str),
    "LDAP_UPN_SUFFIX": ("LDAP_UPN_SUFFIX", str),
    "LDAP_BASE_DN": ("LDAP_BASE_DN", str),
    "LDAP_ADMIN_GROUP_DN": ("LDAP_ADMIN_GROUP_DN", str),
    "LDAP_VERIFY_CERT": ("LDAP_VERIFY_CERT", _bool),

    "PROXMOX_MOCK": ("PROXMOX_MOCK", _bool),
    "PROXMOX_HOST": ("PROXMOX_HOST", str),
    "PROXMOX_PORT": ("PROXMOX_PORT", int),
    "PROXMOX_NODE": ("PROXMOX_NODE", str),
    "PROXMOX_TOKEN_ID": ("PROXMOX_TOKEN_ID", str),
    "PROXMOX_TOKEN_SECRET": ("PROXMOX_TOKEN_SECRET", str),
    "PROXMOX_VERIFY_SSL": ("PROXMOX_VERIFY_SSL", _verify_ssl),
    "PROXMOX_POOL": ("PROXMOX_POOL", str),
    "PROXMOX_IP_MODE": ("LAB_IP_MODE", str),

    "LAB_MAX_PER_USER": ("LAB_MAX_PER_USER", int),
    "LAB_MAX_TOTAL": ("LAB_MAX_TOTAL", int),
    "LAB_DEFAULT_MINUTES": ("LAB_DEFAULT_MINUTES", int),
    "LAB_MAX_MINUTES": ("LAB_MAX_MINUTES", int),
    "LAB_VPN_CONFIG_DIR": ("LAB_VPN_CONFIG_DIR", str),

    "HTTPS": ("SESSION_COOKIE_SECURE", _bool),
}


def apply_env(config, environ=None):
    """Übernimmt gesetzte CYBERLAB_*-Variablen in das Flask-Config-Objekt."""
    environ = environ if environ is not None else os.environ
    for env_name, (cfg_key, conv) in _MAPPING.items():
        raw = environ.get("CYBERLAB_" + env_name)
        if raw is None or raw == "":
            continue
        config[cfg_key] = conv(raw)
    # HTTPS steuert beide Secure-Cookies gemeinsam
    if config.get("SESSION_COOKIE_SECURE"):
        config["REMEMBER_COOKIE_SECURE"] = True
    return config
