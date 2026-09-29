# -*- coding: utf-8 -*-
"""Offline, evidence-labelled knowledge-module × question-type capability view.

Build only from the existing blueprint, question bank and recorded attempts.
Cells are descriptive observations, never ability scores or exam probabilities.
"""
from collections import defaultdict
import html
import os

from . import blueprint as bpmod, evidence


_TYPE_ZH = {"choice": "选择", "true_false": "判断", "fill_blank": "填空",
            "subjective": "主观", "unknown": "其他"}
_TYPE_EN = {"choice": "Choice", "true_false": "True/false",
            "fill_blank": "Fill in", "subjective": "Written", "unknown": "Other"}
_KIND_ZH = {"exam": "试卷", "homework": "作业", "solution": "答案",
            "lecture": "课件", "notes": "笔记"}
_KIND_EN = {"exam": "Exam", "homework": "Homework", "solution": "Solutions",
            "lecture": "Slides", "notes": "Notes"}
_T = {
    "title": ("能力视图", "Capability view"),
    "intro": ("依据题库与作答记录；仅展示证据，不预测成绩或及格概率。",
              "Based on the question bank and attempts; no score or pass probability is predicted."),
    "tested": ("已测", "Tested"), "bank": ("题库", "Bank"),
    "mapped": ("题已标注知识点", "questions mapped to modules"),
    "priorities": ("下一步优先看", "Next priorities"),
    "none": ("当前没有足够的作答证据判定薄弱点；先按考试范围选代表题摸底。",
             "Insufficient attempts to identify a weak area; start with representative items."),
    "matrix": ("知识模块 × 题型", "Knowledge modules × question types"),
    "chapter": ("章节", "Chapter"), "module": ("知识模块", "Knowledge module"),
    "legend": ("图例与读法", "Legend and interpretation"),
    "gray": ("未测 / 灰色：没有有效作答，不代表零分。",
             "Untested / gray: no recorded attempt; not a zero score."),
    "red": ("待补 / 红色：同类题最近有答错或跳过。",
            "Needs work / red: a recent wrong or skipped item in this type."),
    "amber": ("待复测 / 黄色：最近一次答对依赖提示，或只有即时证据。",
              "Retest / amber: hinted answer or only immediate evidence."),
    "green": ("时间/异题证据 / 绿色：同题隔日不等于新题能力；参数、表示和情境变化分别记录，仅限已测题。",
              "Delayed evidence / green: independently correct on a later day; sample still limited."),
    "count_rule": ("N 是该模块同类题有记录的不同题目数；独立对统计各题最近一次有效作答。",
                   "N counts distinct attempted questions; independent correct uses each question's latest valid attempt."),
    "auto_rule": ("知识点标签可能由关键词自动匹配，需核对明显误标；有多个知识点的题会出现在多个模块。",
                  "Topic labels can be keyword matches; check obvious errors. One question may appear under several modules."),
    "fallback": ("尚无知识点词典，暂按章节展示；不能据此断言具体知识缺口。",
                 "No module dictionary: grouped by chapter; specific topic gaps cannot yet be inferred."),
    "six": ("六模块概览", "Six-module overview"),
    "six_note": ("仅汇总状态，不是六项等分的能力分数。",
                 "Summary of observed states, not six numerical ability scores."),
    "sources": ("题目出处表", "Question sources"),
    "file": ("资料文件", "Source file"),
    "kind": ("识别类别", "Detected type"),
    "questions": ("题数", "Questions"),
    "use": ("用途", "Use"),
    "source_use": ("核对题面、参考答案与知识点标签；文件名不能证明考试权重。",
                   "Verify questions, solutions and topic labels; filenames do not prove exam weights."),
    "structure": ("考试结构（按原资料记录）", "Exam structure (as supplied)"),
    "section": ("题型", "Type"), "points": ("分值记录", "Points as recorded"),
    "provenance": ("来源", "Source"),
    "confirmed": ("已确认", "Confirmed"),
    "unconfirmed": ("未确认，不能作为权重", "Unconfirmed; do not use as weight"),
    "latest_wrong": ("最近答错", "Latest wrong"),
    "latest_skip": ("最近跳过", "Latest skipped"),
    "latest_independent": ("最近独立对", "Latest independent correct"),
    "latest_hinted": ("最近提示后对", "Latest correct with hint"),
    "wrong_count": ("错/跳", "Wrong/skipped"),
    "untested": ("未测", "Untested"),
    "no_questions": ("尚无对应题目", "No matching bank questions"),
    "priority_gap": ("有题最近错/跳，先补步骤，再做一题独立验证", "Wrong/skipped question: fix the step, then verify independently"),
    "priority_assist": ("仍有提示后答对，安排独立复测", "Still has hinted successes; try independently"),
    "priority_untested": ("题库尚有未测题；先抽代表题确认", "Untested bank items; sample representative questions"),
    "kc_marks": ("已确认知识点分值", "Confirmed topic marks"),
    "type_marks": ("所涉题型总分（非模块分值）", "Total marks for this question type (not module marks)"),
}


