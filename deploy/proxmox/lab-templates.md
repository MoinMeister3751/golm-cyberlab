# Lab-Templates bauen

Jeder Raum mit `lab.template_vmid` braucht ein Proxmox-**Template**. Die Plattform erzeugt daraus
pro Nutzer einen *Linked Clone* (Sekunden, kaum Speicherbedarf) und löscht ihn nach Ablauf.

## Allgemeine Regeln

* NIC immer an **`vmbr1`** (Labornetz) mit `firewall=1`, niemals an `vmbr0`.
* **qemu-guest-agent** installieren (`LAB_IP_MODE = "agent"`) – sonst kennt die Plattform die IP nicht.
* Keine echten Zugangsdaten, keine Institutsdaten, keine Domänenmitgliedschaft.
* Flaggen in den VMs müssen **exakt** den Antworten in `content/rooms/*.yaml` entsprechen.
* RAM sparsam: 512 MB–1 GB pro Linux-Lab reichen fast immer.

## Basis-Template (Debian 12 Cloud-Image)

```bash
cd /var/lib/vz/template/iso
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 9000 --name lab-base --memory 1024 --cores 1 --ostype l26 \
  --net0 virtio,bridge=vmbr1,firewall=1 --scsihw virtio-scsi-single \
  --agent enabled=1 --serial0 socket --vga serial0
qm importdisk 9000 debian-12-genericcloud-amd64.qcow2 local-lvm
qm set 9000 --scsi0 local-lvm:vm-9000-disk-0 --boot order=scsi0 \
  --ide2 local-lvm:cloudinit --ipconfig0 ip=dhcp --ciuser labadmin --sshkeys ~/.ssh/id_ed25519.pub
qm resize 9000 scsi0 +4G
```

Für die Einrichtung **vorübergehend** an `vmbr0` hängen (Pakete installieren), danach zurück an `vmbr1`.

## 9001 – Linux-Grundlagen

```bash
qm clone 9000 9001 --name tpl-linux-grundlagen --full 1
qm set 9001 --net0 virtio,bridge=vmbr0     # nur zum Einrichten!
qm start 9001 && ssh labadmin@<ip>
```

In der VM:

```bash
sudo apt update && sudo apt install -y qemu-guest-agent openssh-server
sudo systemctl enable qemu-guest-agent

# Übungsbenutzer
sudo useradd -m -s /bin/bash student && echo 'student:golm-lab' | sudo chpasswd
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config.d/*.conf /etc/ssh/sshd_config

# Aufgabe 2: versteckte Datei
echo 'GOLM{v3rst3ckt3_d4t31en_s1nd_n1cht_s1ch3r}' | sudo tee /home/student/.notiz >/dev/null
sudo chown student: /home/student/.notiz

# Aufgabe 3: Gruppe + sudo-Regel
sudo groupadd forschung
sudo mkdir -p /srv/projekt
echo 'GOLM{sud0_r3chte_g3n4u_pr0f3n}' | sudo tee /srv/projekt/geheim.txt >/dev/null
sudo chown root:forschung /srv/projekt/geheim.txt && sudo chmod 640 /srv/projekt/geheim.txt
echo 'student ALL=(:forschung) NOPASSWD: /usr/bin/cat /srv/projekt/*' | sudo tee /etc/sudoers.d/student
# Lösung: sudo -g forschung cat /srv/projekt/geheim.txt

sudo cloud-init clean && sudo truncate -s0 /etc/machine-id && history -c && sudo poweroff
```

```bash
qm set 9001 --net0 virtio,bridge=vmbr1,firewall=1
qm template 9001
```

## 9002 – SQL-Injection („Probenverwaltung“)

Kleine absichtlich verwundbare PHP-App. Kernpunkte:

```bash
sudo apt install -y apache2 php php-sqlite3 qemu-guest-agent
```

`/var/www/html/index.php` (Suchfeld, **absichtlich** ohne Prepared Statement):

```php
<?php
$db = new SQLite3('/var/www/data/proben.db');
$q  = $_GET['q'] ?? '';
echo '<h1>Probenverwaltung</h1><form><input name="q" value="'.htmlspecialchars($q).'"><button>Suchen</button></form>';
if ($q !== '') {
  $res = @$db->query("SELECT id, name, ort, datum FROM proben WHERE name LIKE '%$q%'");  // VERWUNDBAR
  if (!$res) { echo '<pre>SQL-Fehler: '.$db->lastErrorMsg().'</pre>'; }
  else { echo '<table>'; while ($r = $res->fetchArray(SQLITE3_NUM)) echo '<tr><td>'.implode('</td><td>', array_map('htmlspecialchars', $r)).'</td></tr>'; echo '</table>'; }
}
```

Datenbank (4 Spalten in `proben`, Tabelle `benutzer` mit Admin `laborleitung`):

```bash
sudo mkdir -p /var/www/data && sudo sqlite3 /var/www/data/proben.db <<'SQL'
CREATE TABLE proben(id INTEGER PRIMARY KEY, name TEXT, ort TEXT, datum TEXT);
INSERT INTO proben VALUES (1,'Arabidopsis A-17','Gewächshaus 3','2026-03-02'),(2,'Kolloid K-4','Labor 2.14','2026-04-11');
CREATE TABLE benutzer(id INTEGER PRIMARY KEY, name TEXT, passwort TEXT, rolle TEXT, notiz TEXT);
INSERT INTO benutzer VALUES (1,'laborleitung','5f4dcc3b5aa765d61d8327deb882cf99','admin','GOLM{pr3p4r3d_st4t3m3nts_r3tt3n_l3b3n}'),
                            (2,'praktikant','e10adc3949ba59abbe56e057f20f883e','user','-');
SQL
sudo chown -R www-data: /var/www/data
```

## 9003 – Netzwerk-Scanning

```bash
sudo apt install -y vsftpd nginx qemu-guest-agent
# Anonymes FTP mit Flagge
sudo sed -i 's/^anonymous_enable=.*/anonymous_enable=YES/' /etc/vsftpd.conf
echo 'GOLM{4n0nym3r_ftp_1st_31n_r1s1k0}' | sudo tee /srv/ftp/flagge.txt
# Webserver auf ungewöhnlichem Port 8443 (und NICHT auf 80)
sudo sed -i 's/listen 80 default_server;/listen 8443 default_server;/; s/listen \[::\]:80 default_server;/listen [::]:8443 default_server;/' /etc/nginx/sites-enabled/default
sudo systemctl restart vsftpd nginx
```

## Neues Lab hinzufügen

1. Template bauen (VMID im Bereich 9000–9099), an `vmbr1`, `qm template <id>`.
2. Dem Token Rechte geben: `pveum acl modify /vms/<id> --tokens 'cyberlab@pve!platform' --roles CyberLabProvisioner`
3. Raum-YAML mit `lab: {template_vmid: <id>}` anlegen.
4. Admin-Bereich → *Inhalte neu importieren*.
5. Einmal selbst durchspielen und alle Flaggen prüfen.
