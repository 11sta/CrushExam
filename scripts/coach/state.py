# -*- coding: utf-8 -*-
"""study_state.json: the one file that remembers progress. progress.md and notebook.md are views.

v6 changes (CrushExam):
  - exam_id, exam_date (ISO), goal fields added
  - history entries carry evidence_level and is_independent
  - mistakes carry next_review_date, review_count, evidence_level
  - exam_days kept for backward compat; exam_date is the primary scheduler
  - post_exam_score stores the real exam score after the exam (self-reported, clearly labelled)
"""
import datetime as _dt
import json
import os
import tempfile
import shutil

STATE_FILE = "study_state.json"
PROGRESS_FILE = "progress.md"
NOTEBOOK_FILE = "notebook.md"

CURRENT_VERSION = 7


def now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def today():
    return _dt.date.today().isoformat()


def new_state(course, language, days, materials, chapters, slice_chars,
              exam_id=None, exam_date=None, goal=None):
    return {
        "version": CURRENT_VERSION,
        "exam_id": exam_id,
        "course": course,
        "language": language,
        "exam_days": days,          # kept for backward compat
        "exam_date": exam_date,      # ISO date string, e.g. "2027-01-15"
        "goal": goal or "pass",
        "materials": materials,
        "created": now(),
        "updated": now(),
        "slice_chars": slice_chars,
        "current": chapters[0]["n"] if chapters else None,
        "chapters": [
            {"n": c["n"], "title": c["title"], "status": "todo", "part": 0, "parts": c["parts"],
             "sources": c["sources"], "questions": c["questions"]}
            for c in chapters
        ],
        "history": [],   # {"qid","result","ts","chapter","evidence_level","is_independent"}
        "mistakes": [],  # {"qid","chapter","note","status","count","next_review_date","review_count","evidence_level"}
        "notes": [],     # {"chapter","type","text","ts"}
        "post_exam_score": None,  # {"score": float, "max": float, "date": str, "note": str, "source": "self-reported"}
        "unassigned_records": [],  # [{"history":[...], "mistakes":[...], "note": str}] — quarantined from v5 migration
    }


def path(ws):
    return os.path.join(ws, STATE_FILE)


def load(ws):
    p = path(ws)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        state = json.load(fh)
    return migrate(state)


