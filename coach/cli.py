# -*- coding: utf-8 -*-
"""Command line for CrushExam.

Every command prints short plain text that an agent can paste into its reply, and ends
with the command to run next, so even a small model never has to remember the CLI.
"""
import argparse
import datetime as _dt
import json
import os
import re
import sys
import time

from . import __version__, ability_view, blueprint as bpmod, chapters as chmod, evidence as evmod, exams as exammod, extract, figures as figmod, grading as grademod, index as idx, planner as planmod, questions as qmod, state as st, usage_log as usemod
from .text import is_mostly_cjk, pack, shorten
from . import attempts as at, workflow as wf, tasks as taskmod, material_safety as safety

CHAPTERS_FILE = "chapters.json"
BANK_FILE = "quiz_bank.json"
FIGURES_FILE = "figures.json"
POINTER = exammod.OLD_POINTER  # backward-compat pointer
DEFAULT_SLICE = {"zh": 3000, "en": 5000}

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        pass


# ------------------------------------------------------------------ wording

_T = {
    "no_ws": ("找不到学习工作区。先运行：python coach.py setup <材料文件夹>",
              "No study workspace found. Run: python coach.py setup <materials folder>"),
    "setup_done": ("✅ 工作区已建好", "✅ Workspace ready"),
    "files": ("文件", "Files"),
    "chapters": ("章节", "Chapters"),
    "questions": ("题目", "Questions"),
    "with_answers": ("有参考答案", "with reference answers"),
    "figures_count": ("配图", "Figures"),
    "scan_note": ("页扫描/手写页已跳过（不当作题面或答案）", "scanned/handwritten pages skipped (never used as question or answer text)"),
    "warnings": ("⚠️ 注意", "⚠️ Notes"),
    "pdf_missing": ("个 PDF 无法读取文本：请运行 `pip install pypdfium2` 后重新 setup",
                    "PDF file(s) could not be read: run `pip install pypdfium2` and setup again"),
    "no_pdfium": ("未安装 pypdfium2：PDF 里的图无法裁剪。运行 `pip install pypdfium2` 后重新 setup 即可自动配图",
                  "pypdfium2 is not installed: figures inside PDFs cannot be cropped. Run `pip install pypdfium2` and setup again"),
    "no_text": ("没有可提取文本（扫描件/纯图片）。讲这一章时请直接打开文件查看",
                "has no extractable text (scan/pure images). Open the file directly when teaching it"),
    "read_error": ("读取失败", "could not be read"),
    "next_steps": ("下一步", "Next"),
    "course": ("课程", "Course"),
    "exam_in": ("距考试", "Exam in"),
    "days": ("天", "day(s)"),
    "lang": ("语言", "Language"),
    "progress": ("进度", "Progress"),
    "current": ("当前", "Current"),
    "part": ("段", "part"),
    "mistakes": ("错题", "Mistakes"),
    "open": ("待复习", "open"),
    "confusions": ("疑难点", "Confusions"),
    "all_done": ("🎉 所有章节都讲完了。可以复习错题（python coach.py mistakes）或生成小抄（python coach.py cheatsheet）。",
                 "🎉 All chapters covered. Review mistakes (python coach.py mistakes) or build the cheat sheet (python coach.py cheatsheet)."),
    "ch_end": ("本章正文已讲完。", "End of this chapter's text."),
    "ch_examples": ("本章相关题目", "Questions for this chapter"),
    "no_examples": ("材料里没有这一章的题目；保留未测，可补充资料原题，不自动编题。",
                    "No source questions are available. Keep ability untested and request source exercises; do not invent them."),
    "answer_yes": ("有参考答案", "reference answer available"),
    "answer_no": ("无参考答案", "no reference answer"),
    "src": ("来源", "Source"),
    "figures": ("本章配图文件（请直接查看）", "Figure files for this chapter (open them directly)"),
    "slice_figs": ("🖼 本段配图（讲到对应内容时展示给学生）", "🖼 Figures in this slice (show them when you reach that content)"),
    "q_fig": ("🖼 题面图（出题前先展示）", "🖼 Question figure (show it before asking)"),
    "a_fig": ("🖼 答案图（讲解答案时展示）", "🖼 Answer figure (show it while explaining the answer)"),
    "no_text_ch": ("这一章没有可提取的文本。请直接打开下面的文件逐页阅读后讲解：",
                   "This chapter has no extractable text. Open these files and read them page by page:"),
    "quiz_head": ("测验", "Quiz"),
    "no_quiz": ("没有可用的题目。", "No usable questions."),
    "ref_answer": ("参考答案", "Reference answer"),
    "no_ref": ("材料里没有这道题的答案。你的答案必须标注 ⚠️ AI 生成答案，非老师/教材提供。",
               "The materials do not contain an answer. Label yours: ⚠️ AI-generated answer — not from your teacher or textbook."),
    "stmt_missing": ("题干不在材料里（教材题号）。请根据参考答案中复述的已知条件说明题意，并标注 🟡。",
                     "The problem statement is not in the materials (textbook number). Restate the givens from the reference answer and label them 🟡."),
    "givens": ("已知条件（摘自参考答案开头，可复述给学生）", "Givens (from the start of the reference answer; safe to restate)"),
    "recorded": ("已记录", "Recorded"),
    "unknown_q": ("找不到题目", "Unknown question id"),
    "unknown_ch": ("没有这一章", "No such chapter"),
    "done_ok": ("已标记完成", "Marked done"),
    "verified": ("已验证（本章至少答对 1 道材料题）", "verified (at least one material question answered right)"),
    "covered": ("已讲完但未验证（没有答对本章的材料题）", "covered but unverified (no material question answered right)"),
    "note_ok": ("已记入笔记", "Note saved"),
    "no_mistakes": ("没有待复习的错题。", "No open mistakes."),
    "cheatsheet_ok": ("小抄已写入", "Cheat sheet written to"),
    "search_none": ("材料中没有找到相关内容。请告诉学生「资料里没有这部分」，不要编造。",
                    "Nothing relevant found in the materials. Tell the student the materials do not cover this; do not invent."),
    "hint_next": ("继续讲：python coach.py next", "Continue: python coach.py next"),
    "hint_quiz": ("测验：python coach.py quiz", "Quiz: python coach.py quiz"),
    "hint_done": ("讲完本章：python coach.py done", "Finish chapter: python coach.py done"),
    "hint_ask": ("查资料：python coach.py ask \"关键词\"", "Look up: python coach.py ask \"keywords\""),
    "hint_check": ("看答案：python coach.py check <题号>   记录：python coach.py answer <题号> right|wrong|skip",
                   "Answer key: python coach.py check <id>   Record: python coach.py answer <id> right|wrong|skip"),
    "hint_figure": ("整页/局部截图：python coach.py figure <文件> <页码> [--crop x0,y0,x1,y1]",
                    "Page or region shot: python coach.py figure <file> <page> [--crop x0,y0,x1,y1]"),
    "goto_ok": ("已切换到第", "Switched to chapter"),
    "material_label": ("🟢 以下为资料原文（讲解时请注明出处）", "🟢 Material text follows (cite the source when teaching)"),
    "guessed": ("章节为自动推测", "chapter guessed automatically"),
    "figure_saved": ("已保存", "Saved"),
    "no_figures": ("没有找到配图。", "No figures found."),
    "unknown_file": ("材料里没有这个文件", "No such file in the materials"),
    "plan_head": ("📅 学习计划", "📅 Study plan"),
    "plan_day": ("第 %d 天", "Day %d"),
    "plan_last": ("最后一天：复习错题（mistakes --answers）并生成小抄（cheatsheet）", "Last day: review mistakes (mistakes --answers) and build the cheat sheet (cheatsheet)"),
    "plan_today": ("今天目标", "Today's target"),
    "plan_loop": ("每章流程：next 讲完 → quiz → note --type summary → done", "Per chapter: next until the text ends → quiz → note --type summary → done"),
    "plan_no_days": ("没有设置考试日期。设置：python coach.py plan --days N", "No exam date set. Set it: python coach.py plan --days N"),
    "plan_done": ("所有章节已完成，只剩复习错题和小抄。", "All chapters done; only mistakes and the cheat sheet are left."),
    "export_ok": ("已复制 %d 张图到 %s（用下面的相对路径嵌入）", "Copied %d figure(s) to %s (embed the relative paths below)"),
    "export_none": ("没有可导出的图：先运行 next / quiz / check 列出图，或用 --qid / --chapter 指定。",
                    "Nothing to export: run next / quiz / check first, or pass --qid / --chapter."),
    "export_hint": ("聊天界面不显示这些图片时：python coach.py export --to <打开的工作区或宿主 artifact 目录>，再用它打印的相对路径嵌入",
                    "If your chat cannot render these paths: python coach.py export --to <open workspace or the host's artifact folder>, then embed the printed relative paths"),
    # --- CrushExam new strings ---
    "exams_head": ("已注册考试", "Registered exams"),
    "exams_active": ("★活跃", "active"),
    "exams_none": ("没有已注册的考试。运行 setup 创建第一个考试。", "No registered exams. Run setup to create one."),
    "switch_ok": ("已切换到考试", "Switched to exam"),
    "switch_none": ("找不到这个考试。运行 exams 查看所有考试。", "Exam not found. Run exams to see all registered exams."),
    "evidence_head": ("能力证据面板", "Evidence panel"),
    "evidence_levels": ("证据等级", "Evidence levels"),
    "evidence_no_data": ("还没有作答记录。先 quiz 答题。", "No attempts yet. Run quiz first."),
    "review_ok": ("已记录延迟复测", "Delayed re-test recorded"),
    "review_no_q": ("找不到这道题", "Unknown question"),
    "review_scheduled": ("下次复测日期", "Next review date"),
    "no_answer_grade": ("这道题没有参考答案，无法自动判分。请自行核对后用 answer 记录结果。", "This question has no reference answer. Cannot auto-grade. Check it yourself, then use answer to record."),
    "independent_flag": ("独立作答", "independent"),
    "kc_label": ("知识点", "KC"),
    "hinted_flag": ("提示下完成", "hinted"),
    "score_ok": ("已记录考后真实分数", "Post-exam score recorded"),
    "score_source": ("自报", "self-reported"),
    "score_show": ("考后真实分数", "Post-exam score"),
    "score_none": ("尚未记录考后真实分数。考后用 score 命令记录。", "No post-exam score recorded yet. Use score after the exam."),
    "score_warning": ("⚠️ 这是学生自报分数，非系统自动获取。练习正确率不等于考分。", "⚠️ This is a self-reported score, not auto-collected. Practice accuracy ≠ exam score."),
    "grade_head": ("自动判分", "Auto-grade"),
    "grade_right": ("✅ 回答正确", "✅ Correct"),
    "grade_wrong": ("❌ 回答错误", "❌ Incorrect"),
    "grade_partial": ("🔶 部分正确：少选无错选（按全对记录为错，可讲解后重测）", "🔶 Partially correct: missing some, no wrong picks (recorded wrong; re-teach then re-test)"),
    "grade_vs": ("你的答案 %s → 参考答案 %s", "Your answer %s → reference %s"),
    "grade_restate_tf": ("这是判断题，无法解析你的作答。请用 对/错（或 √/×、T/F、是/否）重新作答；本次不会记录。", "This is a true/false item and your answer could not be parsed. Restate with 对/错 (√/×, T/F); nothing was recorded."),
    "grade_restate_single": ("这是单选题，请回答一个选项字母（如 A）。本次不会记录。", "This is a single-choice item: answer with one option letter (e.g. A). Nothing was recorded."),
    "grade_restate_multi": ("多选题请用选项字母作答（如 ABD）。本次不会记录。", "For multi-choice answer with option letters (e.g. ABD). Nothing was recorded."),
    "grade_manual_subj": ("这是主观题，无法自动判分。请对照参考答案按要点自评，再用 answer 记录 right|wrong。", "This is a subjective question; it cannot be auto-graded. Compare with the reference, then record via answer right|wrong."),
    "grade_missing": ("少选了", "missing"),
    "grade_wrong_pick": ("错选了", "wrong pick"),
    "grade_hint": ("自动判分：python coach.py grade <题号> \"<你的答案>\" [--independent]", "Auto-grade: python coach.py grade <qid> \"<your answer>\" [--independent]"),
    "submit_ok": ("已提交作答（未判分、未揭晓）", "Answer submitted (not graded, not revealed)"),
    "your_answer": ("你的作答", "Your answer"),
    "submit_hint": ("现在可以查看解答：python coach.py check <题号>，随后用 grade/answer 记录判分结果", "Now you may reveal: python coach.py check <qid>, then record the verdict via grade/answer"),
    "check_blocked": ("⛔ 先交后查：这题已出示但你还没提交作答。先 submit 你的答案，再查看解答。", "⛔ Answer-first: this question is open but no answer was submitted. Run submit first, then check."),
    "grade_need_answer": ("没有待判作答。先 submit 你的答案，或直接 grade <题号> \"<答案>\"。", "No pending answer. submit your answer first, or call grade <qid> \"<answer>\"."),
    "grade_from_pending": ("（使用已提交的作答判分）", "(graded from the submitted answer)"),
    "answer_stop": ("本轮作答已记录。下一步由你选择：继续当前任务 / 下一题 / 查看任务清单", "Recorded. Your choice next: continue the current task / next question / view the task list"),
    "review_sameday": ("⚠️ 同日复测：与上次作答同一天，不计为延迟独立（按即时记录）。真正的延迟复测需隔天。", "⚠️ Same-day re-test: not counted as delayed (recorded as immediate). A delayed re-test must happen on a later day."),
    "diagnose_first": ("下一步: python coach.py quiz --stratified -n 6  （入口必经：先小规模分层诊断 → gaps → plan，再开始讲课，不要直接 next）", "Next: python coach.py quiz --stratified -n 6  (entry path: stratified diagnosis → gaps → plan BEFORE teaching; do not jump to next)"),
    "blueprint_head": ("考试蓝图", "Exam blueprint"),
    "blueprint_none": ("还没有考试蓝图。构建方法：把课程的 KC 词典（知识点+关键词）写成 JSON，然后 blueprint --file kc-dict.json 导入；格式见 references/blueprint-kc-dictionary.md。", "No blueprint yet. Write the course KC dictionary (knowledge components + keywords) as JSON and import it: blueprint --file kc-dict.json; format: references/blueprint-kc-dictionary.md"),
    "blueprint_structure": ("考试结构", "Exam structure"),
    "blueprint_structure_unknown": ("未知（可稍后用 --file 带 structure 导入，或 setup 时留空）", "unknown (import a structure via --file, or leave it empty)"),
    "blueprint_kcs": ("KC 知识点", "KCs"),
    "blueprint_coverage": ("映射", "Mapped"),
    "blueprint_unmapped": ("未映射题目（不按关键词猜标签，按章聚合展示）", "Unmapped questions (not guessed by keywords; shown aggregated per chapter)"),
    "blueprint_imported": ("蓝图已导入", "Blueprint imported"),
    "blueprint_need_file": ("没有可导入的文件。用法：blueprint --file kc-dict.json", "No file to import. Usage: blueprint --file kc-dict.json"),
    "blueprint_rebuilt": ("已按当前题库重建映射", "Re-mapped against the current bank"),
    "blueprint_file_missing": ("文件不存在", "file not found"),
    "blueprint_bad_file": ("文件无法解析（应为 JSON 对象或 KC 列表）", "could not parse (expected a JSON object or a list of KCs)"),
    "gaps_head": ("知识点能力表", "Knowledge-component ability"),
    "gaps_fallback": ("没有 KC 词典，按章聚合（导入蓝图后可按知识点查看）", "No KC dictionary — aggregated by chapter (import a blueprint for KC-level view)"),
    "gaps_unmapped_note": ("未映射题目按章聚合展示，保证不遗漏", "Unmapped questions are shown per chapter so nothing is hidden"),
    "gaps_based_on": ("基于", "based on"),
    "gaps_questions": ("题作答", "attempts"),
    "gaps_summary": ("证据强度汇总", "Evidence summary"),
    "weak_head": ("缺口优先级", "Priority gaps"),
    "weak_no_data": ("（作答样本不足或尚无错题，先按计划推进）", "(too few attempts; follow the plan)"),
    "stratified_tag": ("分层抽样：按章题量加权，覆盖多章，优先未测题", "stratified: chapters weighted by bank size, untested first"),
    "usage_head": ("用量与积分归因", "Usage & credit attribution"),
    "usage_source": ("数据来源", "Source"),
    "usage_log_missing": ("找不到 .tool-usage-log.json。可用 --log 指定路径（或把文件放到 ~/.config/TeleAgent 或 ~/.local/share/TeleAgent 下）。", "No .tool-usage-log.json found. Pass --log PATH (or drop the file under ~/.config/TeleAgent or ~/.local/share/TeleAgent)."),
    "usage_log_bad": ("日志无法解析（应为 JSON，含 sessions 字段）", "Could not parse the log (expected JSON with a sessions field)"),
    "usage_range": ("统计范围", "Window"),
    "usage_calls": ("工具调用", "tool calls"),
    "usage_sessions": ("会话", "sessions"),
    "usage_empty_sessions": ("其中空会话（0 调用）", "of which empty (0 calls)"),
    "usage_by_day": ("按天分布", "Per-day breakdown"),
    "usage_heaviest": ("调用最多的会话", "Heaviest sessions"),
    "usage_ocr": ("本地渲染图文件数（非视觉调用数）", "Locally rendered image files (not vision calls)"),
    "usage_ocr_none": ("未提供渲染目录，跳过视觉估算。用 --ocr-dir 指向含渲染 PNG 的目录即可。", "No render dir given; vision estimate skipped. Point --ocr-dir at a directory of rendered PNGs."),
    "usage_ocr_dir": ("目录", "dir"),
    "usage_ocr_images": ("个缓存文件；实际视觉调用未知", "cached files; actual vision calls unknown"),
    "usage_note_1": ("工具调用次数 ≠ 积分余额；兑换规则以账户为准", "Tool calls ≠ credits; billing rules live in the host account"),
    "usage_note_2": ("日志只记工具调用次数、不含计费项目；渲染图数量也不能推算 OCR 调用或积分", "The log counts calls, not billable items; cached image files cannot establish OCR calls or credits"),
    "usage_note_3": ("节约调用：复用已提取文本和已有答题记录；缺页只手动核验，不对整套资料重复 OCR", "Reuse extracted text and recorded attempts; check missing pages selectively rather than re-OCRing everything"),
}


