import csv
import io
from functools import wraps

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, url_for)
from flask_login import current_user, login_required
from sqlalchemy import func

from .content import import_content
from .extensions import db
from .labs import active_query, stop_lab
from .models import (LabInstance, Question, Room, Solve, Submission, Task, User)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.is_admin:
            abort(403)
        return fn(*a, **kw)
    return wrapper


def room_stats():
    users_total = User.query.filter_by(is_active_flag=True).count() or 1
    rows = []
    for room in Room.query.order_by(Room.sort_order).all():
        qids = [q.id for q in room.questions]
        if not qids:
            continue
        per_user = (db.session.query(Solve.user_id, func.count(Solve.id))
                    .filter(Solve.question_id.in_(qids)).group_by(Solve.user_id).all())
        started = len(per_user)
        completed = sum(1 for _, c in per_user if c == len(qids))
        wrong = Submission.query.filter(Submission.question_id.in_(qids),
                                        Submission.correct.is_(False)).count()
        rows.append({"room": room, "started": started, "completed": completed,
                     "rate": round(100 * completed / users_total), "wrong": wrong})
    return rows


@bp.get("/")
@admin_required
def index():
    stats = {"users": User.query.count(), "rooms": Room.query.count(),
             "solves": Solve.query.count(), "labs": active_query().count()}
    return render_template("admin/index.html", stats=stats, room_rows=room_stats(),
                           labs=active_query().order_by(LabInstance.created_at).all(),
                           errors=LabInstance.query.filter_by(status="error").all())


@bp.get("/users")
@admin_required
def users():
    rows = (db.session.query(User, func.coalesce(func.sum(Solve.points_awarded), 0))
            .outerjoin(Solve, Solve.user_id == User.id).group_by(User.id)
            .order_by(User.username).all())
    return render_template("admin/users.html", rows=rows)


@bp.post("/users/<int:uid>/toggle-admin")
@admin_required
def toggle_admin(uid):
    user = db.get_or_404(User, uid)
    if user.id == current_user.id:
        flash("Eigene Admin-Rechte können nicht entzogen werden.", "warning")
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:uid>/toggle-active")
@admin_required
def toggle_active(uid):
    user = db.get_or_404(User, uid)
    if user.id != current_user.id:
        user.is_active_flag = not user.is_active_flag
        db.session.commit()
    return redirect(url_for("admin.users"))


@bp.post("/labs/<int:lab_id>/stop")
@admin_required
def force_stop(lab_id):
    lab = db.get_or_404(LabInstance, lab_id)
    stop_lab(lab)
    flash(f"VM {lab.vmid} wird gelöscht.", "info")
    return redirect(url_for("admin.index"))


@bp.post("/content/reload")
@admin_required
def reload_content():
    try:
        stats = import_content(current_app.config["CONTENT_DIR"])
        flash(f"Inhalte importiert: {stats['rooms']} Räume, {stats['paths']} Lernpfade.",
              "success")
    except Exception as exc:  # noqa: BLE001
        flash(f"Import fehlgeschlagen: {exc}", "error")
    return redirect(url_for("admin.index"))


@bp.get("/export/progress.csv")
@admin_required
def export_progress():
    """Aggregierter Fortschritt je Institut und Raum (keine Einzelpersonen – DSGVO/BetrVG)."""
    rows = (db.session.query(User.department, Room.title,
                             func.count(func.distinct(Solve.user_id)), func.count(Solve.id))
            .join(Solve, Solve.user_id == User.id)
            .join(Question, Question.id == Solve.question_id)
            .join(Task, Task.id == Question.task_id).join(Room, Room.id == Task.room_id)
            .group_by(User.department, Room.title).all())
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Institut", "Raum", "Teilnehmende", "Gelöste Fragen"])
    for r in rows:
        w.writerow([r[0] or "–", r[1], r[2], r[3]])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=fortschritt.csv"})