def _atomic_write(p, text):
    """Unique temporary file and fsync; a killed process cannot truncate state."""
    directory = os.path.dirname(os.path.abspath(p))
    fd, tmp = tempfile.mkstemp(prefix=".crushexam-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save(ws, state):
    from . import workflow
    workflow.ensure(state)
    if os.path.isfile(path(ws)):
        with open(path(ws), encoding="utf-8") as fh:
            previous = json.load(fh)
        if previous.get("version", 5) < CURRENT_VERSION:
            backup_dir = os.path.join(ws, ".backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup = os.path.join(backup_dir, "study_state.v%s.before-v7.json" % previous.get("version", 5))
            if not os.path.exists(backup):
                shutil.copy2(path(ws), backup)
    if os.path.isfile(path(ws)) and previous.get('learning_contract_version', 0) < 2:
        backup_dir = os.path.join(ws, '.backups')
        os.makedirs(backup_dir, exist_ok=True)
        backup = os.path.join(backup_dir, 'study_state.v%s.before-v1.7.0.json' % previous.get('version', 5))
        if not os.path.exists(backup):
            shutil.copy2(path(ws), backup)
    state["version"] = CURRENT_VERSION
    state["updated"] = now()
    _atomic_write(path(ws), json.dumps(state, ensure_ascii=False, indent=1))
    _atomic_write(os.path.join(ws, PROGRESS_FILE), render_progress(state))
    _atomic_write(os.path.join(ws, NOTEBOOK_FILE), render_notebook(state))


def migrate(state):
    """Migrate supported v5/v6 states to v7 in-place. Safe and idempotent.

    Key safety rule: if the old state has history/mistakes but no exam_id,
    those records cannot be reliably assigned to a specific exam. They are
    moved to `unassigned_records` for manual review, never silently attached
    to a new exam.
    """
    if not isinstance(state, dict):
        raise ValueError("study_state.json must be a JSON object; original file was not reset.")
    contract_version = state.get('learning_contract_version', 0)
    if not isinstance(contract_version, int) or contract_version > 2 or contract_version < 0:
        raise ValueError('Unsupported learning contract version; refusing destructive downgrade.')
    v = state.get("version", 5)
    if not isinstance(v, int) or v < 5:
        raise ValueError("Unsupported state schema version; inspect a backup before migrating.")
    if v > CURRENT_VERSION:
        raise ValueError("State belongs to a newer skill version; refusing to downgrade it.")

    # v5 → v6
    if v == 5:
        state["version"] = CURRENT_VERSION
        # Add new fields with defaults
        state.setdefault("exam_id", None)
        state.setdefault("exam_date", None)
        state.setdefault("goal", "pass")
        state.setdefault("post_exam_score", None)
        state.setdefault("unassigned_records", [])

        # Safety: if old state has history/mistakes but no exam_id,
        # quarantine them into unassigned_records instead of silently
        # attributing them to whatever exam happens to be active next.
        old_history = state.get("history", [])
        old_mistakes = state.get("mistakes", [])
        has_records = bool(old_history) or bool(old_mistakes)
        no_exam_id = not state.get("exam_id")

        if has_records and no_exam_id:
            # Move old records to unassigned_records
            state["unassigned_records"] = [{
                "history": old_history[:],
                "mistakes": old_mistakes[:],
                "migrated_from_version": 5,
                "migrated_at": now(),
                "note": "Records from single-exam v5 state with no exam_id; manual assignment required.",
            }]
            # Clear the main history/mistakes so they don't get attributed to a wrong exam
            state["history"] = []
            state["mistakes"] = []
        else:
            # Normal migration: keep records in place, just add new fields
            for h in state.get("history", []):
                h.setdefault("evidence_level", "untested")
                h.setdefault("is_independent", False)
            for m in state.get("mistakes", []):
                m.setdefault("next_review_date", None)
                m.setdefault("review_count", 0)
                m.setdefault("evidence_level", "untested")

    # Also ensure fields for v6 states created before some fields existed
    state.setdefault("post_exam_score", None)
    state.setdefault("unassigned_records", [])
    state["version"] = CURRENT_VERSION
    from . import workflow
    workflow.ensure(state)
    return state


def chapter(state, n=None):
    n = state["current"] if n is None else n
    for c in state["chapters"]:
        if c["n"] == n:
            return c
    return None


def open_mistakes(state, n=None):
    return [m for m in state["mistakes"] if m["status"] == "open" and (n is None or m["chapter"] == n)]


def record_result(state, qid, chapter_n, result, note="", evidence_level="untested",
                  is_independent=False, response=None, answer_version=None,
                  grading_source=None, confidence=None, minutes_spent=None,
                  item_version=None, attempt_id=None, rubric=None, error_type=None,
                  graded_response=None, submitted_at=None,
                  score=None, max_score=None, score_source=None, score_pass=None):
    """Record a quiz attempt and update mistakes.

    evidence_level: "untested" | "hinted" | "immediate" | "delayed" | "transfer"
    """
    if attempt_id:
        existing_attempt = next((h for h in state.get("history", []) if h.get("attempt_id") == attempt_id), None)
        if existing_attempt:
            if existing_attempt.get("response") != response or existing_attempt.get("result") != result:
                raise ValueError("Cannot overwrite an immutable attempt")
            return existing_attempt
    attempt = {
        "qid": qid,
        "result": result,
        "ts": now(),
        "chapter": chapter_n,
        "evidence_level": evidence_level,
        "is_independent": is_independent,
    }
    # Optional metadata does not change the positional interface used by old
    # callers. Keep the original submission and grading basis with the verdict.
    for field, value in (("response", response), ("answer_version", answer_version),
                         ("grading_source", grading_source), ("confidence", confidence),
                         ("minutes_spent", minutes_spent), ("item_version", item_version),
                         ("attempt_id", attempt_id), ("rubric", rubric), ("error_type", error_type),
                         ("graded_response", graded_response), ("submitted_at", submitted_at),
                         ("score", score), ("max_score", max_score), ("score_source", score_source),
                         ("score_pass", score_pass)):
        if value is not None:
            attempt[field] = value
    if note:
        attempt["note"] = note
    state["history"].append(attempt)
    existing = next((m for m in state["mistakes"] if m["qid"] == qid), None)
    if result in ("wrong", "skip"):
        if existing:
            existing["count"] += 1
            existing["status"] = "open"
            if note:
                existing["note"] = note
            # Reset evidence on wrong answer
            existing["evidence_level"] = evidence_level
        else:
            state["mistakes"].append({
                "qid": qid, "chapter": chapter_n, "note": note,
                "status": "open", "count": 1,
                "next_review_date": None,
                "review_count": 0,
                "evidence_level": evidence_level,
            })
    elif result == "right":
        if existing and existing["status"] == "open":
            existing["status"] = "fixed"
        # Update evidence level in mistakes record (create if not exists)
        if existing:
            existing["evidence_level"] = max_evidence(existing.get("evidence_level", "untested"), evidence_level)
        elif evidence_level != "untested":
            # Track successful attempts even without prior mistakes
            state["mistakes"].append({
                "qid": qid, "chapter": chapter_n, "note": "",
                "status": "fixed", "count": 0,
                "next_review_date": None,
                "review_count": 0,
                "evidence_level": evidence_level,
            })

    return attempt


def max_evidence(old, new):
    """Return the higher evidence level."""
    levels = ["untested", "hinted", "immediate", "delayed", "transfer"]
    try:
        return new if levels.index(new) > levels.index(old) else old
    except (ValueError, IndexError):
        return new


def set_review_date(state, qid, review_date):
    """Set the next review date for a question."""
    existing = next((m for m in state["mistakes"] if m["qid"] == qid), None)
    if existing:
        existing["next_review_date"] = review_date
    else:
        state["mistakes"].append({
            "qid": qid, "chapter": None, "note": "",
            "status": "open", "count": 0,
            "next_review_date": review_date,
            "review_count": 0,
            "evidence_level": "untested",
        })


def get_evidence_level(state, qid):
    """Evidence since the latest incorrect answer, not lifetime best.

    A later wrong/skip resets the current claim. Earlier successes remain in
    history and can be shown separately without concealing the present gap.
    """
    recent = [h for h in state.get("history", []) if h.get("qid") == qid]
    if recent:
        best = "untested"
        for h in recent:
            if h.get("result") in ("wrong", "skip"):
                best = "untested"
            elif h.get("result") == "right":
                best = max_evidence(best, h.get("evidence_level", "untested"))
        return best
    # Fallback for legacy snapshots containing only mistake entries.
    m = next((m for m in state["mistakes"] if m["qid"] == qid), None)
    return m.get("evidence_level", "untested") if m else "untested"


def latest_attempt(state, qid):
    """Return the last persisted attempt, including its raw response if known."""
    return next((h for h in reversed(state.get("history", []))
                 if h.get("qid") == qid), None)


def current_evidence_level(state, qid):
    """Explicit alias for consumers displaying current rather than peak ability."""
    return get_evidence_level(state, qid)


def reconcile_question_records(state, old_state, old_bank, new_bank, exam_id=None):
    """Carry forward only records tied to an unchanged question and answer.

    Old banks may use the former short qid. Compute the complete question and
    answer hashes directly from both banks, then remap the old qid. A missing
    bank, ambiguous qid, changed question/solution, or different exam archives
    the record in unassigned_records; no old verdict is silently reused.

    Return a summary including ``qid_map`` for any course blueprint migration.
    Chapter progress/notes should only be copied by the caller after checking
    that the old state's exam_id is exactly the requested exam_id.
    """
    from . import questions as qmod

    summary = {"retained_history": 0, "retained_mistakes": 0,
               "quarantined_history": 0, "quarantined_mistakes": 0,
               "qid_map": {}}
    if not old_state:
        return summary
    state["unassigned_records"] = list(old_state.get("unassigned_records") or [])
    old_history = old_state.get("history") or []
    old_mistakes = old_state.get("mistakes") or []
    pending = old_state.get("pending") or {}
    matching_exam = bool(exam_id and old_state.get("exam_id") == exam_id
                         and state.get("exam_id") == exam_id)

    old_by_id = {}
    for q in old_bank or []:
        old_by_id.setdefault(q.get("id"), []).append(q)
    new_by_id = {}
    for q in new_bank or []:
        new_by_id.setdefault(qmod.question_fingerprint(q), []).append(q)

    records_by_qid = {}
    for entry in old_history:
        records_by_qid.setdefault(entry.get("qid"), {"history": [], "mistakes": []})["history"].append(entry)
    for entry in old_mistakes:
        records_by_qid.setdefault(entry.get("qid"), {"history": [], "mistakes": []})["mistakes"].append(entry)
    for qid, groups in records_by_qid.items():
        reason = None
        old_items = old_by_id.get(qid) or []
        if not matching_exam:
            reason = "different_or_unidentified_exam"
        elif len(old_items) != 1:
            reason = "old_bank_missing_or_ambiguous"
        else:
            old_q = old_items[0]
            new_id = qmod.question_fingerprint(old_q)
            matching_items = new_by_id.get(new_id) or []
            stored_records = groups["history"] + groups["mistakes"]
            if any((record.get("item_version") and
                    record["item_version"] != qmod.question_version(old_q)) or
                   (record.get("answer_version") and
                    record["answer_version"] != qmod.question_answer_version(old_q))
                   for record in stored_records):
                reason = "stored_attempt_version_mismatch"
            elif len(matching_items) != 1:
                reason = "question_changed_or_missing"
            elif qmod.question_answer_version(old_q) != qmod.question_answer_version(matching_items[0]):
                reason = "answer_or_scoring_source_changed"
            else:
                new_q = matching_items[0]
                answer_version = qmod.question_answer_version(new_q)
                item_version = qmod.question_version(new_q)
                summary["qid_map"][qid] = new_id
                for h in groups["history"]:
                    migrated = dict(h, qid=new_id, chapter=new_q.get("chapter"),
                                    item_version=item_version, answer_version=answer_version)
                    state["history"].append(migrated)
                    summary["retained_history"] += 1
                for m in groups["mistakes"]:
                    migrated = dict(m, qid=new_id, chapter=new_q.get("chapter"),
                                    item_version=item_version, answer_version=answer_version)
                    state["mistakes"].append(migrated)
                    summary["retained_mistakes"] += 1
                if qid in pending:
                    state["unassigned_records"].append({
                        "qid": qid, "exam_id": old_state.get("exam_id"),
                        "reason": "pending_ungraded_at_rebuild", "archived_at": now(),
                        "history": [], "mistakes": [], "pending": pending[qid],
                    })
                continue
        if groups["history"] or groups["mistakes"] or qid in pending:
            state["unassigned_records"].append({
                "qid": qid, "exam_id": old_state.get("exam_id"),
                "reason": reason, "archived_at": now(),
                "history": groups["history"], "mistakes": groups["mistakes"],
                "pending": pending.get(qid),
            })
            summary["quarantined_history"] += len(groups["history"])
            summary["quarantined_mistakes"] += len(groups["mistakes"])
    # A submitted but as-yet ungraded answer is not a verified attempt and
    # must not reappear as an already submitted quiz in a refreshed bank.
    for qid, submission in pending.items():
        if qid not in records_by_qid:
            state["unassigned_records"].append({
                "qid": qid, "exam_id": old_state.get("exam_id"),
                "reason": "pending_ungraded_at_rebuild", "archived_at": now(),
                "history": [], "mistakes": [], "pending": submission,
            })
    return summary


def chapter_results(state, n):
    right = sum(1 for h in state["history"] if h["chapter"] == n and h["result"] == "right")
    asked = sum(1 for h in state["history"] if h["chapter"] == n)
    return right, asked


def bar(done, total, width=10):
    filled = int(round(width * done / total)) if total else 0
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def render_progress(state):
    zh = state["language"] == "zh"
    done = sum(1 for c in state["chapters"] if c["status"] in ("done", "verified"))
    total = len(state["chapters"])
    lines = ["# %s" % ("复习进度" if zh else "Study progress"), ""]
    lines.append("- %s: %s" % ("课程" if zh else "Course", state["course"]))
    if state.get("exam_id"):
        lines.append("- %s: %s" % ("考试" if zh else "Exam", state["exam_id"]))
    if state.get("exam_date"):
        lines.append("- %s: %s" % ("考试日期" if zh else "Exam date", state["exam_date"]))
    lines.append("- %s: %s" % ("更新" if zh else "Updated", state["updated"]))
    lines.append("- %s: %s %d/%d" % ("章节" if zh else "Chapters", bar(done, total), done, total))
    lines.append("")
    lines.append("| # | %s | %s | %s |" % (("标题", "状态", "测验") if zh else ("Title", "Status", "Quiz")))
    lines.append("| --- | --- | --- | --- |")
    for c in state["chapters"]:
        right, asked = chapter_results(state, c["n"])
        mark = "→ " if c["n"] == state["current"] else ""
        lines.append("| %s%d | %s | %s | %d/%d |" % (mark, c["n"], c["title"], c["status"], right, asked))
    lines.append("")
    lines.append("## %s" % ("错题" if zh else "Mistakes"))
    om = [m for m in state["mistakes"] if m["status"] == "open"]
    if not om:
        lines.append("- (%s)" % ("暂无" if zh else "none"))
    for m in om:
        ev = m.get("evidence_level", "untested")
        lines.append("- %s (ch%s, ×%d, %s) %s" % (m["qid"], m.get("chapter") or "未归类", m["count"], ev, m.get("note", "")))
    lines.append("")
    conf = [n for n in state["notes"] if n["type"] == "confusion"]
    lines.append("## %s" % ("疑难点" if zh else "Confusions"))
    if not conf:
        lines.append("- (%s)" % ("暂无" if zh else "none"))
    for n in conf:
        lines.append("- ch%s: %s" % (n["chapter"], n["text"]))
    return "\n".join(lines) + "\n"


def render_notebook(state):
    zh = state["language"] == "zh"
    lines = ["# %s" % ("学习笔记" if zh else "Notebook"), ""]
    for c in state["chapters"]:
        notes = [n for n in state["notes"] if n["chapter"] == c["n"]]
        if not notes:
            continue
        lines.append("## %s %d: %s" % ("第" if zh else "Chapter", c["n"], c["title"]) if not zh
                     else "## 第 %d 章：%s" % (c["n"], c["title"]))
        for n in notes:
            lines.append("- [%s %s] %s" % (n["type"], n["ts"], n["text"]))
        lines.append("")
    return "\n".join(lines) + "\n"