# ------------------------------------------------------------------ progress line

_SHOWN = []  # figure paths printed by the current command (for `export` without arguments)


def days_for_study(state):
    days = state.get("exam_days")
    if not days or days < 1:
        return None
    return max(1, days - 1) if days >= 2 else 1  # keep the last day for mistakes + cheat sheet


def daily_groups(state):
    """Split the remaining chapters over the remaining study days: [[chapter, ...], ...]."""
    todo = [c for c in state["chapters"] if c["status"] == "todo"]
    cur = st.chapter(state)
    if cur and cur["status"] == "todo":
        todo = [cur] + [c for c in todo if c["n"] != cur["n"]]
    days = days_for_study(state)
    if not todo or not days:
        return [todo] if todo else []
    days = min(days, len(todo))
    base, extra = divmod(len(todo), days)
    groups, i = [], 0
    for d in range(days):
        size = base + (1 if d < extra else 0)
        groups.append(todo[i:i + size])
        i += size
    return groups


def footer(state, w, next_cmd):
    flow = wf.ensure(state)
    label = wf.LABELS.get(flow.get("stage"), "阶段待恢复")
    task = taskmod.current(state)
    bits = [label]
    if task:
        bits.append(shorten(task["label"], 30))
    bits.append("有效作答 %d" % len(state.get("history", [])))
    return "📍 " + " · ".join(bits) + (" → " + next_cmd if next_cmd else " · 等待你的下一步选择")


def _workflow(state):
    return wf.ensure(state)


def _stage(state):
    return _workflow(state).get("stage", "studying")


def _diagnosis_remaining(state):
    flow = _workflow(state)
    return [qid for qid in flow.get("diagnostic_ids", [])
            if qid not in flow.get("diagnostic_submitted", [])]


def _diagnosis_submitted(state, qid):
    flow = state.get("workflow")
    if not isinstance(flow, dict) or flow.get("stage") != "diagnosing":
        return
    if qid in flow.get("diagnostic_ids", []) and qid not in flow.setdefault("diagnostic_submitted", []):
        flow["diagnostic_submitted"].append(qid)
    if not _diagnosis_remaining(state):
        flow["stage"] = "analysis"


def _gate_study(state, w):
    stage = _stage(state)
    if stage == "diagnosing":
        print(("先完成摸底（剩余 %d 题）；然后看能力分析与首轮计划。" % len(_diagnosis_remaining(state))) if w.zh else
              "Finish diagnosis first, then inspect your ability view and first plan.")
        print(footer(state, w, "python coach.py quiz --stratified"))
        return False
    if stage in ("analysis", "planning"):
        print("先查看能力缺口并确认首轮计划。" if w.zh else "Review your gaps and first plan before continuing.")
        print(footer(state, w, "python coach.py gaps" if stage == "analysis" else "python coach.py plan"))
        return False
    if stage not in ("planned", "studying"):
        print("阶段暂停或异常，先恢复；不会默认放行。")
        print(footer(state, w, "python coach.py session recover"))
        return False
    return True


class W(object):
    """Wording in the workspace language."""

    def __init__(self, lang):
        self.zh = lang == "zh"

    def __call__(self, key):
        return _T[key][0 if self.zh else 1]


# ------------------------------------------------------------------ workspace io

def _write_json(path, obj):
    st._atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=1))


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_workspace(explicit):
    selected = explicit or os.environ.get("CRUSHEXAM_WORKSPACE") or os.environ.get("EXAM_CRAM_WORKSPACE")
    if selected:
        return os.path.abspath(selected) if os.path.exists(st.path(selected)) else None
    # Try the CrushExam exam registry first
    ws = exammod.get_active_workspace()
    if ws and os.path.exists(st.path(ws)):
        return ws
    if os.path.exists(st.path("exam-cram")):
        return os.path.abspath("exam-cram")
    if os.path.exists(POINTER):
        cand = open(POINTER, encoding="utf-8").read().strip()
        if cand and os.path.exists(st.path(cand)):
            return cand
    return None


