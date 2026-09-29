# -*- coding: utf-8 -*-
"""Exam blueprint: KC dictionary, question→KC mapping, stratified sampling, ability gaps.

The blueprint is course-specific DATA, not code. The tutor writes a KC
dictionary (knowledge components extracted from the course notes / syllabus)
into a JSON file and imports it via `blueprint --file`. Everything here stays
course-agnostic.

Workspace file blueprint.json:
{
  "version": 1,
  "structure": {                      # exam format, or null when unknown
    "source": "手写笔记 p.2",
    "confirmed": true,
    "sections": [{"type": "单选", "count": 15, "points": 30}, ...]
  },
  "kcs": [                            # KC dictionary
    {"id": "ch1-cia", "chapter": 1, "title": "信息安全三大目标",
     "keywords": ["保密性", "完整性"], "source": "notes"}
  ],
  "q_map": {"q_xxx": ["ch1-cia"], ...},   # auto-built by keyword matching
  "overrides": {"q_yyy": ["ch2-dos"]},    # manual --qmap fixes, kept on rebuild
  "question_meta": {"q_yyy": {"difficulty": "basic",
                     "difficulty_source": "教师题型表", "difficulty_confirmed": true}},
  "built_at": "2026-09-28 12:00"
}

Honesty rules (aligned with SKILL.md §6/§13):
  - keyword matching is a heuristic; unmapped questions are listed, never hidden
  - ability rows always carry the number of questions they are based on
  - only explicitly confirmed exam structure/knowledge-point marks imply weight;
    the number of questions in a bank never implies exam marks
"""
import datetime as _dt
import json
import os
import re

from . import state as st, evidence as ev

BLUEPRINT_FILE = "blueprint.json"

STRENGTH_LABELS = {
    "strong": ("旧版证据标签（不代表当前掌握）", "legacy evidence label"),
    "retention": ("同题隔日证据（非新题能力）", "same-item later-day evidence"),
    "variation": ("异题验证（查看类别与题数）", "cross-item evidence; inspect kind and coverage"),
    "method_pending": ("选项得分保留，方法待核验", "answer credit; reasoning unverified"),
    "medium": ("独立作答样本（仍需补测）", "independent samples; further testing needed"),
    "weak": ("受助证据，需独立复测", "assisted evidence; retest independently"),
    "gap": ("待巩固（仍有未修复题或方法错误）", "unresolved item or reasoning gap"),
    "untested": ("未测", "untested"),
}

# Evidence levels that count as an independent correct answer
_INDEP_LEVELS = ("immediate", "delayed", "transfer")
_MAX_KCS_PER_Q = 3


# ------------------------------------------------------------------ io

def path(ws):
    return os.path.join(ws, BLUEPRINT_FILE)


def load(ws):
    p = path(ws)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save(ws, bp):
    bp["built_at"] = st.now()
    tmp = path(ws) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(bp, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path(ws))


def new_blueprint():
    return {"version": 1, "structure": None, "kcs": [], "q_map": {},
            "overrides": {}, "question_meta": {}}


def import_payload(bp, data):
    """Merge a tutor-provided JSON payload into a blueprint.

    Accepts either {"structure": ..., "kcs": [...]} or a bare list of KCs.
    Rebuilds q_map, keeping existing manual overrides.
    """
    if isinstance(data, list):
        data = {"kcs": data}
    if not isinstance(data, dict):
        raise ValueError("kc file must be a JSON object or a list of KCs")
    if "structure" in data and data["structure"]:
        bp["structure"] = data["structure"]
    if "kcs" in data and data["kcs"] is not None:
        kcs = [normalize_kc(k) for k in data["kcs"]]
        # reject duplicate ids
        seen = set()
        for kc in kcs:
            if kc["id"] in seen:
                raise ValueError("duplicate KC id: %s" % kc["id"])
            seen.add(kc["id"])
        bp["kcs"] = kcs
    if "question_meta" in data:
        if not isinstance(data["question_meta"], dict):
            raise ValueError("question_meta must map question IDs to objects")
        bp["question_meta"] = {}
        for qid, meta in data["question_meta"].items():
            if not isinstance(meta, dict):
                raise ValueError("question_meta[%s] must be an object" % qid)
            # Keep supplied annotation for audit, but only verified and
            # sourced difficulty enters any ranking.
            bp["question_meta"][str(qid)] = dict(meta)
    return bp


