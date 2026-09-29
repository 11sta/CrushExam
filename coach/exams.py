# -*- coding: utf-8 -*-
"""Exam registry: manage multiple exams with full isolation.

Each exam has its own workspace directory (chapters, quiz bank, figures, state).
A global registry file (~/.crushexam/exam_registry.json) maps exam_id → workspace
and tracks the active exam. Switching exams is instant and safe.
"""
import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
import functools
from .workspace_lock import locked

REGISTRY_DIR = os.path.join(os.path.expanduser("~"), ".crushexam")
REGISTRY_FILE = os.path.join(REGISTRY_DIR, "exam_registry.json")
# Keep backward compat with the old ECC Flash pointer
OLD_POINTER = os.path.join(os.path.expanduser("~"), ".exam-cram-coach", "last_workspace")

EXAM_TYPES = ("final", "certification", "skill", "midterm")
GOALS = ("pass", "high", "long")


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _read_registry():
    """Load the global registry, or create an empty one."""
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {"active_exam": None, "exams": {}}


def _write_registry(reg):
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".registry-", suffix=".tmp", dir=REGISTRY_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, REGISTRY_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _registry_transaction(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        # All CLI paths take workspace first, then registry. Never the reverse.
        with locked(REGISTRY_DIR):
            return fn(*args, **kwargs)
    return wrapped


def workspace_conflict(exam_id, workspace):
    """Return another registered exam using this workspace, or None.

    Different exam IDs may share a materials folder but cannot share the
    working state, question bank or blueprint under one workspace.
    """
    real_workspace = os.path.realpath(os.path.abspath(workspace))
    for other_id, entry in _read_registry().get("exams", {}).items():
        if other_id != exam_id and os.path.realpath(entry.get("workspace", "")) == real_workspace:
            return entry
    return None


def suggest_workspace(materials_path, exam_id, workspace=None):
    """Choose an isolated workspace while preserving the original default.

    Additional exams live beneath the original ``exam-cram`` directory, which
    the existing materials scanner already excludes. A later rescan never
    ingests its own progress or question bank as course material.
    """
    if workspace:
        conflict = workspace_conflict(exam_id, workspace)
        if conflict:
            raise ValueError("workspace belongs to exam %s" % conflict["exam_id"])
        return os.path.abspath(workspace)
    registered = get_exam(exam_id)
    if registered:
        return os.path.abspath(registered["workspace"])
    materials = os.path.abspath(materials_path)
    legacy = os.path.join(materials, "exam-cram")
    legacy_exam = None
    legacy_state = os.path.join(legacy, "study_state.json")
    if os.path.isfile(legacy_state):
        try:
            with open(legacy_state, encoding="utf-8") as fh:
                legacy_exam = json.load(fh).get("exam_id") or "unassigned_legacy_exam"
        except (ValueError, OSError):
            legacy_exam = "unreadable_existing_workspace"
    if legacy_exam in (None, exam_id) and workspace_conflict(exam_id, legacy) is None:
        return legacy
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(exam_id)).strip("-")[:45] or "exam"
    suffix = hashlib.sha1(str(exam_id).encode("utf-8")).hexdigest()[:8]
    return os.path.join(legacy, "exams", "%s-%s" % (safe_id, suffix))


@_registry_transaction
def register(exam_id, course, exam_type, exam_date, goal,
              workspace, materials_path, weekly_hours=None,
              target_score=None, timezone="Asia/Shanghai",
              scope=None, question_types=None):
    """Register a new exam or update an existing one. Returns the registry entry.

    scope: list of {"item": str, "source": str, "confirmed": bool} — the
           confirmed exam scope (e.g. chapters, topics). Each entry should
           note its source (teacher/official/student guess) and whether it
           has been confirmed. Empty/None means "unknown".
    question_types: list of strings describing the exam's question types
                    (e.g. ["选择题", "简答题", "编程题"]). None means "unknown".
    """
    conflict = workspace_conflict(exam_id, workspace)
    if conflict:
        raise ValueError("workspace belongs to exam %s" % conflict["exam_id"])
    reg = _read_registry()
    entry = {
        "exam_id": exam_id,
        "course": course,
        "exam_type": exam_type or "final",
        "exam_date": exam_date,
        "goal": goal or "pass",
        "workspace": os.path.abspath(workspace),
        "materials_path": os.path.abspath(materials_path),
        "weekly_hours": weekly_hours,
        "target_score": target_score,
        "timezone": timezone,
        "scope": scope or [],           # [{"item": str, "source": str, "confirmed": bool}]
        "question_types": question_types or [],  # ["选择题", "简答题", ...]
        "created": reg["exams"].get(exam_id, {}).get("created", _now()),
        "updated": _now(),
    }
    reg["exams"][exam_id] = entry
    reg["active_exam"] = exam_id
    _write_registry(reg)
    # Also update the old pointer for backward compat
    try:
        os.makedirs(os.path.dirname(OLD_POINTER), exist_ok=True)
        with open(OLD_POINTER, "w", encoding="utf-8") as fh:
            fh.write(entry["workspace"])
    except OSError:
        pass
    return entry


def list_exams():
    """Return (list of entries, active_exam_id)."""
    reg = _read_registry()
    entries = list(reg["exams"].values())
    entries.sort(key=lambda e: e.get("created", ""))
    return entries, reg.get("active_exam")


def get_active_workspace():
    """Return the workspace path of the active exam, or None."""
    reg = _read_registry()
    aid = reg.get("active_exam")
    if aid and aid in reg["exams"]:
        return reg["exams"][aid]["workspace"]
    # Fall back to old pointer
    if os.path.exists(OLD_POINTER):
        cand = open(OLD_POINTER, encoding="utf-8").read().strip()
        if cand and os.path.exists(cand):
            return cand
    return None


def get_active_exam_id():
    """Return the active exam_id, or None."""
    reg = _read_registry()
    return reg.get("active_exam")


@_registry_transaction
def switch(exam_id):
    """Switch the active exam. Returns the entry or None if not found."""
    reg = _read_registry()
    if exam_id not in reg["exams"]:
        return None
    reg["active_exam"] = exam_id
    _write_registry(reg)
    entry = reg["exams"][exam_id]
    # Update old pointer too
    try:
        os.makedirs(os.path.dirname(OLD_POINTER), exist_ok=True)
        with open(OLD_POINTER, "w", encoding="utf-8") as fh:
            fh.write(entry["workspace"])
    except OSError:
        pass
    return entry


def get_exam(exam_id):
    """Return a single exam entry, or None."""
    reg = _read_registry()
    return reg["exams"].get(exam_id)


@_registry_transaction
def remove(exam_id):
    """Remove an exam from the registry (does not delete files). Returns True if removed."""
    reg = _read_registry()
    if exam_id not in reg["exams"]:
        return False
    del reg["exams"][exam_id]
    if reg.get("active_exam") == exam_id:
        reg["active_exam"] = next(iter(reg["exams"]), None)
    _write_registry(reg)
    return True


def migrate_old_pointer():
    """If the old ECC Flash pointer exists but the registry is empty, try to import it."""
    reg = _read_registry()
    if reg["exams"]:
        return None
    if not os.path.exists(OLD_POINTER):
        return None
    cand = open(OLD_POINTER, encoding="utf-8").read().strip()
    if not cand or not os.path.exists(cand):
        return None
    # Register the old workspace as "migrated_legacy"
    entry = register(
        exam_id="migrated_legacy",
        course="Migrated Course",
        exam_type="final",
        exam_date=None,
        goal="pass",
        workspace=cand,
        materials_path=cand,
    )
    return entry