def remember_workspace(ws):
    # The registry is the primary store; the old pointer is kept for backward compat
    try:
        os.makedirs(os.path.dirname(POINTER), exist_ok=True)
        with open(POINTER, "w", encoding="utf-8") as fh:
            fh.write(ws)
    except OSError:
        pass


def load_ws(args):
    ws = resolve_workspace(args.workspace)
    if ws is None:
        sys.stderr.write(_T["no_ws"][0] + "\n" + _T["no_ws"][1] + "\n")
        sys.exit(2)
    state = st.load(ws)
    return ws, state, W(state["language"])


def load_chapters(ws):
    return [chmod.Chapter.from_dict(d) for d in _read_json(os.path.join(ws, CHAPTERS_FILE), [])]


def load_bank(ws):
    return _read_json(os.path.join(ws, BANK_FILE), [])


def load_figures(ws):
    return _read_json(os.path.join(ws, FIGURES_FILE), [])


def chapter_parts(ch, slice_chars):
    """Stable split of a chapter into teachable pieces: [[(anchor, text), ...], ...]."""
    segments = []
    for rel, page, text in ch.blocks:
        for piece in pack(text, slice_chars):
            segments.append(("%s p.%s" % (rel, page), piece))
    parts, cur, size = [], [], 0
    for seg in segments:
        if cur and size + len(seg[1]) > slice_chars:
            parts.append(cur)
            cur, size = [], 0
        cur.append(seg)
        size += len(seg[1])
    if cur:
        parts.append(cur)
    return parts


def render_part(part):
    out, last_anchor = [], None
    for anchor, text in part:
        if anchor != last_anchor:
            out.append("[%s]" % anchor)
            last_anchor = anchor
        out.append(text)
        out.append("")
    return "\n".join(out).rstrip()


def part_pages(part):
    pages = []
    for anchor, _ in part:
        m = re.match(r"(.+) p\.(\d+)$", anchor)
        if m and (m.group(1), int(m.group(2))) not in pages:
            pages.append((m.group(1), int(m.group(2))))
    return pages


def figures_for_pages(figs, pages):
    wanted = set(pages)
    return [f for f in figs if f.get("kind") == "figure" and (f["file"], f["page"]) in wanted]


# ------------------------------------------------------------------ question crops

def _segments_for(infos, heads, i):
    """Page regions (page, top, bottom) covered by block i, given all block heads in order."""
    page, head = heads[i][0], heads[i][1]
    info = infos.get(page)
    top = figmod.find_text_top(info, head) if info else None
    if top is None:
        return []
    nxt = heads[i + 1] if i + 1 < len(heads) else None
    if nxt and nxt[0] == page:
        nt = figmod.find_text_top(infos[page], nxt[1])
        return [(page, top, nt if nt is not None else 24)]
    segs = [(page, top, 24)]
    if info.scan:
        return segs  # pages after a scanned list are the student's own sheets, never the question
    last = nxt[0] if nxt else min(page + 3, max(infos))
    for p in range(page + 1, last):
        if p in infos:
            segs.append((p, infos[p].height - 24, 24))
    if nxt and nxt[0] in infos:
        nt = figmod.find_text_top(infos[nxt[0]], nxt[1])
        if nt is not None:
            segs.append((nxt[0], infos[nxt[0]].height - 24, nt))
    return segs


def attach_question_figures(materials, ws, bank, pdf_infos, sources):
    """Crop the printed region of each question/answer that contains a picture."""
    by_rel = {s.rel: s for s in sources}
    head_cache = {}

    def heads_of(rel):
        if rel not in head_cache:
            head_cache[rel] = qmod.heads(by_rel[rel]) if rel in by_rel else []
        return head_cache[rel]

    records = []
    for it in bank:
        for side, key in (("source", "figures"), ("answer_source", "answer_figures")):
            ref = it.get(side)
            it[key] = []
            if not ref or ref["file"] not in pdf_infos:
                continue
            heads = heads_of(ref["file"])
            pos = next((k for k, h in enumerate(heads) if h[0] == ref["page"] and h[1] == ref.get("head")), None)
            if pos is None:
                continue
            segs = _segments_for(pdf_infos[ref["file"]], heads, pos)
            label = it["id"] if side == "source" else it["id"] + "_ans"
            paths = figmod.crop_blocks(materials, ws, ref["file"], pdf_infos[ref["file"]], segs, figmod.safe_stem(ref["file"]), label)
            it[key] = paths
            for p in paths:
                records.append({"file": ref["file"], "page": ref["page"], "path": p, "kind": "question" if side == "source" else "answer", "qid": it["id"], "box": None})
    return records


# ------------------------------------------------------------------ commands