def normalize_kc(kc):
    """Validate/normalize one KC entry."""
    if not isinstance(kc, dict):
        raise ValueError("KC must be an object: %r" % (kc,))
    kid = str(kc.get("id") or "").strip()
    if not kid:
        raise ValueError("KC missing id: %r" % (kc,))
    keywords = [str(k).strip() for k in (kc.get("keywords") or []) if str(k).strip()]
    normalized = {
        "id": kid,
        "chapter": kc.get("chapter"),
        "title": str(kc.get("title") or kid),
        "keywords": keywords,
        "source": kc.get("source") or "notes",
    }
    # Optional, verified marks for a knowledge component. A bank question's
    # point value is never treated as an exam-wide weight.
    if kc.get("weight_confirmed") is True and kc.get("weight_source"):
        try:
            points = float(kc.get("exam_points"))
        except (ValueError, TypeError):
            points = 0
        if 0 < points < float("inf"):
            normalized.update(exam_points=points, weight_confirmed=True,
                              weight_source=str(kc["weight_source"]))
    return normalized


# ------------------------------------------------------------------ keyword matching

def _question_text(q):
    parts = [q.get("question") or ""]
    parts.extend(q.get("options") or [])
    parts.append(q.get("answer") or "")
    return "\n".join(parts)


def _kw_pattern(kw):
    """Short pure-ASCII keywords (AH, SA, MAC) need word boundaries so they
    do not match inside other tokens; everything else is a substring."""
    if re.fullmatch(r"[A-Za-z0-9]{1,3}", kw):
        return re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(kw), re.I)
    return None


def match_kcs(q, kcs):
    """Return [(kc, hits)] for keyword hits in question+options+answer, best first."""
    text = _question_text(q)
    lowered = text.lower()
    hits = []
    for kc in kcs:
        count = 0
        for kw in kc["keywords"]:
            pat = _kw_pattern(kw)
            if pat is not None:
                if pat.search(text):
                    count += 1
            elif kw.lower() in lowered:  # ASCII keyword or CJK substring
                count += 1
        if count:
            hits.append((kc, count))
    hits.sort(key=lambda x: (-x[1], x[0]["id"]))
    return hits


def build_q_map(bank, kcs, overrides=None):
    """Map every bank question to up to _MAX_KCS_PER_Q KCs by keyword matching."""
    q_map = {}
    for q in bank:
        hits = match_kcs(q, kcs)
        if hits:
            q_map[q["id"]] = [kc["id"] for kc, _ in hits[:_MAX_KCS_PER_Q]]
    if overrides:
        for qid, kcs_list in overrides.items():
            if kcs_list:
                q_map[qid] = list(kcs_list)
            else:
                q_map.pop(qid, None)
    return q_map


def rebuild(bp, bank):
    """Rebuild q_map from the current KC dictionary + bank, keeping overrides."""
    overrides = bp.get("overrides") or {}
    if bp.get("kcs"):
        bp["q_map"] = build_q_map(bank, bp["kcs"], overrides)
    else:
        bp["q_map"] = {}
    return bp


def coverage(bank, q_map):
    """How many bank questions are mapped to at least one KC."""
    total = len(bank)
    mapped = sum(1 for q in bank if q["id"] in q_map)
    unmapped = [q["id"] for q in bank if q["id"] not in q_map]
    return {"total": total, "mapped": mapped, "unmapped": unmapped}


