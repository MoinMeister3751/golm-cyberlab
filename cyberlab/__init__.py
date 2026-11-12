import os

import click
import markdown as md
from flask import Flask
from markupsafe import Markup

from .extensions import csrf, db, login_manager


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("cyberlab.config.DefaultConfig")
    app.config.from_pyfile("config.py", silent=True)
    from .envconfig import apply_env
    apply_env(app.config)
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            "sqlite:///" + os.path.join(app.instance_path, "cyberlab.db"))

    if app.config["SECRET_KEY"] == "dev-only-change-me" and not app.debug and not app.testing:
        app.logger.warning("SECRET_KEY ist nicht gesetzt! instance/config.py anpassen.")

    # Hinter einem Reverse-Proxy (Caddy/nginx/IIS) die X-Forwarded-*-Header auswerten
    if os.environ.get("CYBERLAB_TRUST_PROXY", "0") == "1":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import admin, auth, labs, main
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(labs.bp)
    app.register_blueprint(admin.bp)

    @app.template_filter("markdown")
    def markdown_filter(text):
        return Markup(md.markdown(text or "", extensions=["fenced_code", "tables", "sane_lists"]))

    @app.context_processor
    def inject_globals():
        return {"PLATFORM_NAME": app.config["PLATFORM_NAME"],
                "ORGANISATION": app.config["ORGANISATION"]}

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
        return resp

    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()

    register_cli(app)
    return app


def register_cli(app):
    from .content import import_content
    from .labs import reap_expired
    from .models import User

    @app.cli.command("import-content")
    def import_content_cmd():
        """Räume und Lernpfade aus CONTENT_DIR (YAML) importieren/aktualisieren."""
        stats = import_content(app.config["CONTENT_DIR"])
        click.echo(f"Import fertig: {stats}")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.option("--email", default="")
    @click.password_option()
    def create_admin(username, email, password):
        """Lokales Admin-Konto anlegen (oder Passwort zurücksetzen)."""
        user = User.query.filter_by(username=username).first() or User(username=username)
        user.email = email or user.email
        user.is_admin = True
        user.auth_source = "local"
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin '{username}' gespeichert.")

    @app.cli.command("reap-labs")
    def reap_labs_cmd():
        """Abgelaufene Lab-VMs sofort löschen."""
        click.echo(f"{reap_expired()} Lab(s) beendet.")
