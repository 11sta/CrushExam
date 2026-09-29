# -*- coding: utf-8 -*-
"""Offline one-question UI. It exports a submission, never grades independently.

No reference key is included before server-side submission/grading. Files are
explicitly imported by the host; no claim of a live TeleAgent integration.
"""
import base64
import html
import json
import mimetypes
import secrets
from pathlib import Path
from . import attempts as at, tasks, evidence


def _image(workspace, q, rel):
    root = Path(workspace).resolve()
    path = (Path(rel) if Path(rel).is_absolute() else root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or path.stat().st_size > 8 * 1024 * 1024:
        return None
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:%s;base64,%s" % (mimetypes.guess_type(path.name)[0] or "image/png", data)


def write(path, workspace, state, a=None, q=None):
    task = next((t for t in state.get("tasks", []) if a and t["id"] == a.get("task_id")), None) or tasks.current(state)
    if a and a["status"] == "presented":
        a.setdefault("delivery_token", secrets.token_urlsafe(24))
    data = {"schema": "crushexam-workbench-v1", "exam_id": state.get("exam_id"),
            "course": state["course"], "task": task,
            "attempt_id": a["id"] if a else None, "qid": q["id"] if q else None,
            "status": a["status"] if a else "no_question",
            "item_version": a.get("item_version") if a else None,
            "delivery_token": a.get("delivery_token") if a else None,
            "question": q.get("question") if q else "当前没有未答题。回到对话继续当前任务，或查看本次反馈。",
            "options": q.get("options", []) if q else [],
            "context": (q.get("context") or {}).get("text") if q else None,
            "source": q.get("source") if q else None,
            "raw_answer": a.get("raw_answer") if a else None,
            "counts": {"attempts": len(state.get("history", [])),
                       "tasks_done": sum(t["status"] not in tasks.OPEN for t in state.get("tasks", [])),
                       "tasks_total": len(state.get("tasks", []))},
            "figures": [img for img in (_image(workspace, q, p) for p in (q.get("figures") or [])) if img] if q else [],
            "feedback": None}
    if a and a["status"] == "graded":
        data["feedback"] = {"result": a.get("result"), "evidence_level": a.get("evidence_level"),
                            "note": a.get("note"), "rubric": a.get("rubric"),
                            "evidence_label": evidence.attempt_label(a),
                            "method_status": a.get("method_status"), "transfer_kind": a.get("transfer_kind"),
                            "novelty": a.get("novelty"),
                            "reference": q.get("answer") if q else None}
    template = (Path(__file__).resolve().parents[1] / "templates" / "workbench.html").read_text(encoding="utf-8")
    safe_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    content = template.replace("__CRUSHEXAM_DATA__", safe_json)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")
    return str(Path(path).resolve())


def read_submission(path, state, a):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 300000:
        raise at.AttemptError("作答文件不存在或过大。")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "crushexam-submission-v1":
        raise at.AttemptError("不是有效的CrushExam离线作答文件。")
    for name, expected in (("exam_id", state.get("exam_id")), ("attempt_id", a["id"]), ("qid", a["qid"]),
                           ("item_version", a.get("item_version")), ("delivery_token", a.get("delivery_token"))):
        if data.get(name) != expected or expected is None:
            raise at.AttemptError("离线作答的%s不匹配；可能来自另一考试或旧题。" % name)
    if data.get("action") not in ("submit", "defer"):
        raise at.AttemptError("无效的离线作答动作。")
    if not isinstance(data.get("hinted", False), bool):
        raise at.AttemptError("hinted 必须为布尔值。")
    return data
