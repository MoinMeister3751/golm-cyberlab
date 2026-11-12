import re

from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db
from .models import User

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.dashboard")


def ldap_authenticate(username, password):
    """Bindet mit user@UPN_SUFFIX gegen AD. Gibt User zurück oder None."""
    cfg = current_app.config
    if not cfg["LDAP_ENABLED"] or not password:
        return None
    import ssl

    from ldap3 import ALL, SUBTREE, Connection, Server, Tls
    from ldap3.utils.conv import escape_filter_chars

    tls = Tls(validate=ssl.CERT_REQUIRED if cfg["LDAP_VERIFY_CERT"] else ssl.CERT_NONE)
    server = Server(cfg["LDAP_SERVER"], get_info=ALL, tls=tls)
    upn = f"{username}@{cfg['LDAP_UPN_SUFFIX']}"
    try:
        conn = Connection(server, user=upn, password=password, auto_bind=True)
    except Exception:  # noqa: BLE001 – falsches Passwort oder Server down
        return None
    conn.search(cfg["LDAP_BASE_DN"],
                f"(userPrincipalName={escape_filter_chars(upn)})", SUBTREE,
                attributes=["displayName", "mail", "memberOf", "department"])
    entry = conn.entries[0] if conn.entries else None
    conn.unbind()

    user = User.query.filter_by(username=username.lower()).first()
    if user and user.auth_source != "ldap":
        return None  # Namenskollision mit lokalem Konto – nicht übernehmen
    if not user:
        user = User(username=username.lower(), auth_source="ldap")
        db.session.add(user)
    if entry is not None:
        user.display_name = str(entry.displayName) if entry.displayName else user.display_name
        user.email = str(entry.mail) if entry.mail else user.email
        groups = [str(g).lower() for g in (entry.memberOf.values if entry.memberOf else [])]
        admin_dn = cfg["LDAP_ADMIN_GROUP_DN"].lower()
        if admin_dn:
            user.is_admin = admin_dn in groups
    db.session.commit()
    return user


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first() \
            or User.query.filter_by(username=username.lower()).first()
        ok = None
        if user and user.auth_source == "local" and user.check_password(password):
            ok = user
        elif not user or user.auth_source == "ldap":
            ok = ldap_authenticate(username, password)
        if ok and ok.is_active:
            login_user(ok, remember=bool(request.form.get("remember")))
            if not ok.department:
                flash("Bitte wähle im Profil dein Institut aus.", "info")
            return redirect(_safe_next(request.args.get("next")))
        flash("Anmeldung fehlgeschlagen.", "error")
    return render_template("login.html", ldap=current_app.config["LDAP_ENABLED"],
                           allow_registration=current_app.config["ALLOW_REGISTRATION"])


@bp.route("/register", methods=["GET", "POST"])
def register():
    cfg = current_app.config
    if not cfg["ALLOW_REGISTRATION"]:
        flash("Registrierung ist deaktiviert – bitte mit Institutskonto anmelden.", "info")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        f = request.form
        username = f.get("username", "").strip()
        email = f.get("email", "").strip().lower()
        pw = f.get("password", "")
        errors = []
        if not USERNAME_RE.match(username):
            errors.append("Benutzername: 3–40 Zeichen, nur Buchstaben, Ziffern, . _ -")
        if "@" not in email:
            errors.append("Bitte eine gültige E-Mail-Adresse angeben.")
        domains = cfg["REGISTRATION_EMAIL_DOMAINS"]
        if domains and email.rsplit("@", 1)[-1] not in domains:
            errors.append("Registrierung nur mit Instituts-E-Mail-Adresse möglich.")
        if len(pw) < 12:
            errors.append("Passwort muss mindestens 12 Zeichen lang sein.")
        if pw != f.get("password2"):
            errors.append("Passwörter stimmen nicht überein.")
        if User.query.filter((User.username == username) | (User.email == email)).first():
            errors.append("Benutzername oder E-Mail bereits vergeben.")
        if f.get("department") not in cfg["DEPARTMENTS"]:
            errors.append("Bitte ein Institut auswählen.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            user = User(username=username, email=email, department=f.get("department"),
                        display_name=f.get("display_name", "").strip()[:120] or None)
            user.set_password(pw)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Willkommen! Starte am besten mit einem Lernpfad.", "success")
            return redirect(url_for("main.paths"))
    return render_template("register.html", departments=cfg["DEPARTMENTS"])


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))
