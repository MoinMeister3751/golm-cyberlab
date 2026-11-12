import re
import time

import pytest

from cyberlab import create_app
from cyberlab.content import import_content
from cyberlab.extensions import db
from cyberlab.models import LabInstance, Question, Solve, User


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test", "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 't.db'}",
        "PROXMOX_MOCK": True,
    })
    with app.app_context():
        import_content(app.config["CONTENT_DIR"])
        admin = User(username="admin", is_admin=True)
        admin.set_password("admin-passwort-123")
        db.session.add(admin)
        db.session.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, name="alice"):
    return client.post("/register", data={
        "username": name, "email": f"{name}@example.org", "password": "geheim-geheim-1",
        "password2": "geheim-geheim-1", "department": "IT / Gemeinsame Dienste"},
        follow_redirects=True)


def qid(app, key):
    with app.app_context():
        return Question.query.filter_by(key=key).one().id


def test_pages_render(client):
    assert client.get("/").status_code == 200
    r = register(client)
    assert "Lernpfade" in r.text
    for url in ["/dashboard", "/rooms", "/rooms?category=Web", "/rooms?q=linux",
                "/paths", "/paths/awareness", "/leaderboard", "/leaderboard?period=30d",
                "/tools", "/profile", "/rooms/web-sql-injection", "/rooms/phishing-erkennen"]:
        r = client.get(url)
        assert r.status_code == 200, url
    assert client.get("/rooms/gibt-es-nicht").status_code == 404
    assert client.get("/admin/").status_code == 403


def test_answers_and_points(app, client):
    register(client)
    q = qid(app, "crypto-1")
    r = client.post(f"/rooms/kodierung-und-hashes/answer/{q}", data={"answer": "falsch"},
                    follow_redirects=True)
    assert "Leider falsch" in r.text
    # case-sensitive Flagge in Kleinbuchstaben -> falsch
    client.post(f"/rooms/kodierung-und-hashes/answer/{q}",
                data={"answer": "golm{b4s364_1st_k31n3_v3rschlu3ss3lung}"})
    r = client.post(f"/rooms/kodierung-und-hashes/answer/{q}",
                    data={"answer": "  GOLM{b4s364_1st_k31n3_v3rschlu3ss3lung} "},
                    follow_redirects=True)
    assert "Richtig! +20" in r.text
    # Tipp halbiert Punkte
    q5 = qid(app, "crypto-5")
    client.post(f"/rooms/kodierung-und-hashes/hint/{q5}")
    r = client.post(f"/rooms/kodierung-und-hashes/answer/{q5}", data={"answer": "Sommer2026"},
                    follow_redirects=True)
    assert "Richtig! +15" in r.text
    # mehrere akzeptierte Antworten
    q1 = qid(app, "phish-1")
    r = client.post(f"/rooms/phishing-erkennen/answer/{q1}", data={"answer": "Spear-Phishing"},
                    follow_redirects=True)
    assert "Richtig" in r.text
    # Frage über falschen Raum-Slug -> 404
    assert client.post(f"/rooms/phishing-erkennen/answer/{q}", data={"answer": "x"}).status_code == 404
    with app.app_context():
        u = User.query.filter_by(username="alice").one()
        assert u.points == 45 and u.streak == 1
    r = client.get("/leaderboard")
    assert "alice" in r.text


def test_rate_limit(app, client):
    register(client)
    q = qid(app, "phish-3")
    for _ in range(10):
        client.post(f"/rooms/phishing-erkennen/answer/{q}", data={"answer": "ja"})
    r = client.post(f"/rooms/phishing-erkennen/answer/{q}", data={"answer": "nein"},
                    follow_redirects=True)
    assert "Zu viele falsche" in r.text