def _t(key, zh):
    return _T[key][0 if zh else 1]


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _qtype(q):
    val = bpmod.question_type(q.get("type") or "unknown")
    return val if val in _TYPE_ZH else "unknown"


def _latest_by_q(state, known_ids):
    """Latest valid completed record for each current-bank question."""
    out = {}
    for h in state.get("history", []):
        if h.get("qid") in known_ids and h.get("result") in ("right", "wrong", "skip"):
            out[h["qid"]] = h
    return out


def _kind(h):
    return evidence.observation(h)


def _cell(qids, latest, zh):
    out = evidence.summarize(qids, latest)
    records = [(q, latest[q]) for q in qids if q in latest]
    if records:
        recent = max(records, key=lambda pair: latest._position[pair[0]]) if isinstance(latest, _Latest) else records[-1]
        h = recent[1]
        out['last'] = _t('latest_wrong' if h['result'] == 'wrong' else
                         'latest_skip' if h['result'] == 'skip' else
                         'latest_independent' if h.get('is_independent') else 'latest_hinted', zh)
    else:
        out['last'] = _t('untested', zh)
    return out


class _Latest(dict):
    """Latest-attempt dictionary with original append position for per-cell labels."""
    def __init__(self, state, known_ids):
        super().__init__()
        self._position = {}
        for pos, h in enumerate(state.get("history", [])):
            if h.get("qid") in known_ids and h.get("result") in ("right", "wrong", "skip"):
                self[h["qid"]] = h
                self._position[h["qid"]] = pos


def _build_rows(state, bank, rows, mode, zh):
    bank_by_id = {q["id"]: q for q in bank if q.get("id")}
    latest = _Latest(state, bank_by_id)
    kinds = [k for k in _TYPE_ZH if any(_qtype(q) == k for q in bank)]
    if not kinds:
        kinds = ["unknown"]
    labels = _TYPE_ZH if zh else _TYPE_EN
    data = []
    for r in rows:
        by_type = defaultdict(set)
        for qid in r.get("qids", []):
            if qid in bank_by_id:
                by_type[_qtype(bank_by_id[qid])].add(qid)
        cells = {k: _cell(by_type.get(k, set()), latest, zh) for k in kinds}
        all_qids = set().union(*by_type.values()) if by_type else set()
        joined = _cell(all_qids, latest, zh)
        data.append({"title": r.get("title") or r.get("kc_id") or "?",
                     "chapter": r.get("chapter"), "id": r.get("kc_id", ""),
                     "cells": cells, "summary": joined})
    return data, kinds, labels


def _priority(data, bp, zh):
    items = []
    topic_points = bpmod.confirmed_kc_points(bp)
    type_points = bpmod.confirmed_type_points(bp)
    for row in data:
        s = row["summary"]
        if not s["total"]:
            continue
        if s["wrong"] or s["method_pending"]:
            rank, reason = 0, "priority_gap"
        elif s["hinted"]:
            rank, reason = 1, "priority_assist"
        elif s["untested"]:
            rank, reason = 2, "priority_untested"
        else:
            continue
        # Exam marks affect order only when confirmed with a source. A section's
        # total marks describe the type, not the marks for this particular KC.
        marks = []
        if row["id"] in topic_points:
            marks.append((topic_points[row["id"]], "kc_marks"))
        for kind, cell in row["cells"].items():
            if cell["total"] and kind in type_points:
                marks.append((type_points[kind], "type_marks"))
        mark, mark_kind = max(marks, default=(0, None), key=lambda x: x[0])
        extra = ("；%s %g" % (_t(mark_kind, zh), mark)) if mark_kind else ""
        items.append((rank, -mark, -s["wrong"], -s["untested"], row["title"],
                      row, _t(reason, zh) + extra))
    items.sort(key=lambda x: x[:5])
    return [(x[5], x[6]) for x in items[:3]]


