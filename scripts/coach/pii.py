# -*- coding: utf-8 -*-
"""Best-effort masking of formatted personal data in extracted material text.

Mitigation only, not full de-identification: high-confidence patterns (phone,
18-digit ID card, email, labelled student/exam-ticket numbers) are masked
before text enters the workspace and any model context. Chinese names are NOT
auto-masked (a person name cannot be reliably told apart from problem-text
names like 小明); name fields are only counted so the host can warn the
student. Student answers and image content stay out of scope.
"""
import re

_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_ID18 = re.compile(r"(?<![0-9A-Za-z])(\d{6})\d{8}(\d{3}[0-9Xx])(?![0-9A-Za-z])")
_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*(@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_LABELED_ID = re.compile(
    r"(学号|考生号|准考证号|学籍号|student\s*id|admission\s*(?:ticket|card)\s*(?:no\.?|number)?)"
    r"(\s*[:：#]?\s*)(\d{5,14})", re.I)
_NAME_FIELD = re.compile(r"(?:^|[\s，,;；|])(?:姓名|name)\s*[:：]\s*\S", re.I | re.M)


def _mask_middle(s, head, tail):
    if len(s) <= head + tail:
        return "*" * len(s)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]


def mask_pii(text):
    """Return (masked_text, counts). counts maps kind -> hits, non-zero only.

    ``name_fields`` counts detected name labels; the name itself is kept.
    """
    counts = {}

    def bump(kind):
        counts[kind] = counts.get(kind, 0) + 1

    def sub_phone(m):
        bump("phone")
        return m.group(1) + "****" + m.group(2)

    def sub_id18(m):
        bump("id_card")
        return m.group(1) + "********" + m.group(2)

    def sub_email(m):
        bump("email")
        return m.group(1) + "***" + m.group(2)

    def sub_labeled(m):
        bump("student_id")
        return m.group(1) + m.group(2) + _mask_middle(m.group(3), 2, 2)

    text = _PHONE.sub(sub_phone, text or "")
    text = _ID18.sub(sub_id18, text)
    text = _EMAIL.sub(sub_email, text)
    text = _LABELED_ID.sub(sub_labeled, text)
    names = len(_NAME_FIELD.findall(text))
    if names:
        counts["name_fields"] = names
    return text, counts