def cmd_setup(args):
    t0 = time.time()
    materials = os.path.abspath(args.materials)
    if not os.path.isdir(materials):
        sys.stderr.write("materials folder not found: %s\n" % materials)
        return 2
    default_ws = os.path.join(materials, "exam-cram")
    prior_root = st.load(default_ws) if os.path.isfile(st.path(default_ws)) else None
    exam_id = args.exam or (prior_root.get("exam_id") if prior_root and not args.workspace else None) or (
        "exam_%s" % _dt.datetime.now().strftime("%Y%m%d%H%M%S"))
    try:
        ws = exammod.suggest_workspace(materials, exam_id, workspace=args.workspace)
    except ValueError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2
    ws = os.path.abspath(ws)
    old = st.load(ws) if os.path.isfile(st.path(ws)) else None
    if old and args.exam and old.get("exam_id") not in (None, args.exam):
        sys.stderr.write("workspace belongs to another exam; choose a different --workspace or --exam\n")
        return 2
    old_bank = load_bank(ws) if old else []
    if old and not args.exam and old.get("exam_id") and not prior_root:
        exam_id = old["exam_id"]
    os.makedirs(os.path.join(ws, "chapters"), exist_ok=True)

    sources = extract.scan(materials)
    fig_records, scan_pages, pdf_infos = figmod.extract_figures(materials, sources, ws)
    n_scan = 0
    for src in sources:
        scans = scan_pages.get(src.rel, set())
        for p in src.pages:
            p.scan = p.number in scans
        n_scan += len(scans)
    chapters = chmod.build_chapters(sources)
    fallback_chapter = not chapters and bool(sources)
    if fallback_chapter:
        # Homework-only folders still need a chapter placeholder for a usable
        # plan. Its name explicitly says that no curriculum mapping is known.
        placeholder = chmod.Chapter(1, "题库资料（章节待核）")
        placeholder.sources = [src.rel for src in sources]
        chapters = [placeholder]
    all_text = "\n".join(c.text for c in chapters)
    lang = args.lang or ("zh" if is_mostly_cjk(all_text) else "en")
    w = W(lang)
    slice_chars = args.slice or DEFAULT_SLICE[lang]
    bank = qmod.extract_questions(sources, chapters)
    if fallback_chapter:
        for q in bank:
            if q.get("chapter") is None:
                q["chapter"] = 1
                q["chapter_guessed"] = True
    fig_records += attach_question_figures(materials, ws, bank, pdf_infos, sources)
    chunks = idx.build_chunks(chapters)

    # readable chapter files (short names: deep Windows paths hit the 260-char limit)
    for stale_name in os.listdir(os.path.join(ws, "chapters")):
        if stale_name.startswith("ch") and stale_name.endswith(".md"):
            os.remove(os.path.join(ws, "chapters", stale_name))
    for ch in chapters:
        safe = re.sub(r"[^\w\-]+", "_", ch.title)[:24].strip("_")
        body = "# %d. %s\n\n" % (ch.number, ch.title)
        body += "\n\n".join(render_part(p) for p in chapter_parts(ch, slice_chars)) + "\n"
        for fname in ("ch%02d_%s.md" % (ch.number, safe) if safe else "", "ch%02d.md" % ch.number):
            if not fname:
                continue
            try:
                with open(os.path.join(ws, "chapters", fname), "w", encoding="utf-8") as fh:
                    fh.write(body)
                break
            except OSError:
                continue
    _write_json(os.path.join(ws, CHAPTERS_FILE), [c.to_dict() for c in chapters])
    _write_json(os.path.join(ws, BANK_FILE), bank)
    _write_json(os.path.join(ws, FIGURES_FILE), fig_records)
    idx.save_index(ws, chunks)

    course = args.name or os.path.basename(materials.rstrip("\\/")) or "course"
    ch_summaries = []
    for ch in chapters:
        ch_summaries.append({
            "n": ch.number, "title": ch.title, "sources": ch.sources,
            "parts": len(chapter_parts(ch, slice_chars)),
            "questions": sum(1 for q in bank if q["chapter"] == ch.number),
        })
    state = st.new_state(course, lang, args.days, materials, ch_summaries, slice_chars,
                          exam_id=exam_id, exam_date=args.date, goal=args.goal or "pass")
    migration = {}
    if old and old.get("version") >= 5 and not args.fresh:
        if old.get("exam_id") == exam_id:
            keep = {c["n"]: c for c in old["chapters"]}
            for c in state["chapters"]:
                if c["n"] in keep:
                    c["status"] = keep[c["n"]]["status"]
                    c["part"] = min(keep[c["n"]]["part"], c["parts"])
            state["notes"] = old.get("notes", [])
            state["current"] = old["current"] if st.chapter(state, old["current"]) else state["current"]
            state["created"] = old["created"]
            for key in ("workflow", "post_exam_score", "study_minutes", "weekly_hours", "last_plan"):
                if key in old:
                    state[key] = old[key]
            if args.days is None:
                state["exam_days"] = old.get("exam_days")
            if args.date is None:
                state["exam_date"] = old.get("exam_date")
            if args.goal is None:
                state["goal"] = old.get("goal", "pass")
        # The helper maps only identical question/answer versions, quarantining
        # changed or unassigned old attempts instead of crediting a new exam.
        migration = st.reconcile_question_records(state, old, old_bank, bank, exam_id=exam_id)
        at.reconcile_runtime(state, old, old_bank, bank)
        flow = state.get("workflow") or {}
        if flow.get("diagnostic_ids"):
            qid_map = migration.get("qid_map", {})
            ids = [qid_map[q] for q in flow["diagnostic_ids"] if q in qid_map]
            if len(ids) != len(flow["diagnostic_ids"]):
                state["workflow"] = {"stage": "diagnosing", "diagnostic_ids": [],
                                     "diagnostic_submitted": []}
            else:
                flow["diagnostic_ids"] = ids
                flow["diagnostic_submitted"] = [qid_map[q] for q in flow.get("diagnostic_submitted", []) if q in qid_map]
    if "workflow" not in state:
        state["workflow"] = {"stage": "analysis" if state.get("history") else "diagnosing",
                             "diagnostic_ids": [],
                             "diagnostic_submitted": []}
    if migration.get("quarantined_history"):
        for ch in state["chapters"]:
            if ch["status"] == "verified" and st.chapter_results(state, ch["n"])[0] == 0:
                ch["status"] = "todo"
        state.pop("last_plan", None)
        if state.get("history") and state["workflow"]["stage"] in ("planned", "studying"):
            state["workflow"]["stage"] = "analysis"
    if args.minutes is not None:
        state["study_minutes"] = max(1, args.minutes)
    if args.weekly_hours is not None:
        state["weekly_hours"] = max(0.0, args.weekly_hours)
    if args.start:
        state["current"] = args.start
    st.save(ws, state)
    remember_workspace(ws)

    # Auto-import a course KC dictionary if one sits next to the materials
    # (kc-dict.json or blueprint.json), so a re-setup keeps the blueprint.
    auto_kc = os.path.join(materials, "kc-dict.json")
    if not os.path.exists(auto_kc):
        auto_kc = os.path.join(materials, "blueprint.json")
    old_bp = bpmod.load(ws)
    if old_bp and migration.get("qid_map"):
        valid_ids = {q["id"] for q in bank}
        qid_map = migration["qid_map"]
        for key in ("overrides", "question_meta"):
            old_bp[key] = {qid_map.get(k, k): v for k, v in (old_bp.get(key) or {}).items()
                           if qid_map.get(k, k) in valid_ids}
        bpmod.save(ws, old_bp)
    if os.path.exists(auto_kc):
        try:
            with open(auto_kc, encoding="utf-8") as fh:
                data = json.load(fh)
            bp = bpmod.load(ws) or bpmod.new_blueprint()
            bpmod.import_payload(bp, data)
            bpmod.rebuild(bp, bank)
            bpmod.save(ws, bp)
            cov = bpmod.coverage(bank, bp.get("q_map") or {})
            print("📋 %s: %s（%d %s / %d）" % (
                w("blueprint_imported"), os.path.basename(auto_kc),
                cov["mapped"], w("questions"), cov["total"]))
        except (ValueError, json.JSONDecodeError):
            print("⚠️ %s 存在但无法解析，跳过（blueprint --file 可手动导入）" % os.path.basename(auto_kc))
    elif old_bp:
        bpmod.rebuild(old_bp, bank)
        bpmod.save(ws, old_bp)

    # Register this exam in the global registry
    # Parse scope: comma-separated items → list of {"item": str, "source": "student", "confirmed": False}
    scope_list = []
    if args.scope:
        for item in args.scope.split(","):
            item = item.strip()
            if item:
                scope_list.append({"item": item, "source": "student confirmed" if args.confirm_scope else "student to verify",
                                   "confirmed": bool(args.confirm_scope)})
    # Parse question_types: comma-separated strings
    qt_list = []
    if args.question_types:
        qt_list = [t.strip() for t in args.question_types.split(",") if t.strip()]
    registered = exammod.get_exam(exam_id) or {}
    try:
        exammod.register(
        exam_id=exam_id,
        course=course,
        exam_type=args.type or registered.get("exam_type") or "final",
        exam_date=state.get("exam_date"),
        goal=state.get("goal") or "pass",
        workspace=ws,
        materials_path=materials,
        weekly_hours=state.get("weekly_hours"),
        scope=scope_list if args.scope is not None else registered.get("scope", []),
        question_types=qt_list if args.question_types is not None else registered.get("question_types", []),
        )
    except ValueError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2

    # report
    kinds = {}
    for s in sources:
        kinds[s.kind] = kinds.get(s.kind, 0) + 1
    print("%s: %s  (%.1fs)" % (w("setup_done"), ws, time.time() - t0))
    print("%s: %s" % (w("files"), ", ".join("%s×%d" % kv for kv in sorted(kinds.items())) or "0"))
    print("%s (%d):" % (w("chapters"), len(chapters)))
    for c in state["chapters"][:6]:
        print("  %2d. %s  [%s; %d %s]" % (c["n"], c["title"], ", ".join(c["sources"]), c["questions"], w("questions")))
    if len(state["chapters"]) > 6:
        print("  … +%d（status --detail 查看全部）" % (len(state["chapters"]) - 6))
    answered = sum(1 for q in bank if q["answer"])
    print("%s: %d (%d %s)" % (w("questions"), len(bank), answered, w("with_answers")))
    n_fig = sum(1 for f in fig_records if f["kind"] == "figure")
    n_q = sum(1 for f in fig_records if f["kind"] in ("question", "answer"))
    print("%s: %d + %d question/answer crops%s" % (w("figures_count"), n_fig, n_q, ("; %d %s" % (n_scan, w("scan_note"))) if n_scan else ""))
    notes = []
    pdf_missing = [s.rel for s in sources if s.error == "pdf_support_missing"]
    if pdf_missing:
        notes.append("%d %s: %s" % (len(pdf_missing), w("pdf_missing"), ", ".join(pdf_missing)))
    elif any(s.rel.lower().endswith(".pdf") for s in sources) and not figmod.has_pdfium():
        notes.append(w("no_pdfium"))
    for s in sources:
        if s.error and s.error != "pdf_support_missing":
            notes.append("%s %s (%s)" % (s.rel, w("read_error"), s.error))
        elif "no_text" in s.warnings:
            notes.append("%s %s" % (s.rel, w("no_text")))
        for wn in s.warnings:
            if wn.startswith("figures_failed"):
                notes.append("%s: %s" % (s.rel, wn))
    print("资料 | 类型(自动归类) | 提取状态 | 用途/待核对")
    print("--- | --- | --- | ---")
    for src in sources[:8]:
        ok = bool(src.text) and not src.error
        status = "可提取" if ok else "需核对/扫描件"
        role = {"homework": "基础原题", "exam": "练习卷(真题身份待核)",
                "solution": "核对答案", "lecture": "理解概念/例题"}.get(src.kind, "人工核对")
        print("%s | %s | %s | %s" % (src.rel.replace("|", "/"), src.kind, status, role))
    if len(sources) > 8:
        print("… 另有 %d 份资料，完整清单见 source_manifest.md" % (len(sources) - 8))
    manifest_path = os.path.join(ws, "source_manifest.md")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write("# 资料提取与使用清单\n\n")
        mf.write("文件 | 自动归类 | 提取状态 | 用途及人工核对点\n--- | --- | --- | ---\n")
        for src in sources:
            status = "可提取" if src.text and not src.error else "需核对/扫描件"
            role = {"homework": "基础原题", "exam": "练习卷（真题身份待核）",
                    "solution": "核对答案", "lecture": "理解概念/例题"}.get(src.kind, "人工核对")
            mf.write("%s | %s | %s | %s\n" %
                     (src.rel.replace("|", "/").replace("\n", " "), src.kind, status, role))
        if notes:
            mf.write("\n## 提取限制\n\n")
            for item in notes:
                mf.write("- %s\n" % item.replace("\n", " "))
    print("文件 | 内容 | 用途")
    print("--- | --- | ---")
    print("%s | 全量资料来源、提取状态及待核对点 | 确认考试重点与遗漏材料" % manifest_path)
    if notes:
        print(w("warnings") + ":")
        for n in notes:
            print("  - " + n)
    # Entry path guard: a NEW exam starts with a small diagnosis, not teaching.
    # An existing exam (re-setup with history kept) resumes at status.
    if _stage(state) == "diagnosing":
        print(w("diagnose_first"))
    else:
        next_step = {"analysis": "gaps", "planning": "plan"}.get(_stage(state), "status")
        print(w("next_steps") + ": python coach.py " + next_step)
    return 0


def cmd_status(args):
    from . import runtime
    return runtime.status(args)


def _advance_to_next_todo(state):
    for c in state["chapters"]:
        if c["status"] == "todo":
            state["current"] = c["n"]
            return c
    return None


def _print_examples(w, ws, bank, n, limit=8):
    items = [q for q in bank if q["chapter"] == n]
    print("--- %s (%d) ---" % (w("ch_examples"), len(items)))
    if not items:
        print(w("no_examples"))
        return
    for q in items[:limit]:
        flag = w("answer_yes") if q["answer"] else w("answer_no")
        guess = " (%s)" % w("guessed") if q.get("chapter_guessed") else ""
        fig = " 🖼" if q.get("figures") or q.get("answer_figures") else ""
        print("[%s] %s | %s p.%s | %s%s%s" % (q["id"], shorten(q["question"] or q["source"].get("head", ""), 100), q["source"]["file"], q["source"]["page"], flag, guess, fig))
    if len(items) > limit:
        print("… +%d" % (len(items) - limit))


def _abs_fig(ws, p):
    return os.path.join(ws, p.replace("/", os.sep))


def _print_figs(ws, label, paths):
    if not paths:
        return
    print(label + ":")
    for p in paths:
        full = _abs_fig(ws, p)
        _SHOWN.append(full)
        print("  " + full)


def _remember_shown(ws, state):
    if _SHOWN:
        state["last_figures"] = list(dict.fromkeys(_SHOWN))
        st.save(ws, state)


def _legacy_next(args):
    ws, state, w = load_ws(args)
    if not _gate_study(state, w):
        return 4
    cur = st.chapter(state)
    if cur is None or cur["status"] != "todo":
        cur = _advance_to_next_todo(state)
    if cur is None:
        print(w("all_done"))
        st.save(ws, state)
        return 0
    chs = {c.number: c for c in load_chapters(ws)}
    ch = chs[cur["n"]]
    slice_chars = args.chars or state["slice_chars"]
    parts = chapter_parts(ch, slice_chars)
    cur["parts"] = len(parts)
    if args.back:
        cur["part"] = max(0, cur["part"] - 2)
    elif args.repeat:
        cur["part"] = max(0, cur["part"] - 1)
    k = cur["part"]
    head = ("第 %d 章：%s" if w.zh else "Chapter %d: %s") % (cur["n"], cur["title"])
    bank = load_bank(ws)
    if not parts:
        print("=== %s ===" % head)
        print(w("no_text_ch"))
        for rel in cur["sources"]:
            print("  - " + os.path.join(state["materials"], rel))
        if ch.figures:
            print(w("figures") + ":")
            for f in ch.figures:
                print("  - " + os.path.join(state["materials"], f))
        cur["part"] = 0
        _print_examples(w, ws, bank, cur["n"])
        print("%s | %s" % (w("hint_quiz"), w("hint_done")))
        st.save(ws, state)
        print(footer(state, w, "python coach.py quiz"))
        return 0
    if k >= len(parts):
        print("=== %s (%s %d/%d) ===" % (head, w("part"), len(parts), len(parts)))
        print(w("ch_end"))
        _print_examples(w, ws, bank, cur["n"])
        print("%s | %s" % (w("hint_quiz"), w("hint_done")))
        st.save(ws, state)
        print(footer(state, w, "python coach.py quiz"))
        return 0
    print("=== %s (%s %d/%d) ===" % (head, w("part"), k + 1, len(parts)))
    print(w("material_label"))
    print(safety.wrap(render_part(parts[k])))
    figs = figures_for_pages(load_figures(ws), part_pages(parts[k]))
    if figs:
        print("")
        print(w("slice_figs") + ":")
        for f in figs:
            full = _abs_fig(ws, f["path"])
            _SHOWN.append(full)
            print("  [%s p.%s] %s" % (f["file"], f["page"], full))
        print("  (%s)" % w("export_hint"))
    if k == 0 and ch.figures:
        print("\n" + w("figures") + ":")
        for f in ch.figures:
            full = os.path.join(state["materials"], f)
            _SHOWN.append(full)
            print("  - " + full)
    cur["part"] = k + 1
    if cur["part"] >= len(parts):
        print("")
        _print_examples(w, ws, bank, cur["n"])
        print("%s | %s" % (w("hint_quiz"), w("hint_done")))
        next_cmd = "python coach.py quiz"
    else:
        print("\n%s | %s" % (w("hint_next"), w("hint_ask")))
        next_cmd = "python coach.py next"
    if _SHOWN:
        state["last_figures"] = list(dict.fromkeys(_SHOWN))
    st.save(ws, state)
    print(footer(state, w, next_cmd))
    return 0


