# Proxmox-Einrichtung

Zielbild: **ein Proxmox-VE-Host** (oder Cluster), darauf

* die **Plattform-VM** mit Windows Server 2025 (Web-App, Datenbank, IIS),
* ein **isoliertes Labornetz** für die verwundbaren Übungs-VMs,
* ein kleiner **Lab-Gateway** (WireGuard-VPN), über den Teilnehmende das Labornetz erreichen,
* **Templates** für jede Übungsmaschine, aus denen pro Nutzer ein Linked Clone entsteht.

```
                Campus-LAN (VLAN „Server“)
                        │
          ┌─────────────┼───────────────────────────┐
          │ Proxmox VE  │                           │
          │      vmbr0 ─┼── WS2025 „cyberlab“ ──────┤ HTTPS :443  (Web-Oberfläche)
          │             │        │ API :8006 ──────► Proxmox-API (nur von dieser VM)
          │             │                           │
          │      vmbr0 ─┼── lab-gw (Debian) ────────┤ UDP :51820 (WireGuard)
          │                       │                 │
          │      vmbr1 (kein Uplink, 10.66.0.0/16) ─┤
          │        ├── lab-9100 (Clone von 9001)    │
          │        ├── lab-9101 (Clone von 9003)    │
          │        └── …                            │
          └─────────────────────────────────────────┘
```

> **Wichtig:** Das Labornetz `vmbr1` hat **keinen** physischen Uplink. Verwundbare VMs dürfen
> niemals ins Campus-Netz oder Internet. Einziger Weg hinein ist der WireGuard-Gateway, und der
> lässt nur Verkehr *von* VPN-Clients *zu* den Labs zu – nicht umgekehrt.

## 1. Hardware-Richtwerte

| Nutzung | CPU | RAM | Storage |
|---|---|---|---|
| Pilot (≤ 10 Labs gleichzeitig) | 8 Kerne | 64 GB | 1 TB NVMe (ZFS/LVM-thin) |
| Campus-Betrieb (≤ 30 Labs) | 16–24 Kerne | 128–192 GB | 2 TB NVMe |

Linked Clones brauchen Storage mit Snapshot-Support: **LVM-thin, ZFS oder Ceph** (nicht „Directory“).

## 2. Netzwerk

`/etc/network/interfaces` auf dem Proxmox-Host ergänzen:

```
auto vmbr1
iface vmbr1 inet manual
        bridge-ports none
        bridge-stp off
        bridge-fd 0
#Isoliertes Labornetz – KEIN Uplink
```

`ifreload -a` ausführen. Alternativ: *Datacenter → SDN → Zone (Simple) + VNet* ohne Gateway.

Zusätzlich die **Proxmox-Firewall** für alle Lab-VMs aktivieren (Security Group `lab`):

```
# /etc/pve/firewall/cluster.fw
[group lab]
IN  ACCEPT -source 10.66.0.1      # Gateway/VPN
OUT ACCEPT -dest 10.66.0.1
IN  DROP
OUT DROP                            # Labs untereinander isoliert
```

Damit sehen sich Labs verschiedener Nutzer nicht gegenseitig. (Templates mit
`firewall=1` an der Netzwerkkarte anlegen, siehe `lab-templates.md`.)

## 3. Windows-Server-2025-VM (Plattform)

*Create VM* mit folgenden Einstellungen:

| Einstellung | Wert |
|---|---|
| OS | Microsoft Windows, Version **11/2022/2025** |
| ISO | Windows Server 2025 (Datacenter oder Standard) + zweites Laufwerk **virtio-win.iso** |
| System | Machine **q35**, BIOS **OVMF (UEFI)**, EFI-Disk, **TPM 2.0** (v2.0), Qemu Agent ✔ |
| Disk | VirtIO SCSI single, 80 GB, Discard ✔, IO thread ✔ |
| CPU | 4 Kerne, Typ **host** |
| RAM | 8 GB (Ballooning aus) |
| Netz | **VirtIO**, Bridge `vmbr0` (Server-VLAN) |

Installation:

1. Bei der Laufwerksauswahl *Treiber laden* → `virtio-win\vioscsi\2k25\amd64`.
2. Nach der Installation `virtio-win-guest-tools.exe` ausführen (Treiber + QEMU-Agent).
3. Windows Updates, Hostname `cyberlab`, Domänenbeitritt (falls AD-Anmeldung gewünscht).
4. Repository nach `C:\Install\golm-cyberlab` kopieren, dann:
   ```powershell
   cd C:\Install\golm-cyberlab
   powershell -ExecutionPolicy Bypass -File .\deploy\windows\install.ps1 -AdminUser admin -InstallIIS
   ```