# ------------------------------------------------------------------ exam blueprint and diagnosis

_TYPE_ALIASES = {
    "choice": "choice", "single_choice": "choice", "multiple_choice": "choice",
    "单选": "choice", "单项选择": "choice", "多选": "choice", "选择": "choice",
    "选择题": "choice", "true_false": "true_false", "判断": "true_false",
    "判断题": "true_false", "正误": "true_false", "fill_blank": "fill_blank",
    "填空": "fill_blank", "填空题": "fill_blank", "subjective": "subjective",
    "简答": "subjective", "简答题": "subjective", "论述": "subjective",
    "论述题": "subjective", "计算": "subjective", "计算题": "subjective",
    "编程": "subjective", "编程题": "subjective",
}


def question_type(value):
    """Map common user-facing section names to the bank's four coarse types."""
    key = str(value or "").strip().lower().replace("-", "_")
    return _TYPE_ALIASES.get(key, key)


def confirmed_type_points(bp):
    """Verified exam marks per type, or empty if the structure is uncertain."""
    structure = (bp or {}).get("structure") or {}
    if structure.get("confirmed") is not True or not structure.get("source"):
        return {}
    points = {}
    for section in structure.get("sections") or []:
        try:
            marks = float(section.get("points"))
        except (TypeError, ValueError):
            continue
        kind = question_type(section.get("type"))
        if not kind or not (0 < marks < float("inf")):
            continue
        points[kind] = points.get(kind, 0) + marks
    return points


def confirmed_kc_points(bp):
    """Explicit confirmed knowledge-point marks, never inferred from question counts."""
    out = {}
    for kc in (bp or {}).get("kcs") or []:
        if kc.get("weight_confirmed") is True and kc.get("weight_source"):
            try:
                points = float(kc.get("exam_points"))
            except (TypeError, ValueError):
                continue
            if 0 < points < float("inf"):
                out[kc["id"]] = points
    return out


def _scope_chapters(state, bp, exam):
    """Restrict only when a confirmed scope item resolves unambiguously."""
    chapters = {c["n"]: c for c in state.get("chapters", [])}
    allowed, unresolved = set(), False
    confirmed_items = [s.get("item", "") for s in (exam or {}).get("scope", [])
                       if isinstance(s, dict) and s.get("confirmed") is True]
    for item in confirmed_items:
        name = str(item).strip()
        span = re.fullmatch(r"(?:ch(?:apter)?\s*|第\s*)?(\d+)\s*[-~至—]\s*(\d+)\s*(?:章)?", name, re.I)
        if span and int(span.group(1)) <= int(span.group(2)):
            covered = set(range(int(span.group(1)), int(span.group(2)) + 1))
            if covered.issubset(chapters):
                allowed.update(covered)
                continue
        match = re.fullmatch(r"(?:ch(?:apter)?\s*|第\s*)?(\d+)\s*(?:章)?", name, re.I)
        if match and int(match.group(1)) in chapters:
            allowed.add(int(match.group(1)))
            continue
        matches = {n for n, c in chapters.items() if str(c.get("title", "")).strip() == name}
        matches.update(kc.get("chapter") for kc in (bp or {}).get("kcs") or []
                       if kc.get("title", "").strip() == name and kc.get("chapter") in chapters)
        if not matches:
            unresolved = True
        else:
            allowed.update(matches)
    # A mixed resolved/unresolved specification must never silently drop scope.
    return allowed if confirmed_items and allowed and not unresolved else None


def eligible_questions(state, bank, bp=None, exam=None):
    """Use verified chapter scope and known question types when safely resolvable."""
    chapters = _scope_chapters(state, bp, exam)
    questions = [q for q in bank if chapters is None or q.get("chapter") in chapters]
    type_points = confirmed_type_points(bp)
    types = set(type_points) if type_points else {
        question_type(t) for t in (exam or {}).get("question_types") or []}
    if types:
        filtered = [q for q in questions if question_type(q.get("type")) in types]
        if filtered or type_points:
            questions = filtered
    return questions