def test_room_completion(app, client):
    register(client)
    answers = {"data-1": "credential stuffing", "data-2": "ablehnen", "data-3": "DSGVO",
               "data-4": "abgeben"}
    for k, a in answers.items():
        r = client.post(f"/rooms/forschungsdaten-schuetzen/answer/{qid(app, k)}",
                        data={"answer": a}, follow_redirects=True)
    assert "abgeschlossen" in r.text
    assert "Forschungsdaten schützen" in client.get("/profile").text


def test_lab_lifecycle(app, client):
    register(client)
    r = client.post("/labs/start/linux-grundlagen", follow_redirects=True)
    assert "wird gestartet" in r.text
    # zweites Lab blockiert
    r = client.post("/labs/start/netzwerk-scanning", follow_redirects=True)
    assert "bereits eine laufende" in r.text
    for _ in range(30):
        data = client.get("/labs/status/linux-grundlagen").get_json()
        if data["status"] == "running":
            break
        time.sleep(0.2)
    assert data["status"] == "running" and re.match(r"10\.66\.", data["ip"])
    r = client.post(f"/labs/{data['id']}/extend", follow_redirects=True)
    assert "verlängert" in r.text
    # fremder Benutzer darf nicht stoppen
    other = app.test_client()
    register(other, "bob")
    assert other.post(f"/labs/{data['id']}/stop").status_code == 404
    client.post(f"/labs/{data['id']}/stop")
    for _ in range(30):
        with app.app_context():
            if db.session.get(LabInstance, data["id"]).status == "stopped":
                break
        time.sleep(0.2)
    with app.app_context():
        assert db.session.get(LabInstance, data["id"]).status == "stopped"


def test_admin_and_reimport_keeps_solves(app, client):
    client.post("/login", data={"username": "admin", "password": "admin-passwort-123"})
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/users").status_code == 200
    q = qid(app, "phish-3")
    client.post(f"/rooms/phishing-erkennen/answer/{q}", data={"answer": "nein"})
    r = client.post("/admin/content/reload", follow_redirects=True)
    assert "6 Räume" in r.text
    assert qid(app, "phish-3") == q
    with app.app_context():
        assert Solve.query.count() == 1
    r = client.get("/admin/export/progress.csv")
    assert "Phishing erkennen" in r.text


def test_login_failures_and_open_redirect(client):
    r = client.post("/login", data={"username": "admin", "password": "falsch"},
                    follow_redirects=True)
    assert "fehlgeschlagen" in r.text
    r = client.post("/login?next=//evil.example", data={"username": "admin",
                    "password": "admin-passwort-123"})
    assert r.headers["Location"].endswith("/dashboard")


def test_env_config_override():
    from cyberlab.envconfig import apply_env
    cfg = {}
    apply_env(cfg, {
        "CYBERLAB_PROXMOX_MOCK": "false",
        "CYBERLAB_PROXMOX_PORT": "8006",
        "CYBERLAB_LAB_MAX_TOTAL": "7",
        "CYBERLAB_ALLOW_REGISTRATION": "0",
        "CYBERLAB_REGISTRATION_EMAIL_DOMAINS": "mpikg.mpg.de, aei.mpg.de",
        "CYBERLAB_PROXMOX_VERIFY_SSL": "/certs/ca.pem",
        "CYBERLAB_HTTPS": "1",
        "CYBERLAB_LDAP_SERVER": "",          # leer -> wird ignoriert
    })
    assert cfg["PROXMOX_MOCK"] is False
    assert cfg["PROXMOX_PORT"] == 8006
    assert cfg["LAB_MAX_TOTAL"] == 7
    assert cfg["ALLOW_REGISTRATION"] is False
    assert cfg["REGISTRATION_EMAIL_DOMAINS"] == ["mpikg.mpg.de", "aei.mpg.de"]
    assert cfg["PROXMOX_VERIFY_SSL"] == "/certs/ca.pem"
    assert cfg["SESSION_COOKIE_SECURE"] and cfg["REMEMBER_COOKIE_SECURE"]
    assert "LDAP_SERVER" not in cfg