def write_html(path, state, bank, bp, rows=None, mode=None):
    """Write a self-contained static HTML capability view and return its path.

    ``rows`` / ``mode`` optionally accept ``blueprint.kc_stats``' existing
    output so the CLI need not recompute the view. No external assets or JS.
    """
    if rows is None or mode is None:
        rows, mode = bpmod.kc_stats(state, bank, bp)
    zh = state.get("language", "zh") != "en"
    data, kinds, labels = _build_rows(state, bank, rows, mode, zh)
    all_ids = {q.get("id") for q in bank if q.get("id")}
    n_attempted = len(_latest_by_q(state, all_ids))
    mapping = (bp or {}).get("q_map") or {}
    n_mapped = sum(q.get("id") in mapping for q in bank)
    heading = _e(_t("title", zh))
    title = _e(state.get("course") or state.get("exam_id") or "CrushExam")
    bits = ["<!doctype html><html lang='%s'><head><meta charset='utf-8'>" % ("zh-CN" if zh else "en"),
            "<meta name='viewport' content='width=device-width,initial-scale=1'>",
            "<title>%s · %s</title>" % (heading, title),
            "<style>body{font:15px/1.55 system-ui,Arial,sans-serif;color:#222;background:#f5f6f8;margin:0}"
            "main{max-width:1120px;margin:0 auto;padding:24px 16px 48px}h1{margin:0 0 8px}h2{margin:0 0 10px;font-size:1.22rem}"
            ".meta{color:#555;margin:4px 0 16px}.card{background:#fff;border:1px solid #d9dde3;border-radius:10px;padding:18px;margin:14px 0}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px}.mini{padding:12px;border:1px solid #d9dde3;border-radius:8px}"
            ".scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:580px}caption{text-align:left;font-weight:600;margin-bottom:8px}"
            "th,td{border:1px solid #d9dde3;padding:8px 10px;text-align:left;vertical-align:top}th{background:#f1f3f6}"
            "td small, .hint{display:block;color:#505a65;font-size:.85em}.untested{background:#e8eaed}"
            ".gap{background:#fce8e6}.retest{background:#fff0c2}.delayed{background:#e4f4e9}"
            "ol{padding-left:1.4em}li{margin:.45em 0} .pill{display:inline-block;padding:2px 8px;border-radius:12px;border:1px solid #bec7d1}"
            "@media print{body{background:white}main{padding:0}.card{break-inside:avoid}}</style></head><body><main>",
            "<h1>%s</h1><p class='meta'>%s · %s</p>" % (heading, title, _e(_t("intro", zh))),
            "<section class='card'><strong>%s %d / %s %d</strong><span class='hint'>%d / %d %s</span></section>" % (
                _e(_t("tested", zh)), n_attempted, _e(_t("bank", zh)), len(bank),
                n_mapped, len(bank), _e(_t("mapped", zh)))]

    priorities = _priority(data, bp, zh)
    bits.append("<section class='card'><h2>%s</h2>" % _e(_t("priorities", zh)))
    if priorities:
        bits.append("<ol>")
        for row, why in priorities:
            s = row["summary"]
            bits.append("<li><strong>%s</strong> · %s · N=%d/%d</li>" % (
                _e(row["title"]), _e(why), s["n"], s["total"]))
        bits.append("</ol>")
    else:
        bits.append("<p>%s</p>" % _e(_t("none", zh)))
    bits.append("</section>")

    modules = [r for r in data if not str(r["id"]).endswith("unmapped")]
    if mode == "kc" and len(modules) == 6:
        bits.append("<section class='card'><h2>%s</h2><p class='meta'>%s</p><div class='grid'>" % (
            _e(_t("six", zh)), _e(_t("six_note", zh))))
        for r in modules:
            s = r["summary"]
            status = s["status"] if s["total"] else "untested"
            bits.append("<div class='mini %s'><strong>%s</strong><small>N=%d/%d · %s</small></div>" % (
                status, _e(r["title"]), s["n"], s["total"], _e(s["last"])))
        bits.append("</div></section>")

    bits.append("<section class='card'><h2>%s</h2>" % _e(_t("matrix", zh)))
    if mode != "kc":
        bits.append("<p class='meta'>%s</p>" % _e(_t("fallback", zh)))
    bits.append("<div class='scroll'><table><thead><tr><th scope='col'>%s</th>" % _e(_t("module" if mode == "kc" else "chapter", zh)))
    for kind in kinds:
        bits.append("<th scope='col'>%s</th>" % _e(labels[kind]))
    bits.append("</tr></thead><tbody>")
    for row in data:
        title_cell = row["title"] + " · " + bpmod.strength_label(row["summary"]["strength"], zh)
        if row["chapter"] is not None:
            title_cell = ("%s %s · " % (_t("chapter", zh), row["chapter"])) + title_cell
        bits.append("<tr><th scope='row'>%s</th>" % _e(title_cell))
        for kind in kinds:
            c = row["cells"][kind]
            if not c["total"]:
                bits.append("<td class='untested'>%s</td>" % _e(_t("no_questions", zh)))
                continue
            bits.append("<td class='%s'><strong>%s</strong><small>N=%d/%d · %s %d · %s %d · %s</small></td>" % (
                c["status"], _e(bpmod.strength_label(c["strength"], zh) + " · " + c["last"]), c["n"], c["total"],
                _e(_t("latest_independent", zh)), c["independent"],
                _e(_t("wrong_count", zh)), c["wrong"],
                _e("未测 %d" % c["untested"] if zh else "%d untested" % c["untested"])))
        bits.append("</tr>")
    bits.append("</tbody></table></div></section>")
    bits.append("<section class='card'><h2>%s</h2><ul>" % _e(_t("legend", zh)))
    for key in ("gray", "red", "amber", "green", "count_rule", "auto_rule"):
        bits.append("<li>%s</li>" % _e(_t(key, zh)))
    bits.append("</ul></section>")

    struct = (bp or {}).get("structure")
    if struct and struct.get("sections"):
        bits.append("<section class='card'><h2>%s</h2><p>%s: %s · %s</p>" % (
            _e(_t("structure", zh)), _e(_t("provenance", zh)),
            _e(struct.get("source") or "?"),
            _e(_t("confirmed" if struct.get("confirmed") is True and struct.get("source")
                  else "unconfirmed", zh))))
        bits.append("<div class='scroll'><table><thead><tr><th>%s</th><th>%s</th><th>%s</th></tr></thead><tbody>" % (
            _e(_t("section", zh)), _e(_t("questions", zh)), _e(_t("points", zh))))
        for item in struct["sections"]:
            if not isinstance(item, dict):
                continue
            bits.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                _e(item.get("type") or "?"), _e(item.get("count") or "?"), _e(item.get("points") or "?")))
        bits.append("</tbody></table></div></section>")

    files = defaultdict(lambda: {"n": 0, "kinds": set()})
    for q in bank:
        source = q.get("source") or {}
        fname = str(source.get("file") or "?")
        files[fname]["n"] += 1
        files[fname]["kinds"].add(str(source.get("kind") or "unknown"))
    bits.append("<section class='card'><h2>%s</h2><p class='meta'>%s</p>" % (
        _e(_t("sources", zh)), _e(_t("source_use", zh))))
    bits.append("<div class='scroll'><table><thead><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead><tbody>" % (
        _e(_t("file", zh)), _e(_t("kind", zh)), _e(_t("questions", zh)), _e(_t("use", zh))))
    kind_labels = _KIND_ZH if zh else _KIND_EN
    for fname, info in sorted(files.items()):
        kind_txt = ", ".join(kind_labels.get(k, k) for k in sorted(info["kinds"]))
        bits.append("<tr><td>%s</td><td>%s</td><td>%d</td><td>%s</td></tr>" % (
            _e(fname), _e(kind_txt), info["n"], _e(_t("source_use", zh))))
    if not files:
        bits.append("<tr><td colspan='4'>%s</td></tr>" % _e(_t("no_questions", zh)))
    bits.append("</tbody></table></div></section></main></body></html>")
    target = os.path.abspath(os.fspath(path))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("".join(bits))
    return target
