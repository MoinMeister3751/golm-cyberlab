# Kopieren nach instance/config.py und anpassen. Diese Datei NICHT ins Git einchecken.
# Werte überschreiben cyberlab/config.py (DefaultConfig).

# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "HIER-EINEN-LANGEN-ZUFALLSWERT-EINTRAGEN"

PLATFORM_NAME = "Golm CyberLab"
ORGANISATION = "Max-Planck-Campus Potsdam-Golm"

# HTTPS über IIS => Cookies nur über TLS
SESSION_COOKIE_SECURE = True
REMEMBER_COOKIE_SECURE = True

# --- Anmeldung ---------------------------------------------------------
# Empfehlung: Anmeldung nur über Active Directory, Registrierung aus.
ALLOW_REGISTRATION = False
REGISTRATION_EMAIL_DOMAINS = []   # z. B. ["mpikg.mpg.de", "mpimp-golm.mpg.de", "aei.mpg.de"] – mit IT abstimmen

LDAP_ENABLED = True
LDAP_SERVER = "ldaps://dc01.campus.local"
LDAP_UPN_SUFFIX = "campus.local"
LDAP_BASE_DN = "DC=campus,DC=local"
LDAP_ADMIN_GROUP_DN = "CN=CyberLab-Admins,OU=Gruppen,DC=campus,DC=local"
LDAP_VERIFY_CERT = True

# --- Proxmox -----------------------------------------------------------
PROXMOX_MOCK = False
PROXMOX_HOST = "pve01.campus.local"
PROXMOX_PORT = 8006
PROXMOX_NODE = "pve01"
PROXMOX_TOKEN_ID = "cyberlab@pve!platform"
PROXMOX_TOKEN_SECRET = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
PROXMOX_VERIFY_SSL = r"C:\CyberLab\certs\proxmox-ca.pem"   # oder True bei offiziellem Zertifikat
PROXMOX_POOL = "cyberlab"
LAB_VMID_RANGE = (9100, 9999)
LAB_IP_MODE = "agent"        # Linux-Templates mit qemu-guest-agent
LAB_MAX_PER_USER = 1
LAB_MAX_TOTAL = 20           # an RAM/CPU des Hosts anpassen
LAB_DEFAULT_MINUTES = 60

# Ordner mit WireGuard-Profilen <benutzername>.conf (siehe deploy/proxmox/README.md)
LAB_VPN_CONFIG_DIR = r"C:\CyberLab\vpn-profiles"