def cmd_chapter(args):
    from . import runtime
    return runtime.chapter(args)


def cmd_goto(args):
    from . import runtime
    return runtime.goto(args)


def cmd_ask(args):
    ws, state, w = load_ws(args)
    hits = idx.search(idx.load_index(ws), args.query, k=args.k, chapter=args.chapter)
    if not hits:
        print(w("search_none"))
        return 4
    figs = load_figures(ws)
    for c, score in hits:
        print("🟢 [ch%s | %s p.%s | score %.1f]" % (c["chapter"], c["file"], c["page"], score))
        print(safety.wrap(shorten(c["text"], args.chars)))
        for f in figures_for_pages(figs, [(c["file"], c["page"])]):
            full = _abs_fig(ws, f["path"])
            _SHOWN.append(full)
            print("  🖼 " + full)
        print("")
    _remember_shown(ws, state)
    print(footer(state, w, "python coach.py next"))
    return 0


def _pick_quiz(state, bank, n, count, include_all):
    from .runtime import _pick
    return _pick(state, bank, n, count, include_all)


def _givens(answer):
    """The setup a solution restates before it starts solving: text before the first sub-part or 'Solution'."""
    if not answer:
        return None
    cut = re.search(r"(?:^|\n)\s*(?:\([a-h1-9]\)|[（(][a-h1-9][)）]|solution\s*[:：]|解[:：])", answer, re.I)
    head = answer[: cut.start()] if cut else answer
    head = " ".join(head.split())
    if not head:
        return None  # the solution starts solving at once: nothing safe to restate
    return (head[:300] + "…") if len(head) > 300 else head


def _print_question(q, w, ws, with_answer=False):
    print("[%s] 第%s章｜%s｜%s p.%s" % (q["id"], q.get("chapter"), q.get("type"), q["source"]["file"], q["source"]["page"]))
    if q.get("context"):
        context = q["context"]
        source = context.get("source") or {}
        print("共享题干（来自前题原文，不含答案）：%s p.%s" % (source.get("file"), source.get("page")))
        print(safety.wrap(context.get("text", "")))
    print(safety.wrap((q.get("question") or "题干缺失，需核对原材料") +
                      ("\n" + "\n".join(q.get("options") or []) if q.get("options") else "")))
    if q.get("options"):
        print("呈现要求：以上每个选项独立成行、逐行原样展示（A./B./C./… 各占一行），不合并为一段，不改写选项文字。")
    _print_figs(ws, w("q_fig"), q.get("figures"))
    if with_answer:
        print("--- %s ---" % w("ref_answer"))
        if q.get("answer"):
            src = q.get("answer_source") or q["source"]
            print("🟢 (%s p.%s)" % (src["file"], src["page"]))
            print(safety.wrap(q["answer"]))
            _print_figs(ws, w("a_fig"), q.get("answer_figures"))
        else:
            print("资料中无可靠答案，保留未核验，不编造解答。")


def cmd_quiz(args):
    from . import runtime
    return runtime.quiz(args)


def _find_q(bank, qid):
    return next((q for q in bank if q["id"] == qid), None)


def cmd_submit(args):
    from . import runtime
    return runtime.submit(args)


def cmd_check(args):
    from . import runtime
    return runtime.check(args)


def cmd_answer(args):
    from . import runtime
    return runtime.answer(args)


def cmd_grade(args):
    from . import runtime
    return runtime.grade(args)


def cmd_done(args):
    from . import runtime
    return runtime.done(args)


def cmd_note(args):
    ws, state, w = load_ws(args)
    n = args.chapter or state["current"]
    state["notes"].append({"chapter": n, "type": args.type, "text": args.text.strip(), "ts": st.now()})
    st.save(ws, state)
    print("%s (ch%s, %s)" % (w("note_ok"), n, args.type))
    cur = st.chapter(state)
    nxt = "python coach.py done" if (args.type == "summary" and cur and cur["part"] >= cur["parts"]) else "python coach.py next"
    print(footer(state, w, nxt))
    return 0


def cmd_mistakes(args):
    ws, state, w = load_ws(args)
    bank = load_bank(ws)
    om = st.open_mistakes(state, args.chapter)
    if args.all_exams:
        # Aggregate mistakes across all exams
        entries, active = exammod.list_exams()
        all_om = []
        for e in entries:
            if e["exam_id"] == state.get("exam_id"):
                all_om.extend((e["exam_id"], m) for m in om)
                continue
            other_state = st.load(e["workspace"])
            if other_state:
                other_om = st.open_mistakes(other_state, args.chapter)
                all_om.extend((e["exam_id"], m) for m in other_om)
        if not all_om:
            print(w("no_mistakes"))
            return 0
        print("=== %s (--all-exams) ===" % w("mistakes"))
        for eid, m in all_om:
            mark = " *" if eid == state.get("exam_id") else ""
            print("  [%s%s] %s x%d ch%d %s" % (eid, mark, m["qid"], m["count"], m.get("chapter", 0), m.get("note", "")))
        print(footer(state, w, "python coach.py quiz"))
        return 0
    if not om:
        print(w("no_mistakes"))
        return 0
    for m in om:
        q = _find_q(bank, m["qid"])
        ev = m.get("evidence_level", "untested")
        ev_str = " | %s: %s" % (w("evidence_levels"), evmod.label(ev, w.zh)) if ev != "untested" else ""
        print("=== %s x%d %s%s ===" % (m["qid"], m["count"], m.get("note", ""), ev_str))
        if q:
            _print_question(q, w, ws, with_answer=args.answers)
        print("")
    print(w("hint_check"))
    _remember_shown(ws, state)
    print(footer(state, w, "python coach.py answer %s right|wrong|skip" % om[0]["qid"]))
    return 0


def cmd_cheatsheet(args):
    ws, state, w = load_ws(args)
    bank = load_bank(ws)
    out = [("# %s 考前小抄" if w.zh else "# %s cheat sheet") % state["course"], ""]
    for c in state["chapters"]:
        notes = [n for n in state["notes"] if n["chapter"] == c["n"]]
        mist = [m for m in state["mistakes"] if m["chapter"] == c["n"]]
        if not notes and not mist:
            continue
        out.append("## %d. %s" % (c["n"], c["title"]))
        for n in notes:
            if n["type"] == "summary":
                out.append(n["text"])
                out.append("")
        conf = [n for n in notes if n["type"] == "confusion"]
        if conf:
            out.append("**%s**" % ("疑难点" if w.zh else "Confusions"))
            for n in conf:
                out.append("- " + n["text"])
            out.append("")
        if mist:
            out.append("**%s**" % ("错题" if w.zh else "Mistakes"))
            for m in mist:
                q = _find_q(bank, m["qid"])
                if not q:
                    continue
                out.append("- [%s] %s" % (m["qid"], shorten(q["question"] or q["source"].get("head", ""), 200)))
                for p in q.get("figures") or []:
                    out.append("  ![](%s)" % p)
                if q["answer"]:
                    src = q.get("answer_source") or q["source"]
                    out.append("  - 🟢 %s: %s (%s p.%s)" % (w("ref_answer"), shorten(q["answer"], 300), src["file"], src["page"]))
                if m.get("note"):
                    out.append("  - " + m["note"])
            out.append("")
    dest = args.out or os.path.join(ws, "cheatsheet.md")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("%s: %s" % (w("cheatsheet_ok"), dest))
    return 0


def cmd_figures(args):
    ws, state, w = load_ws(args)
    figs = load_figures(ws)
    if args.chapter:
        chs = {c.number: c for c in load_chapters(ws)}
        if args.chapter not in chs:
            print(w("unknown_ch"))
            return 2
        pages = {(rel, page) for rel, page, _ in chs[args.chapter].blocks}
        figs = [f for f in figs if (f["file"], f["page"]) in pages]
    if args.file:
        figs = [f for f in figs if f["file"] == args.file]
    if args.page:
        figs = [f for f in figs if f["page"] == args.page]
    if not figs:
        print(w("no_figures"))
        print(w("hint_figure"))
        return 3
    for f in figs:
        extra = " (%s %s)" % (f["kind"], f.get("qid", "")) if f["kind"] != "figure" else ""
        print("[%s p.%s]%s %s" % (f["file"], f["page"], extra, os.path.join(ws, f["path"].replace("/", os.sep))))
    return 0


def cmd_figure(args):
    ws, state, w = load_ws(args)
    if not figmod.has_pdfium():
        print(w("no_pdfium"))
        return 2
    path = os.path.join(state["materials"], args.file)
    if not os.path.exists(path):
        print("%s: %s" % (w("unknown_file"), args.file))
        return 2
    import pypdfium2 as pdfium
    page = pdfium.PdfDocument(path)[args.page - 1]
    pw, ph = page.get_size()
    box = None
    tag = "page"
    if args.crop:
        x0, y0, x1, y1 = [float(v) for v in args.crop.split(",")]
        if max(x0, y0, x1, y1) <= 1.0:  # fractions of the page, top-left origin
            x0, x1, y0, y1 = x0 * pw, x1 * pw, y0 * ph, y1 * ph
        box = (min(x0, x1), ph - max(y0, y1), max(x0, x1), ph - min(y0, y1))
        tag = "crop_%d_%d_%d_%d" % (box[0], ph - box[3], box[2], ph - box[1])
    out_dir = os.path.join(ws, figmod.FIG_DIR)
    os.makedirs(out_dir, exist_ok=True)
    dest = args.out or os.path.join(out_dir, "%s_p%d_%s.png" % (figmod.safe_stem(args.file), args.page, tag))
    wpx, hpx = figmod.render_region(path, args.page, box, dest, scale=args.scale)
    print("%s: %s (%dx%d px)" % (w("figure_saved"), dest, wpx, hpx))
    return 0


def cmd_plan(args):
    from . import runtime
    return runtime.plan(args)


def cmd_export(args):
    import shutil
    ws, state, w = load_ws(args)
    bank = load_bank(ws)
    figs = load_figures(ws)
    chosen = []
    for qid in args.qid or []:
        q = _find_q(bank, qid)
        if q:
            chosen += [_abs_fig(ws, p) for p in (q.get("figures") or []) + (q.get("answer_figures") or [])]
    if args.chapter:
        chs = {c.number: c for c in load_chapters(ws)}
        if args.chapter in chs:
            pages = [(rel, page) for rel, page, _ in chs[args.chapter].blocks]
            chosen += [_abs_fig(ws, f["path"]) for f in figures_for_pages(figs, pages)]
    chosen += [os.path.abspath(p) for p in args.paths or []]
    if not chosen:
        chosen = list(state.get("last_figures") or [])
    chosen = [p for p in dict.fromkeys(chosen) if os.path.exists(p)]
    if not chosen:
        print(w("export_none"))
        return 3
    dest = os.path.abspath(args.to)
    os.makedirs(dest, exist_ok=True)
    copied = []
    for src in chosen:
        target = os.path.join(dest, os.path.basename(src))
        shutil.copy2(src, target)
        copied.append(target)
    print(w("export_ok") % (len(copied), dest))
    cwd = os.getcwd()
    for target in copied:
        try:
            inside = os.path.commonpath([cwd, target]) == cwd
        except ValueError:
            inside = False
        rel = os.path.relpath(target, cwd) if inside else target
        print("  " + rel.replace(os.sep, "/"))
    return 0


