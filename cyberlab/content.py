"""Importiert Räume (content/rooms/*.yaml) und Lernpfade (content/paths.yaml).

Der Import ist idempotent: Räume werden über `slug`, Fragen über `key` erkannt,
damit bereits erzielte Lösungen bei Text-Änderungen erhalten bleiben.
"""
import glob
import json
import os

import yaml

from .extensions import db
from .models import (HintUse, Path, PathRoom, Question, Room, Solve, Submission, Task,
                     hash_answer)

VALID_DIFFICULTIES = {"sehr-leicht", "leicht", "mittel", "schwer"}


class ContentError(ValueError):
    pass


def _answer_hashes(q, case_sensitive):
    if "answer_sha256" in q:
        vals = q["answer_sha256"]
        return [vals] if isinstance(vals, str) else list(vals)
    answers = q.get("answer")
    if answers is None:
        raise ContentError(f"Frage '{q.get('prompt')}' hat keine Antwort")
    if not isinstance(answers, list):
        answers = [answers]
    return [hash_answer(str(a), case_sensitive) for a in answers]


def _import_room(data, filename):
    for field in ("slug", "title", "tasks"):
        if field not in data:
            raise ContentError(f"{filename}: Feld '{field}' fehlt")
    if data.get("difficulty") and data["difficulty"] not in VALID_DIFFICULTIES:
        raise ContentError(f"{filename}: ungültige difficulty '{data['difficulty']}'")

    room = Room.query.filter_by(slug=data["slug"]).first() or Room(slug=data["slug"])
    room.title = data["title"]
    room.summary = data.get("summary", "")
    room.category = data.get("category", "Allgemein")
    room.difficulty = data.get("difficulty", "leicht")
    room.estimated_minutes = data.get("estimated_minutes")
    room.tags = ",".join(data.get("tags", []))
    room.published = data.get("published", True)
    room.sort_order = data.get("order", 100)
    lab = data.get("lab") or {}
    room.lab_template_vmid = lab.get("template_vmid")
    room.lab_minutes = lab.get("minutes")
    room.lab_info = lab.get("info")
    db.session.add(room)
    db.session.flush()

    existing_q = {q.key: q for t in room.tasks for q in t.questions if q.key}
    seen_keys = set()
    old_tasks = list(room.tasks)
    new_tasks = []

    for t_pos, t in enumerate(data["tasks"]):
        task = old_tasks[t_pos] if t_pos < len(old_tasks) else Task(room=room)
        task.position = t_pos
        task.title = t.get("title", f"Aufgabe {t_pos + 1}")
        task.body_md = t.get("body", "")
        new_q = []
        for q_pos, q in enumerate(t.get("questions", [])):
            key = q.get("key") or f"{data['slug']}-{t_pos}-{q_pos}"
            if key in seen_keys:
                raise ContentError(f"{filename}: doppelter Fragen-key '{key}'")
            seen_keys.add(key)
            question = existing_q.get(key) or Question(key=key)
            question.position = q_pos
            question.prompt = q["prompt"]
            question.case_sensitive = bool(q.get("case_sensitive", False))
            question.answer_hashes = json.dumps(_answer_hashes(q, question.case_sensitive))
            question.answer_format = q.get("format")
            question.points = int(q.get("points", 10))
            question.hint = q.get("hint")
            question.explanation = q.get("explanation")
            new_q.append(question)
        task.questions = new_q
        new_tasks.append(task)

    room.tasks = new_tasks
    return room


def import_content(content_dir):
    stats = {"rooms": 0, "paths": 0}
    room_files = sorted(glob.glob(os.path.join(content_dir, "rooms", "*.yaml")))
    try:
        for fn in room_files:
            with open(fn, encoding="utf-8") as fh:
                _import_room(yaml.safe_load(fh), os.path.basename(fn))
            stats["rooms"] += 1
        db.session.flush()

        paths_file = os.path.join(content_dir, "paths.yaml")
        if os.path.exists(paths_file):
            with open(paths_file, encoding="utf-8") as fh:
                paths = yaml.safe_load(fh) or []
            for order, p in enumerate(paths):
                path = Path.query.filter_by(slug=p["slug"]).first() or Path(slug=p["slug"])
                path.title = p["title"]
                path.description = p.get("description", "")
                path.audience = p.get("audience", "")
                path.sort_order = order
                items = []
                for pos, slug in enumerate(p.get("rooms", [])):
                    room = Room.query.filter_by(slug=slug).first()
                    if not room:
                        raise ContentError(f"paths.yaml: Raum '{slug}' existiert nicht")
                    items.append(PathRoom(room=room, position=pos))
                path.items = items
                db.session.add(path)
                stats["paths"] += 1
        db.session.flush()
        # Lösungen zu entfernten Fragen aufräumen (SQLite erzwingt keine FKs)
        live_ids = db.session.query(Question.id)
        for model in (Solve, HintUse, Submission):
            model.query.filter(~model.question_id.in_(live_ids)).delete(
                synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return stats
