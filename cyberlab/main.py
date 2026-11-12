import hashlib
from datetime import date, timedelta

from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required
from sqlalchemy import func

from .extensions import db
from .models import (HintUse, LabInstance, Path, Question, Room, Solve, Submission, Task,
                     User, utcnow)

bp = Blueprint("main", __name__)


def room_of_the_day():
    rooms = Room.query.filter_by(published=True).order_by(Room.id).all()
    if not rooms:
        return None
    idx = int(hashlib.sha256(date.today().isoformat().encode()).hexdigest(), 16) % len(rooms)
    return rooms[idx]


def leaderboard(since=None, department=None, limit=50):
    q = (db.session.query(User, func.sum(Solve.points_awarded).label("pts"),
                          func.count(Solve.id).label("cnt"))
         .join(Solve, Solve.user_id == User.id)
         .filter(User.show_on_leaderboard.is_(True), User.is_active_flag.is_(True)))
    if since:
        q = q.filter(Solve.created_at >= since)
    if department:
        q = q.filter(User.department == department)
    return q.group_by(User.id).order_by(func.sum(Solve.points_awarded).desc()).limit(limit).all()


def department_ranking():
    rows = (db.session.query(User.department, func.sum(Solve.points_awarded),
                             func.count(func.distinct(User.id)))
            .join(Solve, Solve.user_id == User.id)
            .filter(User.department.isnot(None))
            .group_by(User.department).all())
    result = [{"name": d, "points": p or 0, "members": m,
               "avg": round((p or 0) / m) if m else 0} for d, p, m in rows]
    return sorted(result, key=lambda r: r["avg"], reverse=True)


def user_rank(user):
    mine = user.points
    higher = (db.session.query(Solve.user_id).join(User, User.id == Solve.user_id)
              .filter(User.show_on_leaderboard.is_(True))
              .group_by(Solve.user_id)
              .having(func.sum(Solve.points_awarded) > mine).count())
    return higher + 1


@bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    stats = {"rooms": Room.query.filter_by(published=True).count(),
             "users": User.query.count(),
             "solves": Solve.query.count()}
    return render_template("index.html", stats=stats,
                           paths=Path.query.order_by(Path.sort_order).all())


@bp.get("/dashboard")
@login_required
def dashboard():
    solved_ids = {s.question_id for s in current_user.solves}
    in_progress, completed = [], []
    for room in Room.query.filter_by(published=True).order_by(Room.sort_order).all():
        ids = {q.id for q in room.questions}
        if not ids or not (ids & solved_ids):
            continue
        (completed if ids <= solved_ids else in_progress).append(
            (room, len(ids & solved_ids), len(ids)))
    recent = current_user.solves.order_by(Solve.created_at.desc()).limit(8).all()
    active_lab = LabInstance.query.filter(
        LabInstance.user_id == current_user.id,
        LabInstance.status.in_(LabInstance.ACTIVE)).first()
    return render_template("dashboard.html", in_progress=in_progress, completed=completed,
                           recent=recent, rotd=room_of_the_day(), rank=user_rank(current_user),
                           active_lab=active_lab,
                           paths=Path.query.order_by(Path.sort_order).all())


@bp.get("/rooms")
@login_required
def rooms():
    q = Room.query.filter_by(published=True)
    cat = request.args.get("category")
    diff = request.args.get("difficulty")
    search = request.args.get("q", "").strip()
    if cat:
        q = q.filter_by(category=cat)
    if diff:
        q = q.filter_by(difficulty=diff)
    if search:
        like = f"%{search}%"
        q = q.filter(Room.title.ilike(like) | Room.summary.ilike(like) | Room.tags.ilike(like))
    categories = [c for (c,) in db.session.query(Room.category).filter_by(published=True)
                  .distinct().order_by(Room.category)]
    return render_template("rooms.html", rooms=q.order_by(Room.sort_order, Room.title).all(),
                           categories=categories, difficulties=Room.DIFFICULTY_LABELS,
                           sel_cat=cat, sel_diff=diff, search=search)


@bp.get("/rooms/<slug>")
@login_required
def room(slug):
    room = Room.query.filter_by(slug=slug).first_or_404()
    if not room.published and not current_user.is_admin:
        return render_template("404.html"), 404
    solved = {s.question_id: s for s in current_user.solves.filter(
        Solve.question_id.in_([q.id for q in room.questions]))}
    hints = {h.question_id for h in HintUse.query.filter_by(user_id=current_user.id)}
    lab = None
    if room.lab_template_vmid:
        lab = (LabInstance.query.filter_by(user_id=current_user.id, room_id=room.id)
               .filter(LabInstance.status.in_(LabInstance.ACTIVE + ("error",)))
               .order_by(LabInstance.id.desc()).first())
    return render_template("room.html", room=room, solved=solved, hints=hints, lab=lab,
                           access_info=current_app.config["LAB_ACCESS_INFO"])