def cmd_doctor(args):
    print("CrushExam %s | python %s" % (__version__, sys.version.split()[0]))
    backend = extract.pdf_backend()
    if backend == "pypdfium2":
        print("pypdfium2: ok (PDF text + figure cropping)")
    elif backend == "pypdf":
        print("pypdf: ok (PDF text). pypdfium2 missing -> no figure cropping from PDFs: pip install pypdfium2")
    else:
        print("PDF support: missing -> pip install pypdfium2   (DOCX/PPTX/MD/TXT work without it)")
    # Show exam registry
    entries, active = exammod.list_exams()
    if entries:
        print("exams: %d registered, active: %s" % (len(entries), active or "(none)"))
        for e in entries:
            mark = " *" if e["exam_id"] == active else ""
            print("  %s%s  %s  %s" % (e["exam_id"], mark, e["course"], e.get("exam_date") or "(no date)"))
    else:
        print("exams: (none registered)")
    ws = resolve_workspace(args.workspace)
    print("workspace: %s" % (ws or "(none)"))
    return 0


# ------------------------------------------------------------------ CrushExam new commands

def cmd_exams(args):
    """List all registered exams."""
    entries, active = exammod.list_exams()
    if not entries:
        print(_T["exams_none"][0] + "\n" + _T["exams_none"][1])
        return 0
    print("=== %s ===" % _T["exams_head"][0])  # always show, language-agnostic table
    for e in entries:
        mark = " %s" % _T["exams_active"][0] if e["exam_id"] == active else ""
        date_str = e.get("exam_date") or "(no date)"
        goal = e.get("goal", "pass")
        etype = e.get("exam_type", "final")
        print("  %s  %s  %s  %s  [%s/%s]%s" % (
            e["exam_id"], e["course"], date_str, etype, goal, e.get("weekly_hours", "?"), mark))
    print("")
    print("python coach.py switch <exam_id>  |  python coach.py setup <folder> --exam <new_id>")
    return 0


def cmd_switch(args):
    """Switch the active exam."""
    entry = exammod.switch(args.exam_id)
    if entry is None:
        w_zh = True  # default to zh
        print(_T["switch_none"][0])
        return 2
    # Load state to check language
    state = st.load(entry["workspace"])
    w = W(state["language"]) if state else W("zh")
    print("%s: %s (%s)" % (w("switch_ok"), args.exam_id, entry["course"]))
    # Show status of the switched exam
    if state:
        done = sum(1 for c in state["chapters"] if c["status"] in ("done", "verified"))
        total = len(state["chapters"])
        print("%s: %s %d/%d" % (w("progress"), st.bar(done, total), done, total))
    print(w("next_steps") + ": python coach.py status")
    return 0


def cmd_evidence(args):
    from . import runtime
    return runtime.evidence_panel(args)


def cmd_review(args):
    from . import runtime
    return runtime.review(args)


def cmd_score(args):
    """Record or show the real post-exam score (self-reported)."""
    ws, state, w = load_ws(args)
    if args.score is None:
        # Show current score
        s = state.get("post_exam_score")
        if not s:
            print(w("score_none"))
            print(footer(state, w, "python coach.py score --score 85 --max 100"))
            return 0
        print("=== %s ===" % w("score_show"))
        print("  %s: %s/%s  (%s: %s)  %s" % (
            "分数" if w.zh else "Score", s.get("score", "?"), s.get("max", "?"),
            "日期" if w.zh else "date", s.get("date", "?"),
            "[%s]" % w("score_source")))
        if s.get("note"):
            print("  %s: %s" % ("备注" if w.zh else "Note", s["note"]))
        print("  %s" % w("score_warning"))
        print(footer(state, w, "python coach.py status"))
        return 0
    # Record a new score
    max_score = args.max if args.max is not None else 100.0
    try:
        score_val = float(args.score)
    except (ValueError, TypeError):
        print("Invalid score value")
        return 2
    state["post_exam_score"] = {
        "score": score_val,
        "max": float(max_score),
        "date": args.date or st.today(),
        "note": args.note or "",
        "source": "self-reported",
    }
    st.save(ws, state)
    print("%s: %s/%s  [%s]" % (
        w("score_ok"), score_val, max_score, w("score_source")))
    if args.note:
        print("  %s: %s" % ("备注" if w.zh else "Note", args.note))
    print(w("score_warning"))
    print(footer(state, w, "python coach.py status"))
    return 0


HELP_ZH = """CrushExam：先摸底，后分析，再制定计划；每次只展示一题。
  setup <材料目录> [--exam ID] [--date YYYY-MM-DD] [--goal pass|high|long] [--minutes N]
  blueprint --file <kc-dict.json>  导入你核实过的范围、题型和知识点（可后补）
  quiz --stratified [-n 6]       先分层摸底，当前仅展示一题
  submit <题号> "原答" [--hinted] [--confidence low|medium|high]
  gaps [--detail] [--html 路径]  摸底结束后分析，生成离线多维能力视图
  plan [--detail] [--minutes N]   给出当天任务和核验标准；--skip-diagnosis 可显式跳过摸底
  quiz [--qid 题号] | check 题号 | grade 题号 | answer 题号 right|wrong|skip
  status [--detail] | evidence | review 题号 --result right|wrong
  exams | switch <ID> | next | chapter | goto | ask | done | note | mistakes
  resume | clarify <qid> "澄清" | skip | defer | diagnose --restart
  task show|note|assess|skip-check|finish | session pause|resume|finish|recover | attempts [--json]
  workbench | import-answer <JSON> | verify-transfer <目标qid> <基题qid> --kc ... --kind parameter|representation|context --basis ... --confirmed
  rubric draft|freeze|ratings <qid> | verify-reason <qid>  (see -h)
  cheatsheet | score | usage | export | figures | figure | doctor
使用 python coach.py <命令> -h 查看参数。积分消耗请以实际账户明细为准。"""

HELP_EN = """CrushExam: diagnose, inspect evidence, plan, then study; one question at a time.
  setup <materials> [--exam ID] [--date YYYY-MM-DD] [--goal pass|high|long] [--minutes N]
  blueprint --file <kc-dict.json>  Import a sourced and verified course map (optional)
  quiz --stratified [-n 6]       Start a representative diagnosis, one item per turn
  submit <qid> "raw answer" [--hinted] [--confidence low|medium|high]
  gaps [--detail] [--html PATH] Inspect attempts and generate an offline capability view
  plan [--detail] [--minutes N]   Today's task and completion rule; --skip-diagnosis if needed
  quiz [--qid ID] | check ID | grade ID | answer ID right|wrong|skip
  status [--detail] | evidence | review ID --result right|wrong
  exams | switch <ID> | next | chapter | goto | ask | done | note | mistakes
  resume | clarify <qid> "clarification" | skip | defer | diagnose --restart
  task show|note|assess|skip-check|finish | session pause|resume|finish|recover | attempts [--json]
  workbench | import-answer <JSON> | verify-transfer <target> <base> --kc ... --kind parameter|representation|context --basis ... --confirmed
  rubric draft|freeze|ratings <qid> | verify-reason <qid>  (see -h)
  cheatsheet | score | usage | export | figures | figure | doctor
Use python coach.py <command> -h for all flags. For credits, rely on the host's bill."""


def cmd_blueprint(args):
    """Import / rebuild / show the exam blueprint (KC dictionary + exam structure)."""
    ws, state, w = load_ws(args)
    bank = load_bank(ws)
    bp = bpmod.load(ws) or bpmod.new_blueprint()
    changed = False
    if args.file:
        if not os.path.exists(args.file):
            print("%s: %s" % (w("blueprint_file_missing"), args.file))
            return 2
        try:
            with open(args.file, encoding="utf-8") as fh:
                data = json.load(fh)
            bpmod.import_payload(bp, data)
            bpmod.rebuild(bp, bank)
            changed = True
        except (ValueError, json.JSONDecodeError) as e:
            print("%s: %s" % (w("blueprint_bad_file"), e))
            return 2
        print("%s: %s" % (w("blueprint_imported"), args.file))
        if bp["structure"]:
            line = bpmod.structure_line(bp["structure"], w.zh)
            if line:
                print("%s: %s" % (w("blueprint_structure"), line))
    if args.qmap:
        overrides = bp.setdefault("overrides", {})
        for pair in args.qmap:
            if ":" not in pair:
                print("忽略无效覆盖: %s (应为 qid:kc1+kc2)" % pair)
                continue
            qid, kcs = pair.split(":", 1)
            kcs = [k.strip() for k in kcs.split("+") if k.strip()]
            if qid not in {q["id"] for q in bank} or any(k not in {kc["id"] for kc in bp.get("kcs", [])} for k in kcs):
                raise ValueError("qmap 必须指向当前题库与已导入词典中的知识点；请先检查qid和KC id")
            overrides[qid] = kcs
        bpmod.rebuild(bp, bank)
        changed = True
    if args.rebuild:
        bpmod.rebuild(bp, bank)
        changed = True
        print(w("blueprint_rebuilt"))
    if changed:
        bpmod.save(ws, bp)
    # show
    print("=== %s ===" % w("blueprint_head"))
    if not bp.get("kcs"):
        print(w("blueprint_none"))
        print(footer(state, w, "python coach.py quiz --stratified" if _stage(state) == "diagnosing" else "python coach.py gaps"))
        return 0
    if state.get("exam_id"):
        print("exam: %s | course: %s" % (state["exam_id"], state["course"]))
    if bp.get("structure"):
        line = bpmod.structure_line(bp["structure"], w.zh)
        if line:
            print("%s: %s" % (w("blueprint_structure"), line))
    else:
        print("%s: %s" % (w("blueprint_structure"), w("blueprint_structure_unknown")))
    kcs = bp["kcs"]
    by_ch = {}
    for kc in kcs:
        by_ch.setdefault(kc.get("chapter"), []).append(kc)
    print("%s: %d（%d 章%s）" % (
        w("blueprint_kcs"), len(kcs), len(by_ch),
        " + 题库补充" if any(kc.get("source") == "bank" for kc in kcs) else ""))
    if args.kcs:
        for ch in sorted(by_ch, key=lambda c: (c is None, c)):
            print("  ch%s:" % ch)
            for kc in by_ch[ch]:
                src = " [题库补充]" if kc.get("source") == "bank" else ""
                print("    %-24s %s%s" % (kc["id"], kc["title"], src))
    cov = bpmod.coverage(bank, bp.get("q_map") or {})
    pct = (100.0 * cov["mapped"] / cov["total"]) if cov["total"] else 0
    print("%s: %d/%d 题（%.0f%%）" % (w("blueprint_coverage"), cov["mapped"], cov["total"], pct))
    if cov["unmapped"]:
        print("%s: %s" % (w("blueprint_unmapped"), ", ".join(cov["unmapped"][:12]) + (" …" if len(cov["unmapped"]) > 12 else "")))
    print(footer(state, w, "python coach.py quiz --stratified" if _stage(state) == "diagnosing" else "python coach.py gaps"))
    return 0


