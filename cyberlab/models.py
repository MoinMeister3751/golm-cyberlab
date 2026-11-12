import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_answer(value: str, case_sensitive: bool = False) -> str:
    value = " ".join((value or "").strip().split())
    return value if case_sensitive else value.lower()


def hash_answer(value: str, case_sensitive: bool = False) -> str:
    return hashlib.sha256(normalize_answer(value, case_sensitive).encode()).hexdigest()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(200))
    display_name = db.Column(db.String(120))
    department = db.Column(db.String(120))
    password_hash = db.Column(db.String(255))
    auth_source = db.Column(db.String(20), default="local")  # local | ldap
    is_admin = db.Column(db.Boolean, default=False)
    is_active_flag = db.Column(db.Boolean, default=True)
    show_on_leaderboard = db.Column(db.Boolean, default=True)
    streak = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=utcnow)

    solves = db.relationship("Solve", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def is_active(self):
        return self.is_active_flag

    @property
    def name(self):
        return self.display_name or self.username

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return bool(self.password_hash) and check_password_hash(self.password_hash, pw)

    @property
    def points(self):
        return db.session.query(func.coalesce(func.sum(Solve.points_awarded), 0)).filter(
            Solve.user_id == self.id).scalar()

    def touch_streak(self):
        today = date.today()
        if self.last_active_date == today:
            return
        if self.last_active_date == today - timedelta(days=1):
            self.streak = (self.streak or 0) + 1
        else:
            self.streak = 1
        self.last_active_date = today


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text)
    category = db.Column(db.String(60))
    difficulty = db.Column(db.String(20))  # sehr-leicht | leicht | mittel | schwer
    estimated_minutes = db.Column(db.Integer)
    tags = db.Column(db.String(300))
    published = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=100)
    lab_template_vmid = db.Column(db.Integer)  # Proxmox-Template, None = kein Lab
    lab_minutes = db.Column(db.Integer)
    lab_info = db.Column(db.Text)

    tasks = db.relationship("Task", backref="room", order_by="Task.position",
                            cascade="all, delete-orphan")

    DIFFICULTY_LABELS = {"sehr-leicht": "Sehr leicht", "leicht": "Leicht",
                         "mittel": "Mittel", "schwer": "Schwer"}

    @property
    def difficulty_label(self):
        return self.DIFFICULTY_LABELS.get(self.difficulty, self.difficulty or "–")

    @property
    def questions(self):
        return [q for t in self.tasks for q in t.questions]

    @property
    def total_points(self):
        return sum(q.points for q in self.questions)

    def progress_for(self, user):
        qs = self.questions
        if not qs or not user.is_authenticated:
            return 0, len(qs)
        ids = [q.id for q in qs]
        done = Solve.query.filter(Solve.user_id == user.id, Solve.question_id.in_(ids)).count()
        return done, len(qs)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False)
    position = db.Column(db.Integer, default=0)
    title = db.Column(db.String(200))
    body_md = db.Column(db.Text)
    questions = db.relationship("Question", backref="task", order_by="Question.position",
                                cascade="all, delete-orphan")


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    key = db.Column(db.String(80))  # stabile ID aus YAML (für Re-Import)
    position = db.Column(db.Integer, default=0)
    prompt = db.Column(db.Text, nullable=False)
    answer_hashes = db.Column(db.Text, nullable=False)  # JSON-Liste von SHA-256
    answer_format = db.Column(db.String(120))           # z. B. "GOLM{...}"
    case_sensitive = db.Column(db.Boolean, default=False)
    points = db.Column(db.Integer, default=10)
    hint = db.Column(db.Text)
    explanation = db.Column(db.Text)  # wird nach dem Lösen angezeigt

    def check(self, submitted: str) -> bool:
        return hash_answer(submitted, self.case_sensitive) in json.loads(self.answer_hashes)


class Solve(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "question_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"),
                            nullable=False)
    points_awarded = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    question = db.relationship("Question")


class HintUse(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "question_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"),
                            nullable=False)


class Submission(db.Model):
    """Protokoll aller Antworten (Rate-Limit + Admin-Auswertung). Antworttext wird NICHT gespeichert."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"))
    correct = db.Column(db.Boolean)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class Path(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    audience = db.Column(db.String(200))
    sort_order = db.Column(db.Integer, default=100)
    items = db.relationship("PathRoom", order_by="PathRoom.position",
                            cascade="all, delete-orphan")

    @property
    def rooms(self):
        return [i.room for i in self.items if i.room.published]


class PathRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path_id = db.Column(db.Integer, db.ForeignKey("path.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False)
    position = db.Column(db.Integer, default=0)
    room = db.relationship("Room")


class LabInstance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False)
    vmid = db.Column(db.Integer)
    node = db.Column(db.String(60))
    ip = db.Column(db.String(60))
    # provisioning | running | stopping | stopped | error
    status = db.Column(db.String(20), default="provisioning", index=True)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    expires_at = db.Column(db.DateTime)

    user = db.relationship("User")
    room = db.relationship("Room")

    ACTIVE = ("provisioning", "running", "stopping")

    @property
    def seconds_left(self):
        if not self.expires_at:
            return 0
        return max(0, int((self.expires_at - utcnow()).total_seconds()))