def _verified_difficulty(q, bp=None):
    """Only explicit sourced difficulty participates in choosing representative items."""
    supplied = ((bp or {}).get("question_meta") or {}).get(q.get("id")) or {}
    meta = supplied if supplied.get("difficulty_confirmed") is True else q
    if meta.get("difficulty_confirmed") is not True or not meta.get("difficulty_source"):
        return None
    value = meta.get("difficulty")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 5:
        return int(value)
    return {"easy": 1, "basic": 1, "基础": 1, "medium": 3, "中等": 3,
            "hard": 5, "advanced": 5, "困难": 5}.get(str(value).lower())


def stratified_pick(state, bank, n, bp=None, exam=None):
    """One diverse diagnosis sample: scope, verified marks, type, KC, difficulty.

    Prefer untouched KC/type combinations and never-attempted questions. When
    marks/difficulty are unavailable, cover areas evenly and report unknown
    separately; do not substitute the number of bank questions for exam marks.
    """
    if n <= 0:
        return []
    pool = eligible_questions(state, bank, bp, exam)
    q_map = (bp or {}).get("q_map") or {}
    type_points = confirmed_type_points(bp)
    kc_points = confirmed_kc_points(bp)
    history = {h["qid"] for h in state.get("history", [])}
    used = {h["qid"] for h in state.get("history", [])
            if h.get("result") in ("right", "wrong", "skip")}
    picked, seen_topics, seen_types, seen_chapters, seen_difficulties = [], set(), set(), set(), set()
    while pool and len(picked) < n:
        def rank(q):
            kind = question_type(q.get("type"))
            kids = set(q_map.get(q["id"], []))
            topic_key = kids or {"ch%s" % q.get("chapter")}
            difficulty = _verified_difficulty(q, bp)
            diff_band = ("basic" if difficulty <= 2 else "advanced" if difficulty >= 4 else "medium") if difficulty else None
            known_marks = max([type_points.get(kind, 0)] + [kc_points.get(k, 0) for k in kids])
            return (
                0 if q["id"] not in used else 1,
                0 if topic_key - seen_topics else 1,
                0 if kind not in seen_types else 1,
                0 if q.get("chapter") not in seen_chapters else 1,
                0 if diff_band and diff_band not in seen_difficulties else 1,
                -known_marks,
                0 if q["id"] not in history else 1,
                str(q["id"]),
            )
        q = min(pool, key=rank)
        picked.append(q)
        pool.remove(q)
        seen_topics.update(q_map.get(q["id"]) or ["ch%s" % q.get("chapter")])
        seen_types.add(question_type(q.get("type")))
        seen_chapters.add(q.get("chapter"))
        difficulty = _verified_difficulty(q, bp)
        if difficulty:
            seen_difficulties.add("basic" if difficulty <= 2 else "advanced" if difficulty >= 4 else "medium")
    return picked


# ------------------------------------------------------------------ ability stats

def _chapter_titles(state):
    return {c["n"]: c["title"] for c in state.get("chapters", [])}


def _latest_attempts(state):
    """Last actual result wins; historical best is a separate evidence field."""
    return {h["qid"]: h for h in state.get("history", []) if h.get("qid") and
            h.get("result") in ("right", "wrong", "skip")}