5. IIS/HTTPS nach `deploy/windows/IIS.md` einrichten.

## 4. API-Token mit minimalen Rechten

Auf dem Proxmox-Host:

```bash
# Pool für alle Lab-Klone
pvesh create /pools --poolid cyberlab --comment "Golm CyberLab Übungs-VMs"

# Eigene Rolle mit genau den benötigten Rechten
pveum role add CyberLabProvisioner -privs "VM.Clone VM.Allocate VM.Audit VM.Monitor VM.PowerMgmt VM.Config.Disk VM.Config.CPU VM.Config.Memory VM.Config.Network VM.Config.Options VM.Config.Cloudinit Datastore.AllocateSpace Datastore.Audit SDN.Use Pool.Allocate Sys.Audit"

# Benutzer + Token (privsep=1: Token hat nur explizit vergebene Rechte)
pveum user add cyberlab@pve --comment "CyberLab-Plattform"
pveum user token add cyberlab@pve platform --privsep 1
#  -> Secret notieren! Kommt nach instance/config.py (PROXMOX_TOKEN_SECRET)

# Rechte: Pool, Templates, Storage, Labornetz
pveum acl modify /pool/cyberlab      --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner
pveum acl modify /vms/9001           --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner
pveum acl modify /vms/9002           --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner
pveum acl modify /vms/9003           --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner
pveum acl modify /storage/local-lvm  --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner
pveum acl modify /sdn/zones/localnetwork/vmbr1 --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner
pveum acl modify /                   --tokens 'cyberlab@pve!platform' --roles PVEAuditor --propagate 0
```

> `/cluster/resources` (für die VMID-Vergabe) benötigt `Sys.Audit`/`VM.Audit`; die Rolle
> `PVEAuditor` auf `/` **ohne Vererbung** reicht dafür.

Den Zugriff auf Port 8006 per Firewall nur von der Windows-VM (und dem Admin-Netz) erlauben.

**TLS:** Entweder ein Zertifikat der internen CA auf dem Proxmox-Host hinterlegen oder die
Proxmox-CA (`/etc/pve/pve-root-ca.pem`) auf die Windows-VM kopieren und in der Konfiguration
`PROXMOX_VERIFY_SSL = r"C:\CyberLab\certs\proxmox-ca.pem"` setzen. **Niemals** `False`.

Danach in `C:\CyberLab\instance\config.py`: `PROXMOX_MOCK = False` + Host/Node/Token eintragen,
`Restart-Service GolmCyberLab`.

## 5. Lab-Gateway mit WireGuard

Kleine Debian-12-VM `lab-gw` (1 vCPU, 512 MB) mit **zwei** Netzwerkkarten:
`net0` → `vmbr0` (Campus), `net1` → `vmbr1` (Labor, statisch `10.66.0.1/16`).

```bash
apt install wireguard dnsmasq nftables
# dnsmasq: DHCP fürs Labornetz
cat >/etc/dnsmasq.d/lab.conf <<'EOF'
interface=ens19
dhcp-range=10.66.1.10,10.66.254.250,255.255.0.0,2h
EOF

# WireGuard-Server
wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
cat >/etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.67.0.1/16
ListenPort = 51820
PrivateKey = $(cat /etc/wireguard/server.key)
EOF
systemctl enable --now wg-quick@wg0 dnsmasq
sysctl -w net.ipv4.ip_forward=1 && echo net.ipv4.ip_forward=1 > /etc/sysctl.d/99-fwd.conf
```

`/etc/nftables.conf` – nur VPN → Lab erlaubt, Labs dürfen **nichts** nach außen:

```
table inet filter {
  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
    iifname "wg0" oifname "ens19" accept     # VPN-Client -> Lab
  }
}
```

Für jede Person ein Peer mit eigener IP (`10.67.x.y/32`); die erzeugten Client-Profile als
`<benutzername>.conf` nach `C:\CyberLab\vpn-profiles` legen – die Plattform bietet sie dann unter
*Profil → Lab-Zugang* zum Download an (`LAB_VPN_CONFIG_DIR`). Client-Profil:

```
[Interface]
PrivateKey = <client-key>
Address = 10.67.0.23/32

[Peer]
PublicKey = <server.pub>
Endpoint = lab-gw.campus.local:51820
AllowedIPs = 10.66.0.0/16      # nur Labornetz, kein Full-Tunnel
```

**Alternative ohne VPN-Client:** Apache Guacamole (Linux-VM) mit einer Kali-„AttackBox“-VM
im Labornetz – Zugriff dann komplett im Browser. Das ist der nächste Ausbauschritt
(siehe `docs/ANALYSE.md`, Roadmap).

## 6. Templates

Siehe [`lab-templates.md`](lab-templates.md).