def _legacy_gaps(args):
    """Knowledge-component ability table: tested / independent-correct / gaps / untested."""
    ws, state, w = load_ws(args)
    if _stage(state) == "diagnosing":
        _gate_study(state, w)
        return 4
    bank = load_bank(ws)
    bp = bpmod.load(ws)
    rows, mode = bpmod.kc_stats(state, bank, bp, chapter=args.chapter)
    print("=== %s｜%s ===" % (w("gaps_head"), "知识点 × 题型" if mode == "kc" else "按章暂代"))
    print("已测 %d 道；未测不是零分，单题答对也不能推算考试得分概率。" %
          len({h["qid"] for h in state.get("history", [])
               if h.get("qid") in {q["id"] for q in bank} and h.get("result") in ("right", "wrong", "skip")}))
    print(w("gaps_unmapped_note") if mode == "kc" else w("gaps_fallback"))
    # Red/amber/gray describe latest evidence, not percent mastery. Confirmed
    # KC marks break ties; unknown marks stay unknown, not zero.
    confirmed = bpmod.confirmed_kc_points(bp)
    order = {"gap": 0, "method_pending": 1, "weak": 2, "untested": 3, "medium": 4, "retention": 5, "variation": 6, "strong": 7}
    priority = sorted(rows, key=lambda r: (order.get(r["strength"], 5),
                                             -confirmed.get(r["kc_id"], 0),
                                             -r.get("wrong", 0), str(r["kc_id"])))
    show = priority if args.detail else priority[:3]
    print("模块 | 最近证据 | 已测/题库 | 说明")
    print("--- | --- | --- | ---")
    for r in show:
        label = shorten(r["title"], 26).replace("|", "/")
        status = bpmod.strength_label(r["strength"], w.zh)
        print("%s | %s | %d/%d | 错/跳 %d、独立对 %d、未测 %d" % (
            label, status, r["tested"], r["total"], r["wrong"], r["indep_right"], r["untested"]))
    if len(priority) > len(show):
        print("其余 %d 个模块见 gaps --detail 或可视化文件。" % (len(priority) - len(show)))
    pending_manual = sum(1 for p in (state.get("pending") or {}).values() if p.get("status") == "awaiting_manual")
    if pending_manual:
        print("%d 道主观题待依据参考答案核对；暂不纳入已测能力。" % pending_manual)
    if not rows:
        print("尚无可分析的材料题；核对考试范围与材料后再生成计划。")
    if not args.no_html:
        path = os.path.abspath(args.html or os.path.join(ws, "capability.html"))
        ability_view.write_html(path, state, bank, bp, rows=rows, mode=mode)
        print("文件 | 内容 | 用途")
        print("--- | --- | ---")
        print("%s | 离线知识模块×题型热图、六模块概览及来源表 | 核对误标并确定先补模块（浏览器打开）" % path.replace("|", "/"))
    if _stage(state) == "analysis":
        state["workflow"]["stage"] = "planning"
        st.save(ws, state)
    print(footer(state, w, "python coach.py plan"))
    return 0


def cmd_usage(args):
    """Attribution report: where did tool calls / credits go this week."""
    ws, state, w = load_ws(args)
    log_path = usemod.find_log(args.log)
    print("=== %s ===" % w("usage_head"))
    if state.get("exam_id"):
        print("exam: %s | course: %s" % (state["exam_id"], state["course"]))
    if log_path is None:
        print(w("usage_log_missing"))
        return 2
    sessions = usemod.load_log(log_path)
    if sessions is None:
        print(w("usage_log_bad"))
        print("  %s: %s" % (w("usage_source"), log_path))
        return 2
    rep = usemod.summarize(sessions, args.days)
    print("%s: %s" % (w("usage_source"), log_path))
    print("%s: %s（%d %s）" % (
        w("usage_range"), rep["window"],
        rep["sessions_nonempty"], w("usage_sessions")))
    empty = rep["sessions_total"] - rep["sessions_nonempty"]
    print("%s: %d %s（%s: %d）" % (
        w("usage_calls"), rep["calls_total"],
        ("累计" if w.zh else "total"),
        w("usage_empty_sessions"), empty))
    print("")
    print(w("usage_by_day") + ":")
    for day in sorted(rep["by_day"]):
        d = rep["by_day"][day]
        if d["calls"] == 0:
            continue  # empty-session days are already counted in the overview
        bar = "█" * min(30, d["calls"])
        print("  %s  %s  %3d %s / %d %s" % (
            day, bar, d["calls"], w("usage_calls"), d["sessions"], w("usage_sessions")))
    if not any(rep["by_day"][d]["calls"] for d in rep["by_day"]):
        print("  (%s)" % ("窗口内没有工具调用" if w.zh else "no calls in the window"))
    print("")
    if rep["heaviest"]:
        print(w("usage_heaviest") + ":")
        for s in rep["heaviest"]:
            print("  %s  %s  %d %s" % (
                s["session_id"][:20], s["day"], s["total_calls"], w("usage_calls")))
        print("")
    print(w("usage_ocr") + ":")
    if args.ocr_dir:
        n_imgs, files = usemod.estimate_ocr(args.ocr_dir)
        for d in args.ocr_dir:
            if os.path.isdir(d):
                print("  %s: %s" % (w("usage_ocr_dir"), d))
        if n_imgs:
            print("  %d %s：%s" % (
                n_imgs, ("张本地渲染图" if w.zh else "locally rendered images"),
                w("usage_ocr_images")))
        else:
            print("  (%s)" % ("目录里没有渲染图" if w.zh else "no images found"))
    else:
        print("  " + w("usage_ocr_none"))
    print("")
    print("⚠️ " + w("usage_note_1"))
    print("⚠️ " + w("usage_note_2"))
    print("💡 " + w("usage_note_3"))
    print(footer(state, w, "python coach.py status"))
    return 0


def cmd_next(args):
    from . import runtime
    return runtime.next_step(args)


def cmd_gaps(args):
    from . import runtime
    return runtime.gaps(args)


def cmd_clarify(args):
    from . import runtime
    return runtime.clarify(args)


def cmd_skip(args):
    from . import runtime
    return runtime.skip(args)


def cmd_diagnose(args):
    from . import runtime
    return runtime.diagnose(args)


def cmd_session(args):
    from . import runtime
    return runtime.session(args)


def cmd_resume(args):
    from . import runtime
    return runtime.resume(args)


def cmd_task(args):
    from . import runtime
    return runtime.task_command(args)


def cmd_attempts(args):
    from . import runtime
    return runtime.attempts_command(args)


def cmd_verify_transfer(args):
    from . import runtime
    return runtime.verify_transfer(args)


def cmd_workbench(args):
    from . import runtime
    return runtime.workbench(args)


def cmd_import_answer(args):
    from . import runtime
    return runtime.import_answer(args)


def cmd_rubric(args):
    from . import runtime
    return runtime.rubric_command(args)


def cmd_verify_reason(args):
    from . import runtime
    return runtime.verify_reason(args)


def cmd_help(args):
    ws = resolve_workspace(args.workspace)
    state = st.load(ws) if ws else None
    zh = (state or {}).get("language") == "zh"
    print(HELP_ZH if zh else HELP_EN)
    return 0


# ------------------------------------------------------------------ parser

