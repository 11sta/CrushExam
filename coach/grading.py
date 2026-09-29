# -*- coding: utf-8 -*-
"""Answer normalization and grading for objective questions.

Answers in the quiz bank keep their raw first line ("A", "ABC", "正确", "错误"),
followed by an explanation line.  Grading here is based on the *shape of the
reference answer's first line*, not the question's `type` field: true/false
items extracted from Chinese papers are often typed `subjective` because the
stem lacks a "判断" marker, while their answer line is exactly "正确"/"错误".

Rules (mirrors SKILL.md §5 判分适配):
- true/false: map 对/√/T/true/是/正确/1 → True, 错/×/F/false/否/错误/0 → False.
  An unmappable answer (e.g. "C") is NOT graded — ask the student to restate.
- single choice: exactly one letter A-H after stripping punctuation ("A." "a" "选A").
- multi choice: letter set comparison; subset without wrong picks = partial.
- anything else: cannot auto-grade (subjective) — the tutor grades it.
"""
import re

TRUE_TOKENS = {"对", "正确", "√", "T", "TRUE", "是", "YES", "Y", "1"}
FALSE_TOKENS = {"错", "错误", "×", "X", "F", "FALSE", "否", "NO", "N", "0"}
_LETTER_RE = re.compile(r"[A-Ha-h]")


def answer_first_line(answer):
    """Reference answers keep 'A\\n解析：…'; grading uses only the first line."""
    if not answer:
        return ""
    return answer.split("\n", 1)[0].strip()


def _norm_token(text):
    return "".join(text.split()).upper().replace("，", ",").rstrip("。.")


def parse_true_false(text):
    """Return True/False for a true/false answer, else None (cannot map)."""
    t = _norm_token(text).rstrip("。，,.")
    if t in TRUE_TOKENS:
        return True
    if t in FALSE_TOKENS:
        return False
    # tolerate prefixes like "答案：对" or "答:对"
    t2 = re.sub(r"^(答案|答|ANSWER)[:：]?", "", t).strip()
    if t2 in TRUE_TOKENS:
        return True
    if t2 in FALSE_TOKENS:
        return False
    return None


def parse_letters(text, expect=None):
    """Extract the set of choice letters from free-form input.

    "A" / "a." / "选A" -> {A};  "ABD" / "A、B、D" / "全选ABD" -> {A,B,D}
    Returns (letters, error) where error explains why nothing could be parsed.
    """
    t = _norm_token(text)
    t = re.sub(r"^(?:答案|答|全选|选|ANSWER)[:：]?", "", t).strip()
    # Optional reasoning after a clear punctuation separator does not change
    # the option token; arbitrary English words are never mined for letters.
    match = re.fullmatch(r"[A-H](?:[A-H、,，/;；\s]*[A-H])?[.。]?", t, re.I)
    if not match:
        return None, "no_letters"
    letters = set(ch.upper() for ch in _LETTER_RE.findall(t))
    # "全选" with no letters following: not resolvable here
    if not letters:
        return None, "no_letters"
    if expect is not None and letters != expect:
        # single-choice expects exactly one letter
        if len(letters) > 1:
            return None, "multiple_letters"
    return letters, None


def ref_shape(first_line):
    """Classify the reference answer's first line into a grading shape."""
    fl = _norm_token(answer_first_line(first_line)).rstrip("。，,.")
    fl = re.sub(r"^(答案|答)[:：]?", "", fl).strip()
    if not fl:
        return "none"
    if parse_true_false(fl) is not None:
        return "true_false"
    letters = [ch.upper() for ch in _LETTER_RE.findall(fl)]
    if letters and len(fl.replace("、", "").replace(",", "").replace(" ", "")) == len(letters):
        return "multi" if len(letters) >= 2 else "single"
    return "subjective"


def grade(student_answer, ref_answer):
    """Grade a student answer against the reference.

    Returns a dict:
      {kind, verdict, student, reference, detail}
    kind: true_false | single | multi | subjective | none
    verdict: right | wrong | partial | restate | manual
      - restate: objective question but the student's answer cannot be mapped
        (e.g. "C" on a true/false item) — ask them to restate, never record.
      - manual: no reference answer / subjective — the tutor grades it.
    """
    first = answer_first_line(ref_answer)
    shape = ref_shape(first)
    if shape == "none":
        return {"kind": "none", "verdict": "manual", "student": student_answer,
                "reference": "", "detail": "no reference answer"}
    if shape == "true_false":
        ref = parse_true_false(first)
        stu = parse_true_false(student_answer)
        if stu is None:
            return {"kind": "true_false", "verdict": "restate", "student": student_answer,
                    "reference": first, "detail": "tf_unmappable"}
        ok = (stu == ref)
        return {"kind": "true_false", "verdict": "right" if ok else "wrong",
                "student": "对" if stu else "错", "reference": "对" if ref else "错",
                "detail": ""}
    if shape == "single":
        ref_letters, _ = parse_letters(first)
        ref = sorted(ref_letters or [])
        stu_letters, err = parse_letters(student_answer, expect=set(ref))
        if err == "multiple_letters":
            return {"kind": "single", "verdict": "restate", "student": student_answer,
                    "reference": ref[0], "detail": "single_got_multiple"}
        if err:
            return {"kind": "single", "verdict": "restate", "student": student_answer,
                    "reference": ref[0], "detail": "no_letters"}
        stu = sorted(stu_letters)
        ok = (stu == ref)
        return {"kind": "single", "verdict": "right" if ok else "wrong",
                "student": "".join(stu), "reference": "".join(ref), "detail": ""}
    if shape == "multi":
        ref_letters, _ = parse_letters(first)
        ref = set(ref_letters or [])
        stu_letters, err = parse_letters(student_answer)
        if err:
            return {"kind": "multi", "verdict": "restate", "student": student_answer,
                    "reference": "".join(sorted(ref)), "detail": "no_letters"}
        stu = set(stu_letters)
        if stu == ref:
            return {"kind": "multi", "verdict": "right",
                    "student": "".join(sorted(stu)), "reference": "".join(sorted(ref)), "detail": ""}
        if stu < ref:  # subset: missing some, no wrong picks
            missing = "".join(sorted(ref - stu))
            return {"kind": "multi", "verdict": "partial",
                    "student": "".join(sorted(stu)), "reference": "".join(sorted(ref)),
                    "detail": "missing:%s" % missing}
        wrong = "".join(sorted(stu - ref))
        return {"kind": "multi", "verdict": "wrong",
                "student": "".join(sorted(stu)), "reference": "".join(sorted(ref)),
                "detail": "wrong_pick:%s" % wrong}
    return {"kind": "subjective", "verdict": "manual", "student": student_answer,
            "reference": first, "detail": "subjective"}