def _row(kc_id, chapter, title, qids, state, bank_by_id, latest=None):
    qids = list(dict.fromkeys(qids))
    latest = latest if latest is not None else _latest_attempts(state)
    tested = indep = hinted = wrong = 0
    by_type = {}
    history = state.get("history", [])
    row_qids = set(qids)
    recent = next((h for h in reversed(history) if h.get("qid") in row_qids and
                   h.get("result") in ("right", "wrong", "skip")), None)
    best = "untested"
    strongest_recent = "untested"
    for qid in qids:
        best = max_level(best, st.get_evidence_level(state, qid))
        item = latest.get(qid)
        kind = question_type((bank_by_id.get(qid) or {}).get("type")) or "unknown"
        cell = by_type.setdefault(kind, {"total": 0, "tested": 0,
                                         "indep_right": 0, "hinted": 0,
                                         "wrong": 0, "untested": 0,
                                         "recent_status": "untested"})
        cell["total"] += 1
        if item is None:
            cell["untested"] += 1
            continue
        tested += 1
        cell["tested"] += 1
        evidence = item.get("evidence_level") or "untested"
        independent = item.get("result") == "right" and (
            item.get("is_independent") is True or evidence in _INDEP_LEVELS)
        if independent:
            indep += 1
            cell["indep_right"] += 1
            strongest_recent = max_level(strongest_recent, evidence if evidence in _INDEP_LEVELS else "immediate")
        elif item.get("result") == "right":
            hinted += 1
            cell["hinted"] += 1
        else:
            wrong += 1
            cell["wrong"] += 1
    for kind, cell in by_type.items():
        cell_qids = {qid for qid in qids if question_type((bank_by_id.get(qid) or {}).get("type")) == kind}
        cell_recent = next((h for h in reversed(history) if h.get("qid") in cell_qids and
                            h.get("result") in ("right", "wrong", "skip")), None)
        cell["recent_status"] = cell_recent.get("result") if cell_recent else "untested"
    summary = ev.summarize(qids, latest)
    for kind, cell in by_type.items():
        ids = {qid for qid in qids if question_type((bank_by_id.get(qid) or {}).get('type')) == kind}
        counts = ev.summarize(ids, latest)
        cell.update(status=counts['status'], indep_right=counts['independent'], wrong=counts['wrong'],
                    method_pending=counts['method_pending'])
    return {
        'kc_id': kc_id, 'chapter': chapter, 'title': title,
        'total': summary['total'], 'tested': summary['n'], 'indep_right': summary['independent'],
        'hinted': summary['hinted'], 'wrong': summary['wrong'], 'untested': summary['untested'],
        'strength': summary['strength'], 'status': summary['status'], 'best_evidence': best,
        'recent_status': recent.get('result') if recent else 'untested', 'by_type': by_type, 'qids': qids,
        'method_pending': summary['method_pending'], 'retention': summary['retention'],
        'variation': summary['variation'], 'transfer_kinds': summary['transfer_kinds'],
        'unseen_independent': summary['unseen_independent'],
    }


def max_level(a, b):
    levels = ["untested", "hinted", "immediate", "delayed", "transfer"]
    try:
        return a if levels.index(a) >= levels.index(b) else b
    except (ValueError, IndexError):
        return b


def kc_stats(state, bank, bp, chapter=None):
    """Per-KC ability rows. Without a KC dictionary, per-chapter rows instead.

    Returns (rows, mode) where mode is "kc" or "chapter".
    """
    bank_by_id = {q["id"]: q for q in bank}
    titles = _chapter_titles(state)
    latest = _latest_attempts(state)
    kcs = (bp or {}).get("kcs") or []
    rows = []
    if kcs:
        q_map = bp.get("q_map") or {}
        by_kc = {}
        for q in bank:
            for kid in q_map.get(q["id"], []):
                by_kc.setdefault(kid, []).append(q["id"])
        # KC rows (only KCs that actually have questions are useful; keep
        # zero-question KCs visible too so the tutor sees the whole dictionary)
        for kc in kcs:
            if chapter is not None and kc.get("chapter") != chapter:
                continue
            rows.append(_row(kc["id"], kc.get("chapter"), kc["title"],
                             by_kc.get(kc["id"], []), state, bank_by_id, latest))
        # unmapped questions, aggregated per chapter (transparency)
        unmapped_by_ch = {}
        for q in bank:
            if q["id"] not in q_map and (chapter is None or q["chapter"] == chapter):
                unmapped_by_ch.setdefault(q["chapter"], []).append(q["id"])
        for ch in sorted(unmapped_by_ch, key=lambda c: (c is None, c)):
            qids = unmapped_by_ch[ch]
            r = _row("ch%s-unmapped" % ch, ch,
                     "其他（未映射到 KC）", qids, state, bank_by_id, latest)
            r["kc_id"] = "ch%s-unmapped" % ch
            rows.append(r)
        rows.sort(key=lambda r: (r["chapter"] is None, r["chapter"] or 0, r["kc_id"]))
        return rows, "kc"
    # chapter fallback
    by_ch = {}
    for q in bank:
        if chapter is None or q["chapter"] == chapter:
            by_ch.setdefault(q["chapter"], []).append(q["id"])
    for ch in sorted(by_ch, key=lambda c: (c is None, c)):
        rows.append(_row("ch%s" % ch, ch, titles.get(ch, ""), by_ch[ch], state, bank_by_id, latest))
    return rows, "chapter"


