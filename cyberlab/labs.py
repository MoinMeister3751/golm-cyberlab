"""Lab-Maschinen: Start/Stop/Verlängern + Hintergrund-Reaper für abgelaufene VMs."""
import threading
import time
from datetime import timedelta

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, send_file,
                   url_for)
from flask_login import current_user, login_required

from .extensions import db
from .models import LabInstance, Room, utcnow
from .proxmox import get_client

bp = Blueprint("labs", __name__, url_prefix="/labs")


def active_query():
    return LabInstance.query.filter(LabInstance.status.in_(LabInstance.ACTIVE))


def _provision(app, lab_id):
    with app.app_context():
        lab = db.session.get(LabInstance, lab_id)
        client = get_client(app.config)
        try:
            client.clone_and_start(
                lab.room.lab_template_vmid, lab.vmid,
                name=f"lab-{lab.room.slug}-{lab.user.username}"[:60].replace("_", "-"),
                tags=["cyberlab", f"user-{lab.user_id}", f"room-{lab.room.slug}"])
            lab.ip = client.get_ip(lab.vmid)
            lab.status = "running"
            lab.message = None if lab.ip else "IP noch unbekannt – bitte in 1–2 Minuten neu laden."
        except Exception as exc:  # noqa: BLE001
            app.logger.exception("Lab-Provisionierung fehlgeschlagen")
            lab.status = "error"
            lab.message = "Start fehlgeschlagen. Bitte Admin informieren."
            db.session.commit()
            try:
                client.destroy(lab.vmid)
            except Exception:  # noqa: BLE001
                app.logger.warning("Aufräumen von VM %s fehlgeschlagen: %s", lab.vmid, exc)
            return
        db.session.commit()


def _destroy(app, lab_id):
    with app.app_context():
        lab = db.session.get(LabInstance, lab_id)
        try:
            get_client(app.config).destroy(lab.vmid)
            lab.status = "stopped"
        except Exception:  # noqa: BLE001
            app.logger.exception("Löschen von VM %s fehlgeschlagen", lab.vmid)
            lab.status = "error"
            lab.message = "Löschen fehlgeschlagen – Admin prüft."
        db.session.commit()


def stop_lab(lab):
    lab.status = "stopping"
    db.session.commit()
    app = current_app._get_current_object()
    threading.Thread(target=_destroy, args=(app, lab.id), daemon=True).start()


def reap_expired():
    expired = active_query().filter(LabInstance.expires_at < utcnow(),
                                    LabInstance.status != "stopping").all()
    for lab in expired:
        stop_lab(lab)
    return len(expired)


def start_reaper(app, interval=60):
    def loop():
        while True:
            try:
                with app.app_context():
                    reap_expired()
            except Exception:  # noqa: BLE001
                app.logger.exception("Reaper-Fehler")
            time.sleep(interval)
    threading.Thread(target=loop, name="lab-reaper", daemon=True).start()


def _lab_json(lab):
    if not lab:
        return {"status": "none"}
    return {"id": lab.id, "status": lab.status, "ip": lab.ip, "message": lab.message,
            "seconds_left": lab.seconds_left}


_start_lock = threading.Lock()


@bp.post("/start/<slug>")
@login_required
def start(slug):
    room = Room.query.filter_by(slug=slug, published=True).first_or_404()
    if not room.lab_template_vmid:
        abort(400)
    cfg = current_app.config
    with _start_lock:
        if active_query().filter_by(user_id=current_user.id).count() >= cfg["LAB_MAX_PER_USER"]:
            flash("Du hast bereits eine laufende Maschine. Beende sie zuerst.", "warning")
            return redirect(url_for("main.room", slug=slug))
        if active_query().count() >= cfg["LAB_MAX_TOTAL"]:
            flash("Alle Lab-Plätze sind gerade belegt. Bitte später erneut versuchen.", "warning")
            return redirect(url_for("main.room", slug=slug))
        reserved = {lab.vmid for lab in active_query().all() if lab.vmid}
        try:
            vmid = get_client(cfg).allocate_vmid(reserved)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("VMID-Vergabe fehlgeschlagen")
            flash("Proxmox ist nicht erreichbar. Bitte Admin informieren.", "error")
            return redirect(url_for("main.room", slug=slug))
        minutes = room.lab_minutes or cfg["LAB_DEFAULT_MINUTES"]
        lab = LabInstance(user_id=current_user.id, room_id=room.id, vmid=vmid,
                          node=cfg["PROXMOX_NODE"], status="provisioning",
                          expires_at=utcnow() + timedelta(minutes=minutes))
        db.session.add(lab)
        db.session.commit()
    app = current_app._get_current_object()
    threading.Thread(target=_provision, args=(app, lab.id), daemon=True).start()
    flash("Maschine wird gestartet – das dauert meist 1–2 Minuten.", "info")
    return redirect(url_for("main.room", slug=slug) + "#lab")


def _own_lab(lab_id):
    lab = db.session.get(LabInstance, lab_id)
    if not lab or (lab.user_id != current_user.id and not current_user.is_admin):
        abort(404)
    return lab


@bp.post("/<int:lab_id>/stop")
@login_required
def stop(lab_id):
    lab = _own_lab(lab_id)
    if lab.status in ("provisioning", "running", "error"):
        stop_lab(lab)
        flash("Maschine wird beendet.", "info")
    return redirect(url_for("main.room", slug=lab.room.slug))


@bp.post("/<int:lab_id>/extend")
@login_required
def extend(lab_id):
    lab = _own_lab(lab_id)
    cfg = current_app.config
    if lab.status == "running":
        limit = lab.created_at + timedelta(minutes=cfg["LAB_MAX_MINUTES"])
        lab.expires_at = min(lab.expires_at + timedelta(minutes=cfg["LAB_EXTEND_MINUTES"]), limit)
        db.session.commit()
        flash("Laufzeit verlängert.", "success")
    return redirect(url_for("main.room", slug=lab.room.slug) + "#lab")


@bp.get("/status/<slug>")
@login_required
def status(slug):
    room = Room.query.filter_by(slug=slug).first_or_404()
    lab = (LabInstance.query.filter_by(user_id=current_user.id, room_id=room.id)
           .order_by(LabInstance.id.desc()).first())
    if lab and lab.status == "stopped":
        lab = None
    return jsonify(_lab_json(lab))


@bp.get("/vpn")
@login_required
def vpn_config():
    """Liefert das persönliche WireGuard-Profil aus LAB_VPN_CONFIG_DIR/<username>.conf."""
    import os
    import re
    folder = current_app.config.get("LAB_VPN_CONFIG_DIR")
    if not folder or not re.fullmatch(r"[A-Za-z0-9._-]+", current_user.username):
        abort(404)
    path = os.path.join(folder, f"{current_user.username}.conf")
    if not os.path.isfile(path):
        flash("Für dein Konto ist noch kein VPN-Profil hinterlegt. Bitte IT kontaktieren.",
              "warning")
        return redirect(url_for("main.profile"))
    return send_file(path, as_attachment=True, download_name="golm-cyberlab.conf")