def _question_or_404(slug, qid):
    question = db.session.get(Question, qid)
    if not question or question.task.room.slug != slug:
        return None
    return question


@bp.post("/rooms/<slug>/answer/<int:qid>")
@login_required
def answer(slug, qid):
    question = _question_or_404(slug, qid)
    if not question:
        return render_template("404.html"), 404
    anchor = f"#q-{qid}"
    target = url_for("main.room", slug=slug) + anchor
    if Solve.query.filter_by(user_id=current_user.id, question_id=qid).first():
        return redirect(target)

    one_min_ago = utcnow() - timedelta(minutes=1)
    wrong_recent = Submission.query.filter(
        Submission.user_id == current_user.id, Submission.correct.is_(False),
        Submission.created_at >= one_min_ago).count()
    if wrong_recent >= current_app.config["MAX_WRONG_ANSWERS_PER_MINUTE"]:
        flash("Zu viele falsche Versuche – bitte kurz warten.", "warning")
        return redirect(target)

    correct = question.check(request.form.get("answer", ""))
    db.session.add(Submission(user_id=current_user.id, question_id=qid, correct=correct))
    if correct:
        used_hint = HintUse.query.filter_by(user_id=current_user.id, question_id=qid).first()
        pts = question.points // 2 if used_hint else question.points
        db.session.add(Solve(user_id=current_user.id, question_id=qid, points_awarded=pts))
        current_user.touch_streak()
        flash(f"Richtig! +{pts} Punkte", "success")
    else:
        flash("Leider falsch – versuch es nochmal.", "error")
    db.session.commit()

    if correct:
        room = question.task.room
        done, total = room.progress_for(current_user)
        if done == total:
            flash(f"🎉 Raum „{room.title}“ abgeschlossen!", "success")
    return redirect(target)


@bp.post("/rooms/<slug>/hint/<int:qid>")
@login_required
def hint(slug, qid):
    question = _question_or_404(slug, qid)
    if question and question.hint and not HintUse.query.filter_by(
            user_id=current_user.id, question_id=qid).first():
        db.session.add(HintUse(user_id=current_user.id, question_id=qid))
        db.session.commit()
    return redirect(url_for("main.room", slug=slug) + f"#q-{qid}")


@bp.get("/paths")
@login_required
def paths():
    return render_template("paths.html", paths=Path.query.order_by(Path.sort_order).all())


@bp.get("/paths/<slug>")
@login_required
def path(slug):
    p = Path.query.filter_by(slug=slug).first_or_404()
    return render_template("path.html", path=p)


@bp.get("/leaderboard")
@login_required
def leaderboard_view():
    period = request.args.get("period", "all")
    dept = request.args.get("department") or None
    since = utcnow() - timedelta(days=30) if period == "30d" else None
    return render_template("leaderboard.html", rows=leaderboard(since, dept),
                           departments=current_app.config["DEPARTMENTS"],
                           dept_ranking=department_ranking(), period=period, sel_dept=dept)


@bp.get("/tools")
@login_required
def tools():
    return render_template("tools.html")


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    cfg = current_app.config
    if request.method == "POST":
        dept = request.form.get("department")
        if dept in cfg["DEPARTMENTS"]:
            current_user.department = dept
        current_user.display_name = request.form.get("display_name", "").strip()[:120] or None
        current_user.show_on_leaderboard = bool(request.form.get("show_on_leaderboard"))
        if current_user.auth_source == "local" and request.form.get("new_password"):
            if not current_user.check_password(request.form.get("old_password", "")):
                flash("Aktuelles Passwort ist falsch.", "error")
                return redirect(url_for("main.profile"))
            if len(request.form["new_password"]) < 12:
                flash("Neues Passwort muss mindestens 12 Zeichen lang sein.", "error")
                return redirect(url_for("main.profile"))
            current_user.set_password(request.form["new_password"])
        db.session.commit()
        flash("Profil gespeichert.", "success")
        return redirect(url_for("main.profile"))

    solved_ids = {s.question_id for s in current_user.solves}
    badges = [r for r in Room.query.filter_by(published=True).all()
              if r.questions and {q.id for q in r.questions} <= solved_ids]
    by_cat = (db.session.query(Room.category, func.sum(Solve.points_awarded))
              .join(Task, Task.room_id == Room.id).join(Question, Question.task_id == Task.id)
              .join(Solve, Solve.question_id == Question.id)
              .filter(Solve.user_id == current_user.id).group_by(Room.category).all())
    return render_template("profile.html", badges=badges, by_cat=by_cat,
                           departments=cfg["DEPARTMENTS"], rank=user_rank(current_user),
                           vpn_enabled=bool(cfg.get("LAB_VPN_CONFIG_DIR")))