def strength_label(strength, zh=True):
    return STRENGTH_LABELS.get(strength, (strength, strength))[0 if zh else 1]


def weak_spots(state, bank, bp, k=3):
    """Top weak chapters for the plan's priority hint.

    Returns (lines, n_attempted_questions). Chapters with ≥2 attempts and the
    lowest independent-correct rate come first; then large never-attempted
    chapters. Every line carries its evidence base.
    """
    # Aggregate distinct question IDs directly: one question may map to
    # several KCs and must not inflate the chapter evidence denominator.
    latest = _latest_attempts(state)
    by_ch = {}
    for q in bank:
        ch = q.get("chapter")
        if ch is None:
            continue
        agg = by_ch.setdefault(ch, {"tested": 0, "indep": 0, "wrong": 0, "untested": 0})
        attempt = latest.get(q["id"])
        if not attempt:
            agg["untested"] += 1
            continue
        agg["tested"] += 1
        if ev.observation(attempt) in ("immediate", "retention", "variation"):
            agg["indep"] += 1
        elif ev.observation(attempt) in ("gap", "method_pending"):
            agg["wrong"] += 1
    titles = _chapter_titles(state)
    # honest sample size: distinct questions ever attempted, not KC-row sums
    n_attempted = len(latest)
    ranked = []
    for ch, a in by_ch.items():
        if a["tested"] and a["indep"] < a["tested"]:
            rate = a["indep"] / float(a["tested"])
            ranked.append((0, rate, ch, a))
        elif a["tested"] == 0 and a["untested"] >= 5:
            ranked.append((1, -a["untested"], ch, a))
    ranked.sort(key=lambda x: (x[0], x[1], x[2]))
    lines = []
    for kind, _, ch, a in ranked[:k]:
        label = "ch%s %s" % (ch, titles.get(ch, ""))
        if kind == 0:
            lines.append({"kind": "weak", "chapter": ch, "label": label,
                          "detail": "独立对 %d/%d" % (a["indep"], a["tested"])})
        else:
            lines.append({"kind": "untested", "chapter": ch, "label": label,
                          "detail": "未测 %d 题" % a["untested"]})
    return lines, n_attempted


# ------------------------------------------------------------------ structure rendering

def structure_line(structure, zh=True):
    """Render the exam structure as one compact line, or 'unknown'."""
    if not structure or not structure.get("sections"):
        return None
    parts = []
    for s in structure.get("sections", []):
        parts.append("%s %s×%s分" % (s.get("type", "?"), s.get("count", "?"), s.get("points", "?")))
    src = structure.get("source") or ""
    confirmed = structure.get("confirmed")
    suffix = ""
    if confirmed is False:
        suffix = "（未确认）" if zh else " (unconfirmed)"
    line = " · ".join(parts) + suffix
    if src:
        line += "  来源: %s" % src
    return line
