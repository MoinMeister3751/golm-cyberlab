"""Minimaler Proxmox-VE-API-Client für Lab-VMs (Linked Clones aus Templates).

Benötigte Rechte für den API-Token (siehe deploy/proxmox/README.md):
VM.Clone, VM.Allocate, VM.Config.*, VM.PowerMgmt, VM.Audit, VM.Monitor,
Datastore.AllocateSpace, Pool.Allocate auf dem Pool /pool/cyberlab und Templates.
"""
import random
import threading
import time

import requests

_vmid_lock = threading.Lock()


class ProxmoxError(RuntimeError):
    pass


class ProxmoxClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.node = cfg["PROXMOX_NODE"]
        self.base = f"https://{cfg['PROXMOX_HOST']}:{cfg['PROXMOX_PORT']}/api2/json"
        self.session = requests.Session()
        self.session.headers["Authorization"] = (
            f"PVEAPIToken={cfg['PROXMOX_TOKEN_ID']}={cfg['PROXMOX_TOKEN_SECRET']}")
        self.session.verify = cfg["PROXMOX_VERIFY_SSL"]

    def _req(self, method, path, **kw):
        r = self.session.request(method, self.base + path, timeout=30, **kw)
        if r.status_code >= 400:
            raise ProxmoxError(f"{method} {path}: {r.status_code} {r.text[:300]}")
        return r.json().get("data")

    def wait_task(self, upid, timeout=300):
        end = time.time() + timeout
        while time.time() < end:
            st = self._req("GET", f"/nodes/{self.node}/tasks/{upid}/status")
            if st.get("status") == "stopped":
                if st.get("exitstatus") != "OK":
                    raise ProxmoxError(f"Task fehlgeschlagen: {st.get('exitstatus')}")
                return
            time.sleep(2)
        raise ProxmoxError("Timeout beim Warten auf Proxmox-Task")

    def allocate_vmid(self, reserved: set[int]):
        lo, hi = self.cfg["LAB_VMID_RANGE"]
        used = {int(r["vmid"]) for r in self._req("GET", "/cluster/resources",
                                                  params={"type": "vm"})}
        for vmid in range(lo, hi + 1):
            if vmid not in used and vmid not in reserved:
                return vmid
        raise ProxmoxError("Keine freie VMID im Lab-Bereich")

    def clone_and_start(self, template_vmid, vmid, name, tags):
        upid = self._req("POST", f"/nodes/{self.node}/qemu/{template_vmid}/clone", data={
            "newid": vmid, "name": name, "full": 0, "pool": self.cfg["PROXMOX_POOL"]})
        self.wait_task(upid)
        conf = {"tags": ";".join(tags), "onboot": 0}
        if self.cfg["LAB_IP_MODE"] == "cloudinit":
            conf["ipconfig0"] = (f"ip={self.cloudinit_ip(vmid)}/16,"
                                 f"gw={self.cfg['LAB_CLOUDINIT_GATEWAY']}")
        self._req("PUT", f"/nodes/{self.node}/qemu/{vmid}/config", data=conf)
        upid = self._req("POST", f"/nodes/{self.node}/qemu/{vmid}/status/start")
        self.wait_task(upid)

    def cloudinit_ip(self, vmid):
        prefix = self.cfg["LAB_CLOUDINIT_PREFIX"]
        return f"{prefix}.{vmid // 250}.{vmid % 250 + 2}"

    def get_ip(self, vmid, timeout=180):
        if self.cfg["LAB_IP_MODE"] == "cloudinit":
            return self.cloudinit_ip(vmid)
        end = time.time() + timeout
        while time.time() < end:
            try:
                res = self._req("GET",
                                f"/nodes/{self.node}/qemu/{vmid}/agent/network-get-interfaces")
                for iface in (res or {}).get("result", []):
                    for addr in iface.get("ip-addresses", []):
                        ip = addr.get("ip-address", "")
                        if addr.get("ip-address-type") == "ipv4" and not ip.startswith("127."):
                            return ip
            except ProxmoxError:
                pass  # Agent noch nicht bereit
            time.sleep(5)
        return None

    def destroy(self, vmid):
        try:
            upid = self._req("POST", f"/nodes/{self.node}/qemu/{vmid}/status/stop")
            self.wait_task(upid, timeout=120)
        except ProxmoxError:
            pass  # evtl. bereits gestoppt
        upid = self._req("DELETE", f"/nodes/{self.node}/qemu/{vmid}",
                         params={"purge": 1, "destroy-unreferenced-disks": 1})
        self.wait_task(upid)


class MockProxmoxClient:
    """Simuliert Proxmox für Entwicklung und Demos."""
    node = "mock"

    def __init__(self, cfg):
        self.cfg = cfg

    def allocate_vmid(self, reserved):
        lo, hi = self.cfg["LAB_VMID_RANGE"]
        for vmid in range(lo, hi + 1):
            if vmid not in reserved:
                return vmid
        raise ProxmoxError("Keine freie VMID")

    def clone_and_start(self, template_vmid, vmid, name, tags):
        time.sleep(2)

    def get_ip(self, vmid, timeout=0):
        return f"10.66.{random.randint(0, 3)}.{random.randint(2, 250)}"

    def destroy(self, vmid):
        time.sleep(1)


def get_client(cfg):
    return MockProxmoxClient(cfg) if cfg["PROXMOX_MOCK"] else ProxmoxClient(cfg)