def build_parser():
    p = argparse.ArgumentParser(prog="coach.py", description="CrushExam", add_help=True)
    p.add_argument("--workspace", "-w", help="study workspace (default: active exam workspace)")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("setup")
    s.add_argument("materials")
    s.add_argument("--exam", help="exam ID (e.g. math_202701_final)")
    s.add_argument("--type", choices=list(exammod.EXAM_TYPES))
    s.add_argument("--date", help="exam date in YYYY-MM-DD format")
    s.add_argument("--goal", choices=list(exammod.GOALS), help="pass|high|long (defaults to pass for a new exam)")
    s.add_argument("--minutes", type=int, help="confirmed available study minutes per day")
    s.add_argument("--weekly-hours", type=float, help="confirmed available hours per week")
    s.add_argument("--lang", choices=["zh", "en"])
    s.add_argument("--days", type=int)
    s.add_argument("--name")
    s.add_argument("--start", type=int)
    s.add_argument("--slice", type=int, help="characters per teaching slice (smaller for small models)")
    s.add_argument("--fresh", action="store_true", help="discard previous progress")
    s.add_argument("--scope", help="confirmed exam scope, comma-separated (e.g. 'ch1-3,排序,树')")
    s.add_argument("--confirm-scope", action="store_true", help="mark --scope as confirmed by the student against the exam notice")
    s.add_argument("--question-types", help="question types, comma-separated (e.g. '选择题,简答题,编程题')")
    s.set_defaults(fn=cmd_setup)

    sub.add_parser("exams").set_defaults(fn=cmd_exams)

    s = sub.add_parser("switch")
    s.add_argument("exam_id")
    s.set_defaults(fn=cmd_switch)

    s = sub.add_parser("status")
    s.add_argument("--detail", action="store_true", help="all chapters")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("next")
    s.add_argument("--repeat", action="store_true")
    s.add_argument("--back", action="store_true")
    s.add_argument("--chars", type=int)
    s.set_defaults(fn=cmd_next)

    s = sub.add_parser("chapter")
    s.add_argument("n", type=int)
    s.add_argument("--part", type=int)
    s.add_argument("--chars", type=int)
    s.set_defaults(fn=cmd_chapter)

    s = sub.add_parser("goto")
    s.add_argument("n", type=int)
    s.add_argument("--restart", action="store_true")
    s.set_defaults(fn=cmd_goto)

    s = sub.add_parser("ask")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--chapter", type=int)
    s.add_argument("--chars", type=int, default=700)
    s.set_defaults(fn=cmd_ask)

    s = sub.add_parser("quiz")
    s.add_argument("-n", type=int, default=4)
    s.add_argument("--qid", help="show a specific source question; repeats resume the same unresolved attempt")
    s.add_argument("--outside-scope", action="store_true", help="explicit extra practice outside the confirmed exam scope")
    s.add_argument("--chapter", type=int)
    s.add_argument("--all", action="store_true")
    s.add_argument("--stratified", action="store_true", help="分层抽样：按章题量加权，覆盖多章，优先未测题（诊断用）")
    s.set_defaults(fn=cmd_quiz)

    s = sub.add_parser("submit")
    s.add_argument("qid")
    s.add_argument("response", help="the student's raw answer, recorded before revealing")
    s.add_argument("--hinted", action="store_true", help="the student used a hint before answering")
    s.add_argument("--confidence", choices=["low", "medium", "high"], help="self-reported confidence; not an exam score")
    s.add_argument("--minutes-spent", type=float, help="observed minutes spent on this item")
    s.add_argument("--attempt", help="optional expected immutable attempt id")
    s.set_defaults(fn=cmd_submit)

    s = sub.add_parser("check")
    s.add_argument("qid")
    s.add_argument("--force", action="store_true", help="legacy accepted flag; does NOT bypass diagnosis or answer-first guards")
    s.add_argument("--attempt", help="specific historical attempt")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("answer")
    s.add_argument("qid")
    s.add_argument("result", choices=["right", "wrong", "skip"])
    s.add_argument("--independent", action="store_true", help="student answered without hints/solution")
    s.add_argument("--note")
    s.add_argument("--attempt", help="expected immutable attempt id")
    s.add_argument("--rubric", help="source-grounded step assessment JSON; no invented point weights")
    s.add_argument("--error-type", choices=list(taskmod.ERROR_ACTIONS), help="observed error category, not an inferred diagnosis")
    s.add_argument("--transfer-from", help="base source item, only after verify-transfer")
    s.set_defaults(fn=cmd_answer)

    s = sub.add_parser("grade")
    s.add_argument("qid")
    s.add_argument("response", nargs="?", help="optional compatibility echo; must exactly match the frozen submit")
    s.add_argument("--independent", action="store_true", help="student answered without hints/solution")
    s.add_argument("--note", help="error cause or comment")
    s.add_argument("--attempt", help="expected immutable attempt id")
    s.add_argument("--rubric", help="source-grounded step assessment JSON; no invented point weights")
    s.add_argument("--error-type", choices=list(taskmod.ERROR_ACTIONS), help="observed error category, not an inferred diagnosis")
    s.add_argument("--transfer-from", help="base source item, only after verify-transfer")
    s.set_defaults(fn=cmd_grade)

    s = sub.add_parser("review")
    s.add_argument("qid")
    s.add_argument("--result", choices=["right", "wrong"], required=True)
    s.add_argument("--attempt", help="expected immutable attempt id")
    s.add_argument("--rubric", help="source-grounded step assessment JSON; no invented point weights")
    s.add_argument("--error-type", choices=list(taskmod.ERROR_ACTIONS), help="observed error category, not an inferred diagnosis")
    s.add_argument("--transfer-from", help="base source item, only after verify-transfer")
    s.add_argument("--note", help="manual grading basis for a subjective re-test")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("evidence")
    s.add_argument("--chapter", type=int)
    s.set_defaults(fn=cmd_evidence)

    s = sub.add_parser("score")
    s.add_argument("--score", type=float, help="real exam score (self-reported)")
    s.add_argument("--max", type=float, help="max possible score (default 100)")
    s.add_argument("--date", help="date of the exam (YYYY-MM-DD, default today)")
    s.add_argument("--note", help="optional note (e.g. pass/fail, grade)")
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("done")
    s.add_argument("--chapter", type=int)
    s.add_argument("--unverified", action="store_true", help="explicitly defer an unlearned/material-blocked chapter")
    s.set_defaults(fn=cmd_done)

    s = sub.add_parser("note")
    s.add_argument("text")
    s.add_argument("--type", choices=["summary", "confusion", "note"], default="note")
    s.add_argument("--chapter", type=int)
    s.set_defaults(fn=cmd_note)

    s = sub.add_parser("mistakes")
    s.add_argument("--chapter", type=int)
    s.add_argument("--answers", action="store_true")
    s.add_argument("--all-exams", action="store_true", help="show mistakes across all exams")
    s.set_defaults(fn=cmd_mistakes)

    s = sub.add_parser("cheatsheet")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_cheatsheet)

    s = sub.add_parser("figures")
    s.add_argument("--chapter", type=int)
    s.add_argument("--file")
    s.add_argument("--page", type=int)
    s.set_defaults(fn=cmd_figures)

    s = sub.add_parser("figure")
    s.add_argument("file")
    s.add_argument("page", type=int)
    s.add_argument("--crop", help="x0,y0,x1,y1 as 0-1 fractions of the page (top-left origin) or PDF points")
    s.add_argument("--scale", type=float, default=2.0)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_figure)

    s = sub.add_parser("plan")
    s.add_argument("--days", type=int)
    s.add_argument("--date", help="set the exam date in YYYY-MM-DD format")
    s.add_argument("--goal", choices=list(exammod.GOALS), help="override the study goal (pass|high|long)")
    s.add_argument("--weekly-hours", type=float, help="confirmed available hours per week")
    s.add_argument("--minutes", type=int, help="confirmed available minutes per day")
    s.add_argument("--detail", action="store_true", help="show more of the multi-day plan")
    s.add_argument("--skip-diagnosis", action="store_true", help="explicitly proceed without ability evidence")
    s.add_argument("--rebuild", action="store_true", help="archive previous tasks and recalculate, only with no active attempt")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("export")
    s.add_argument("paths", nargs="*")
    s.add_argument("--to", default="exam-cram-figures")
    s.add_argument("--qid", nargs="*")
    s.add_argument("--chapter", type=int)
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("blueprint")
    s.add_argument("--file", help="导入 KC 词典 JSON（对象或列表，可含 structure 与 kcs）")
    s.add_argument("--qmap", nargs="*", help="手动修正映射：qid:kc1+kc2（重建时保留）")
    s.add_argument("--rebuild", action="store_true", help="按当前题库重建映射")
    s.add_argument("--kcs", action="store_true", help="列出全部知识点")
    s.set_defaults(fn=cmd_blueprint)

    s = sub.add_parser("gaps")
    s.add_argument("--chapter", type=int, help="只看某一章的知识点")
    s.add_argument("--detail", action="store_true", help="list all module rows")
    s.add_argument("--html", nargs="?", const="", help="offline capability HTML (default: workspace/capability.html)")
    s.add_argument("--no-html", action="store_true", help="skip offline capability HTML")
    s.set_defaults(fn=cmd_gaps)

    s = sub.add_parser("usage")
    s.add_argument("--log", help=".tool-usage-log.json 路径（默认自动探测）")
    s.add_argument("--ocr-dir", nargs="*", help="已渲染图片所在目录，仅统计缓存文件数")
    s.add_argument("--days", type=int, help="只看最近 N 天（默认全部）")
    s.set_defaults(fn=cmd_usage)

    s = sub.add_parser("clarify")
    s.add_argument("qid")
    s.add_argument("response")
    s.set_defaults(fn=cmd_clarify)

    for command in ("skip", "defer"):
        s = sub.add_parser(command)
        s.add_argument("qid", nargs="?")
        s.add_argument("--reason", choices=["user_choice", "unable", "material_missing", "later"], default="user_choice")
        s.add_argument("--note")
        s.set_defaults(fn=cmd_skip)

    sub.add_parser("resume").set_defaults(fn=cmd_resume)
    s = sub.add_parser("diagnose")
    s.add_argument("--restart", action="store_true")
    s.add_argument("--cancel-current", action="store_true")
    s.add_argument("-n", type=int, default=4)
    s.set_defaults(fn=cmd_diagnose)

    s = sub.add_parser("session")
    s.add_argument("action", choices=["pause", "resume", "finish", "summary", "recover"], default="summary", nargs="?")
    s.set_defaults(fn=cmd_session)

    s = sub.add_parser("task")
    s.add_argument("action", choices=["show", "note", "assess", "skip-check", "finish"], default="show", nargs="?")
    s.add_argument("--status", choices=["needs_work", "deferred", "material_blocked", "completed_unverified"], default="needs_work")
    s.add_argument("--note")
    s.add_argument("--json", action="store_true")
    s.add_argument('--step-id')
    s.add_argument('--verdict', choices=['met', 'partial', 'incorrect', 'uncertain'])
    s.add_argument('--quote')
    s.add_argument('--reference-quote')
    s.set_defaults(fn=cmd_task)

    s = sub.add_parser("attempts")
    s.add_argument("--qid")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_attempts)

    s = sub.add_parser("verify-transfer")
    s.add_argument("qid")
    s.add_argument("base_qid")
    s.add_argument("--kc", required=True)
    s.add_argument("--basis", required=True)
    s.add_argument("--confirmed", action="store_true")
    s.add_argument('--kind', choices=['parameter', 'representation', 'context', 'unclassified'], default='unclassified')
    s.set_defaults(fn=cmd_verify_transfer)

    s = sub.add_parser('rubric')
    s.add_argument('action', choices=['draft', 'freeze', 'ratings'])
    s.add_argument('qid')
    s.add_argument('--out')
    s.add_argument('--file')
    s.add_argument('--attempt')
    s.set_defaults(fn=cmd_rubric)

    s = sub.add_parser('verify-reason')
    s.add_argument('qid')
    s.add_argument('--attempt')
    s.add_argument('--verdict', choices=['met', 'incorrect', 'uncertain'], required=True)
    s.add_argument('--quote', required=True)
    s.add_argument('--reference-quote', required=True)
    s.add_argument('--note', required=True)
    s.set_defaults(fn=cmd_verify_reason)

    s = sub.add_parser("workbench")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_workbench)
    s = sub.add_parser("import-answer")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import_answer)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("help").set_defaults(fn=cmd_help)
    return p


def main(argv=None):
    from .workspace_lock import locked
    parser = build_parser()
    args = parser.parse_args(argv)
    _SHOWN.clear()
    if not getattr(args, "fn", None):
        return cmd_help(args)
    try:
        # Reject invalid numeric/date inputs before touching files.
        for field in ("date",):
            value = getattr(args, field, None)
            if value:
                _dt.date.fromisoformat(value)
        if getattr(args, "chars", None) is not None and not 1 <= args.chars <= 100000:
            raise ValueError("--chars must be 1..100000")
        if getattr(args, "slice", None) is not None and not 1 <= args.slice <= 100000:
            raise ValueError("--slice must be 1..100000")
        if getattr(args, "minutes", None) is not None and not 1 <= args.minutes <= 1440:
            raise ValueError("--minutes must be 1..1440")
        if getattr(args, "weekly_hours", None) is not None and not 0 < args.weekly_hours <= 168:
            raise ValueError("--weekly-hours must be greater than 0 and no more than 168")
        if getattr(args, "days", None) is not None and args.days < 0:
            raise ValueError("--days must not be negative")
        if args.cmd == "setup":
            if not os.path.isdir(args.materials):
                raise ValueError("materials folder not found")
            base = os.path.abspath(args.materials)
            root_state = st.load(os.path.join(base, "exam-cram"))
            eid = args.exam or (root_state or {}).get("exam_id") or "exam_" + _dt.datetime.now().strftime("%Y%m%d%H%M%S")
            args.exam = eid
            ws = exammod.suggest_workspace(base, eid, workspace=args.workspace)
            with locked(ws):
                # Do not re-resolve to a different unprotected workspace after acquiring the lock.
                args.workspace = ws
                return args.fn(args)
        ws = resolve_workspace(args.workspace)
        if not ws:
            if args.cmd in ("help", "doctor", "exams", "switch"):
                return args.fn(args)
            print(_T["no_ws"][0])
            return 2
        with locked(ws):
            state = st.load(ws)
            denial = wf.denied(state, args)
            if denial:
                print(denial[0])
                print(footer(state, W(state["language"]), wf.next_command(state)))
                return denial[1]
            active = at.active(state)
            # A request for help during a practice item is allowed but must
            # be recorded as assistance, never as an independent attempt.
            if active and args.cmd in ("ask", "chapter", "figure", "figures", "export", "cheatsheet"):
                at.expose(state, active["qid"], "hint", active["id"])
                st.save(ws, state)
            if args.cmd == "mistakes" and getattr(args, "answers", False):
                if active and active["status"] in ("presented", "needs_clarification"):
                    print("当前题尚未提交，先作答或暂缓；错题答案不能绕过先交后查。")
                    return 5
                for m in st.open_mistakes(state, args.chapter):
                    at.expose(state, m["qid"], "solution")
                st.save(ws, state)
            return args.fn(args)
    except TimeoutError as exc:
        print(str(exc))
        return 6
    except at.AttemptError as exc:
        print(str(exc))
        return 4
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("操作未完成：%s。原记录未被默认重置；可用 doctor 检查。" % exc)
        return 2
