# -*- coding: utf-8 -*-
"""Usage attribution: where did the session's tool calls / credits go?

An agent host may provide a per-session call counter in
`.tool-usage-log.json`; the host's billing rules may involve other factors:

    {"sessions": {
        "ses_xxx": {"totalCalls": N, "seenCallIds": [...],
                    "updatedAt": "...", "endedAt": "..."}
    }}

This module turns that log into a call-count report: total calls, calls per
day, the heaviest sessions, and (optionally) a count of local OCR render files.
Rendering an image is a local operation. A rendered image may be never sent to
a vision model, or sent many times; the count is NOT a vision-call estimate.

Honesty rules (aligned with SKILL.md §6/§13 and the OCR cost guard):
  - tool-call counts are NOT credits/money; the host's own billing rules decide
  - the log stores counts only, no tool names: vision calls cannot be inferred
    from the log or from local rendered image files (--ocr-dir)
  - empty sessions (0 calls) are counted separately, never hidden
"""
import datetime as _dt
import glob
import json
import os

LOG_FILENAME = ".tool-usage-log.json"

# Auto-detection roots; overridable (tests point this at nothing).
SEARCH_ROOTS = (os.path.join(os.path.expanduser("~"), ".config", "TeleAgent"),
                os.path.join(os.path.expanduser("~"), ".local", "share", "TeleAgent"))


# ------------------------------------------------------------------ load

def find_log(explicit=None):
    """Locate .tool-usage-log.json: explicit path first, then SEARCH_ROOTS.

    An explicit path that does not exist returns None (never silently falls
    through to auto-detection — the caller asked for a specific file).
    """
    if explicit:
        return os.path.abspath(explicit) if os.path.exists(explicit) else None
    for base in SEARCH_ROOTS:
        if not os.path.isdir(base):
            continue
        for hit in glob.glob(os.path.join(base, "**", LOG_FILENAME), recursive=True):
            if os.path.isfile(hit):
                return os.path.abspath(hit)
    return None


def load_log(path):
    """Parse the log into a list of session dicts with a day key. Never raises
    on a malformed file: returns None so the caller can report the issue."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    sessions = (data or {}).get("sessions") or {}
    out = []
    for sid, rec in sessions.items():
        if not isinstance(rec, dict):
            continue
        total = rec.get("totalCalls") or 0
        ts = rec.get("updatedAt") or rec.get("endedAt") or ""
        day = ts[:10] if ts else ""
        out.append({
            "session_id": sid,
            "total_calls": int(total),
            "seen": len(rec.get("seenCallIds") or []),
            "day": day,
        })
    out.sort(key=lambda r: (r["day"], r["session_id"]))
    return out


# ------------------------------------------------------------------ aggregate

def summarize(sessions, days=None):
    """Aggregate session rows into a report dict.

    days: keep only sessions whose day is within the last N days (None = all).
    """
    today = _dt.date.today().isoformat()
    if days:
        try:
            cutoff = (_dt.date.fromisoformat(today) - _dt.timedelta(days=days)).isoformat()
        except ValueError:
            cutoff = None
    else:
        cutoff = None
    kept = [s for s in sessions if not cutoff or (s["day"] and s["day"] >= cutoff)]
    total = sum(s["total_calls"] for s in kept)
    nonempty = [s for s in kept if s["total_calls"] > 0]
    by_day = {}
    for s in kept:
        d = s["day"] or "(unknown)"
        by_day.setdefault(d, {"sessions": 0, "calls": 0})
        by_day[d]["sessions"] += 1
        by_day[d]["calls"] += s["total_calls"]
    heaviest = sorted(nonempty, key=lambda s: -s["total_calls"])[:5]
    return {
        "window": "all" if cutoff is None else "%s..%s" % (cutoff, today),
        "sessions_total": len(kept),
        "sessions_nonempty": len(nonempty),
        "calls_total": total,
        "by_day": by_day,
        "heaviest": heaviest,
    }


# ------------------------------------------------------------------ OCR render files

def estimate_ocr(dirs):
    """Count distinct local image files, not vision calls or credits.

    Preserve the original ``(count, files)`` CLI contract. A cache may contain
    unused images, and the same image can be submitted more than once.
    """
    exts = (".png", ".jpg", ".jpeg", ".webp")
    files = set()
    for d in dirs or []:
        if not os.path.isdir(d):
            continue
        for root, _, names in os.walk(d):
            for n in names:
                if n.lower().endswith(exts):
                    files.add(os.path.realpath(os.path.join(root, n)))
    return len(files), sorted(files)
