# -*- coding: utf-8 -*-
"""Student workflow controller. Heavy extraction stays in the original modules.

The state machine, immutable attempts and task ledger are shared by CLI and the
optional offline workbench. There is no second frontend grading authority.
"""
import argparse
import copy
import datetime as dt
import json
import os
import uuid
from pathlib import Path

from . import attempts as at, blueprint as bp, evidence, exams, grading, material_safety as safety
from . import planner, questions, state as st, tasks, workflow as wf, assessment


def _cli():
    from . import cli
    return cli


def load(args):
    ws, state, wording = _cli().load_ws(args)
    wf.ensure(state)
    return ws, state, wording


def _save(ws, state):
    at.sync(state)
    tasks.refresh(state)
    st.save(ws, state)


def _foot(state, w, action=None):
    print(_cli().footer(state, w, action))


def _q(ws, qid):
    q = _cli()._find_q(_cli().load_bank(ws), qid)
    if not q:
        raise at.AttemptError("找不到题目：%s。若重建了题库，旧原答仍保留，请恢复或暂缓旧任务。" % qid)
    return q


def _exam(state):
    return exams.get_exam(state.get("exam_id")) if state.get("exam_id") else None


def _eligible(ws, state, outside_scope=False):
    bank = _cli().load_bank(ws)
    return bank if outside_scope else bp.eligible_questions(state, bank, bp.load(ws), _exam(state))


def _available(ws, state, bank):
    return [q for q in bank if not safety.readiness(q, ws) and not at.eligibility_reason(state, q["id"])
            and not at.lookup(state, q["id"], unresolved=True)]


def _show(ws, state, w, a):
    q = _q(ws, a["qid"])
    at.verify_version(a, q)
    if a["status"] in ("submitted", "awaiting_manual"):
        print("本题原答已保存，等待核对；再次查看不会覆盖原答或新增尝试。")
    elif a["status"] == "needs_clarification":
        print("原答保留，但格式待澄清。请用 clarify 补充明确选项，也可跳过。")
    _cli()._print_question(q, w, ws)
    print("作答编号：%s" % a["id"])
    _cli()._remember_shown(ws, state)
    _foot(state, w, wf.next_command(state))
    return 0


def _pick(state, bank, n, count, include_all):
    """Bounded ordering shared with legacy _pick_quiz consumers."""
    pool = [q for q in bank if (include_all or q.get("chapter") == n)
            and not at.eligibility_reason(state, q["id"])]
    last = {h["qid"]: h for h in state.get("history", [])}
    review = {m["qid"]: m.get("next_review_date") for m in state.get("mistakes", [])}
    def rank(q):
        qid = q["id"]
        h = last.get(qid)
        today = bool(h and h.get("ts", "")[:10] == st.today())
        due = review.get(qid)
        # Do not starve untouched items with a same-day wrong-item loop.
        return (0 if due and due <= st.today() and not today else
                1 if not h else 2 if h.get("result") == "wrong" and not today else 3,
                today, q.get("seq", 999999), qid)
    return sorted(pool, key=rank)[:count]


def quiz(args):
    ws, state, w = load(args)
    a = at.active(state)
    if a:
        if getattr(args, "qid", None) and args.qid != a["qid"]:
            print("已有当前题。请先提交、暂缓或跳过，不能静默切题。")
            _foot(state, w, wf.next_command(state))
            return 4
        return _show(ws, state, w, a)
    flow = state["workflow"]
    bank = _eligible(ws, state, getattr(args, "outside_scope", False))
    if flow["stage"] == "diagnosing":
        if not flow.get("diagnostic_ids"):
            available = _available(ws, state, bank)
            picked = bp.stratified_pick(state, available, max(1, min(args.n, 8)), bp=bp.load(ws), exam=_exam(state))
            wf.begin_diagnosis(state, [q["id"] for q in picked])
            flow = state["workflow"]
            if len(available) < len(bank):
                print("%d 道原题暂不用于摸底：题干/配图待核对或今日已达次数上限。" % (len(bank) - len(available)))
        # Rebuilt/edited banks cannot leave dangling diagnosis IDs forever.
        full_bank = {q["id"]: q for q in _cli().load_bank(ws)}
        for qid in list(wf.remaining(state)):
            candidate = full_bank.get(qid)
            reason = safety.readiness(candidate, ws) if candidate else "missing_item"
            if reason or qid in state.get("question_blocks", {}):
                wf.diagnostic_done(state, qid, "material_blocked")
                print("摸底题 %s 因资料不完整暂缓，不记为答错。" % qid)
        remaining = wf.remaining(state)
        if not remaining:
            flow["stage"] = "analysis"
            _save(ws, state)
            print("本轮可用题已完成；未测、资料阻塞和待人工核对分别保留。")
            _foot(state, w, "python coach.py gaps")
            return 0
        if getattr(args, "qid", None) and args.qid != remaining[0]:
            raise at.AttemptError("本轮按已冻结的摸底题序推进；不能直接替换其中一道。")
        q = full_bank[remaining[0]]
        a, _ = at.present(state, q, purpose="diagnosis")
        print("=== 摸底 %d/%d：先作答，整轮后统一分析 ===" % (
            len(flow["diagnostic_submitted"]) + 1, len(flow["diagnostic_ids"])))
        print("选题依据：确认范围、题型/章节覆盖、未测优先；难度和分值只使用已核对来源，不估个人得分概率。")
    else:
        if at.practice_break(state):
            print("连续错误已触发暂停刷题。先 next 补讲关键步骤，或结束本次；不会反复出错题。")
            _foot(state, w, "python coach.py next")
            return 4
        task = tasks.current(state)
        if task and task['phase'] in tasks.WAIT_PHASES:
            print('当前步骤尚未核对；先 task note / task assess，或按学生明确意图 task skip-check --note 原因；也可结束任务。')
            _foot(state, w, wf.next_command(state))
            return 4
        if getattr(args, "qid", None):
            q = next((q for q in bank if q["id"] == args.qid), None)
            if not q:
                raise at.AttemptError("该题不在已确认考试范围内或不存在；课外自选题须显式 --outside-scope。")
            reason = safety.readiness(q, ws) or at.eligibility_reason(state, q["id"])
            if reason:
                print("该题暂不可测：%s。可查看原资料、修复题目或换题。" % reason)
                return 4
            old = at.lookup(state, q["id"], unresolved=True)
            if old:
                state["active_attempt_id"] = old["id"]
                _save(ws, state)
                return _show(ws, state, w, old)
            if task and q["id"] not in task["qids"]:
                task = None  # explicit extra exercise must not complete another task
        elif task and not getattr(args, "all", False) and not getattr(args, "chapter", None):
            tasks.activate(state, task)
            ids = task["remaining_qids"]
            available = _available(ws, state, [q for q in bank if q["id"] in ids])
            guided = set(task.get("guided_qids", []))
            available.sort(key=lambda q: (q["id"] in guided, any(h["qid"] == q["id"] for h in state.get("history", [])), q.get("seq", 0)))
            q = available[0] if available else None
            if not q:
                tasks.finish(state, task, "material_blocked" if not ids else "needs_work",
                             "暂无本任务可独立验证的原题；不自动生成新题、不假定掌握。")
                _save(ws, state)
                print("当前任务已收束为待巩固/资料待补；其余任务可继续。")
                _foot(state, w, "python coach.py task")
                return 0
        else:
            available = _available(ws, state, bank)
            picked = _pick(state, available, getattr(args, "chapter", None) or state.get("current"), 1,
                           getattr(args, "all", False) or getattr(args, "stratified", False))
            q = picked[0] if picked else None
            if task and q and q["id"] not in task["qids"]:
                task = None
        if not q:
            print("没有可用原题：可能已超出范围、题目待补或今日次数已满。可补讲、暂缓或结束本次。")
            _foot(state, w, "python coach.py session finish")
            return 3
        if task:
            tasks.activate(state, task)
            task["phase"] = "independent"
        a, _ = at.present(state, q, task["id"] if task else None,
                          "review" if task and task["kind"] in ("due_review", "mistake_review") else "practice")
        a["outside_scope"] = bool(getattr(args, "outside_scope", False))
        print("=== %s｜只做当前这一题 ===" % ("到期/错题复测" if a["purpose"] == "review" else "资料原题练习"))
    _save(ws, state)
    return _show(ws, state, w, a)


def _after_submission(ws, state, w, a, q):
    if a["status"] == "needs_clarification":
        print("原答已保存但无法解析；请澄清选项/对错，也可 skip。此次不记为答错。")
        _save(ws, state)
        _foot(state, w, wf.next_command(state))
        return 0
    if state["workflow"]["stage"] == "diagnosing":
        verdict = grading.grade(a.get("graded_response", a["raw_answer"]), q.get("answer") or "")
        if verdict["verdict"] in ("right", "wrong", "partial"):
            result = "right" if verdict["verdict"] == "right" else "wrong"
            at.record(state, a, q, result, "reference_auto", note="摸底原答")
            outcome = "graded"
        elif verdict["kind"] == "none":
            at.close(state, a, "unverified", "材料未提供可靠答案")
            outcome = "missing_reference"
        else:
            at.park(state, a)
            outcome = "awaiting_manual"
        wf.diagnostic_done(state, q["id"], outcome)
        print("已记录原答。先完成整轮摸底，再统一分析；此处不揭晓解析。")
    else:
        print("原答已冻结保存。下一步核对；修改不会覆盖这次提交。")
    _save(ws, state)
    _foot(state, w, wf.next_command(state))
    return 0


def submit(args):
    ws, state, w = load(args)
    q = _q(ws, args.qid)
    a = at.lookup(state, args.qid, getattr(args, "attempt", None))
    if not a:
        raise at.AttemptError("先 quiz 呈现本题，再提交学生真实原答。")
    if at.active(state) and at.active(state)["id"] != a["id"]:
        raise at.AttemptError("不能向另一道旧题提交；先结束当前作答。")
    changed = at.submit(state, a, q, args.response, args.hinted, args.confidence, args.minutes_spent)
    if not changed:
        print("相同提交已保存；本次重试未新增记录。")
        _foot(state, w, wf.next_command(state))
        return 0
    return _after_submission(ws, state, w, a, q)


def clarify(args):
    ws, state, w = load(args)
    q = _q(ws, args.qid)
    a = at.lookup(state, args.qid, unresolved=True)
    if not a:
        raise at.AttemptError("没有待澄清的作答。")
    at.clarify(state, a, q, args.response)
    return _after_submission(ws, state, w, a, q)


def skip(args):
    ws, state, w = load(args)
    a = at.lookup(state, getattr(args, "qid", None), unresolved=True) if getattr(args, "qid", None) else at.active(state)
    if not a:
        print("没有未结束的当前题。")
        return 0
    reason = getattr(args, "reason", "user_choice")
    status = "material_blocked" if reason == "material_missing" else "deferred" if args.cmd == "defer" else "skipped"
    at.close(state, a, status, getattr(args, "note", None) or reason)
    wf.diagnostic_done(state, a["qid"], status)
    tasks.on_closed_attempt(state, a)
    _save(ws, state)
    print("已%s：不记为答错、不产生掌握证据，原答如已提交仍保留。" % ("暂缓" if status == "deferred" else "挂起缺材料题" if status == "material_blocked" else "跳过"))
    _foot(state, w, wf.next_command(state))
    return 0


def check(args):
    ws, state, w = load(args)
    q = _q(ws, args.qid)
    a = at.lookup(state, args.qid, getattr(args, "attempt", None))
    if not a or a["status"] in ("presented", "needs_clarification"):
        print("先提交可判定的原答，再查看解析；--force 不绕过此约束。")
        _foot(state, w, wf.next_command(state))
        return 5
    at.expose(state, q["id"], "solution", a["id"])
    _save(ws, state)
    _cli()._print_question(q, w, ws, with_answer=True)
    _cli()._remember_shown(ws, state)
    print("提交后的解析不会改变这次原答的独立性；今天再次做同题会标记为受助。")
    _foot(state, w, "python coach.py grade %s" % q["id"] if a["status"] != "graded" else None)
    return 0


def _validate_rubric(path, q, a):
    return assessment.assess(assessment.read_json(path), q, a)


def _transfer(ws, state, a, q, base_id):
    if not base_id:
        return False
    link = (state.get("transfer_links") or {}).get(q["id"])
    if not link or link.get("base_qid") != base_id:
        raise at.AttemptError("迁移关系未确认。先 verify-transfer 建立有依据的题族关系，不能将普通重做标为迁移。")
    base_q = _q(ws, base_id)
    if link.get("item_version") != questions.question_version(q) or link.get("base_version") != questions.question_version(base_q):
        raise at.AttemptError("题目已变化，旧题族关系不再有效；需依据新原题重新核对。")
    if link.get("answer_version") != questions.question_answer_version(q) or link.get("base_answer_version") != questions.question_answer_version(base_q):
        raise at.AttemptError("参考答案已变化，旧题族关系不再有效。")
    if any(old["qid"] == q["id"] and old["id"] != a["id"] and old.get("raw_answer") is not None for old in state.get("attempts", {}).values()):
        raise at.AttemptError("目标题已有原答，不是首次迁移验证；可以继续作为普通练习。")
    if any(h["qid"] == q["id"] for h in state.get("history", [])):
        raise at.AttemptError("目标题已有作答记录，不是首次独立迁移验证。")
    base = [h for h in state.get("history", []) if h["qid"] == base_id and h.get("is_independent") and h["result"] == "right"
            and h.get("ts", "") < a["presented_at"]
            and h.get("item_version") == questions.question_version(base_q)
            and h.get("answer_version") == questions.question_answer_version(base_q)]
    if not base or not at.independent(state, a):
        raise at.AttemptError("迁移需前题已有独立成功，且目标题首次无提示作答。")
    if any(e.get('qid') == q['id'] and e.get('at', '') <= a['submitted_at'] for e in state.get('exposures', [])):
        # Feedback after the current submission is allowed; earlier-day viewing is not novelty.
        raise at.AttemptError('目标题曾在提交前展示过提示/答案，不能算未见题验证；仍可普通判分。')
    latest_base = next((h for h in reversed(state.get('history', [])) if h['qid'] == base_id and h.get('ts', '') < a['presented_at']), None)
    if not latest_base or latest_base.get('result') != 'right' or not evidence.method_ready(latest_base):
        raise at.AttemptError('基题最近仍有错误或方法未核验，不能用旧成功申请迁移。')
    if not evidence.method_ready({'method_status': assessment.method_status(a, q)}):
        raise at.AttemptError('目标题方法尚未核验，先保留选项得分，不升级异题证据。')
    return copy.deepcopy(link)


def grade(args):
    ws, state, w = load(args)
    q = _q(ws, args.qid)
    a = at.lookup(state, args.qid, getattr(args, "attempt", None))
    if not a or a["status"] in ("presented", "needs_clarification"):
        raise at.AttemptError("先呈题并提交可判定原答；若格式不清，请 clarify，不能直接 grade 替换答案。")
    response_arg = getattr(args, "response", None)
    effective = a.get("graded_response", a.get("raw_answer"))
    if response_arg is not None and response_arg != effective:
        raise at.AttemptError("grade 不能覆盖已保存原答。原答保持不变；需重做时结束本次后重新呈题。")
    if a["status"] == "graded":
        print("本次作答已经判分；重复调用不会新增或改写记录。")
        _foot(state, w, None)
        return 0
    if a["status"] not in ("submitted", "awaiting_manual"):
        raise at.AttemptError("本次已跳过、暂缓或资料未核验，不能直接改为已判分。")
    auto = grading.grade(effective or "", q.get("answer") or "")
    requested = getattr(args, "result", None)
    if requested == "skip":
        args.cmd = "skip"
        args.reason = "user_choice"
        return skip(args)
    if auto["kind"] == "none":
        at.close(state, a, "unverified", "无可靠参考答案")
        tasks.on_closed_attempt(state, a)
        _save(ws, state)
        print("没有可靠参考答案：保留原答并标为未核验，不给确定对错或能力等级。")
        return 3
    rubric = _validate_rubric(args.rubric, q, a) if getattr(args, "rubric", None) else None
    if rubric and rubric.get("result") is None:
        a["rubric"] = rubric
        at.park(state, a)
        _save(ws, state)
        print("评分点未完整核对或未在作答前冻结。保留分项反馈和原答，不判整题正确。可补全已冻结评分记录，或暂缓并为新作答先冻结契约。")
        return 3
    if auto["verdict"] == "manual":
        if rubric:
            result = rubric["result"]
            if requested and result != requested:
                raise at.AttemptError("整体结果与分项评分点不一致。")
        elif requested == "wrong" and getattr(args, "note", None):
            result = requested
        else:
            at.park(state, a)
            _save(ws, state)
            print("主观题原答已保存。判整题正确必须在作答前 rubric freeze，再 grade --rubric 核对完整冻结要点；自由文本结论不能跳过覆盖检查。")
            _foot(state, w, "python coach.py check %s" % q["id"])
            return 3
        source = "reference_manual"
    elif auto["verdict"] in ("right", "wrong", "partial"):
        result = "right" if auto["verdict"] == "right" else "wrong"
        if requested and result != requested:
            raise at.AttemptError("所填结果与原答、参考答案不一致；保留原始证据。")
        source = "reference_auto"
    else:
        raise at.AttemptError("原答需澄清，不能猜测判分。")
    note = getattr(args, "note", None) or ("部分正确：" + auto.get("detail", "") if auto["verdict"] == "partial" else "")
    transfer = _transfer(ws, state, a, q, getattr(args, "transfer_from", None))
    at.record(state, a, q, result, source, note, rubric, getattr(args, "error_type", None), transfer)
    tasks.on_graded(state, a)
    # Print the key only after freezing and grading. This exposure matters to
    # any later same-day attempt, not to the one that just finished.
    at.expose(state, q["id"], "solution", a["id"])
    _save(ws, state)
    print("%s｜%s" % ("正确" if result == "right" else "部分正确" if auto["verdict"] == "partial" else "需要修正",
                       evidence.attempt_label(a, w.zh) if result == "right" else "已作答，本次尚未形成正确证据"))
    print("原答：%s" % a["raw_answer"])
    if a.get("graded_response") != a.get("raw_answer"):
        print("格式澄清：%s（首次原答未改动）" % a["graded_response"])
    print("参考依据：%s p.%s" % ((q.get("answer_source") or q["source"])["file"], (q.get("answer_source") or q["source"])["page"]))
    if auto["verdict"] != "manual":
        print("参考答案：%s" % auto.get("reference", ""))
    if rubric:
        for item in rubric["criteria"]:
            print("%s：%s" % (item["label"], {"met": "完成", "partial": "部分完成", "missing": "缺失", "uncertain": "待核对", "unassessed": "漏评待核对"}[item["status"]]))
    if note:
        print("反馈：%s" % note)
    if result == "wrong":
        print("下一教学动作：%s" % tasks.ERROR_ACTIONS.get(getattr(args, "error_type", None), tasks.ERROR_ACTIONS["unknown"]))
    if at.practice_break(state):
        print("连续错误已达上限：停止刷题，先补讲或结束本次。")
    print("本题已收束。等待你决定继续、查看任务或结束本次，不自动开启下一题。")
    _foot(state, w, None)
    return 0


def answer(args):
    return grade(args)


def review(args):
    ws, state, w = load(args)
    a = at.lookup(state, args.qid, unresolved=True)
    if not a or a["status"] not in ("submitted", "awaiting_manual"):
        raise at.AttemptError("复测必须先 quiz 呈现并 submit 新原答，不能沿用旧作答。")
    return grade(args)


def diagnose(args):
    ws, state, w = load(args)
    if at.active(state):
        if not args.cancel_current:
            raise at.AttemptError("当前还有作答。先完成/暂缓，或显式 --cancel-current 后重新摸底。")
        a = at.active(state)
        at.close(state, a, "cancelled", "用户选择重新摸底")
        tasks.on_closed_attempt(state, a)
    if state["workflow"].get("diagnostic_ids") and not args.restart:
        print("当前或最近一轮摸底已存在；重测请 diagnose --restart。")
        return 4
    available = _available(ws, state, _eligible(ws, state))
    picked = bp.stratified_pick(state, available, max(1, min(args.n, 8)), bp=bp.load(ws), exam=_exam(state))
    wf.begin_diagnosis(state, [q["id"] for q in picked], restart=args.restart)
    _save(ws, state)
    print("新摸底批次已建立；保留旧批次与全部原答。此次 %d 道可用原题。" % len(picked))
    _foot(state, w, wf.next_command(state))
    return 0


def plan(args):
    ws, state, w = load(args)
    if getattr(args, "skip_diagnosis", False):
        wf.skip_diagnosis(state)
        print("已跳过本轮剩余摸底；已提交原答保留，未测仍是未测。")
    updates = any(getattr(args, name, None) is not None for name in ("date", "days", "goal", "weekly_hours", "minutes"))
    if tasks.current(state) and not updates and not getattr(args, "rebuild", False):
        print("=== 今日计划｜继续已保存任务 ===")
        for line in tasks.card(tasks.current(state)):
            print(line)
        if args.detail:
            for i, task in enumerate(state["tasks"], 1):
                print("%d. %s｜%s｜%s｜题号 %s" % (i, task["label"], task["status"], task["phase"], ",".join(task["qids"])))
        _save(ws, state)
        _foot(state, w, "python coach.py next")
        return 0
    if at.active(state):
        raise at.AttemptError("还有未结束的当前题。先提交并核对，或 defer 后再重排计划。")
    if args.date:
        dt.date.fromisoformat(args.date)
        state["exam_date"] = args.date
    if args.days is not None:
        if args.days < 0:
            raise at.AttemptError("剩余天数不能小于0。")
        state["exam_date"] = (dt.date.today() + dt.timedelta(days=args.days)).isoformat()
        state["exam_days"] = args.days
    if args.goal:
        state["goal"] = args.goal
    if args.weekly_hours is not None:
        if not 0 < args.weekly_hours <= 168:
            raise at.AttemptError("每周学习时间应为0～168小时之间的正数。")
        state["weekly_hours"] = args.weekly_hours
    if args.minutes is not None:
        if not 1 <= args.minutes <= 1440:
            raise at.AttemptError("每日学习时间应为1～1440分钟。")
        state["study_minutes"] = args.minutes
    bank = _eligible(ws, state)
    ids = {q["id"] for q in bank}
    planning_state = copy.deepcopy(state)
    planning_state["mistakes"] = [m for m in state["mistakes"] if m["qid"] in ids and not at.eligibility_reason(state, m["qid"])]
    plans = planner.generate_plan(planning_state, exam_date=state.get("exam_date"), goal=state.get("goal"),
                                  bank=bank, bp=bp.load(ws), exam=_exam(state), weekly_hours=args.weekly_hours)
    if not plans:
        plans = [planner.DayPlan(date_str=st.today(), tasks=[])]
    tasks.install(state, plans[0], bank)
    state["workflow"]["stage"] = "planned"
    task = tasks.current(state)
    if task and task.get("chapter") is not None:
        state["current"] = task["chapter"]
    _save(ws, state)
    print("=== 今日计划｜%s ===" % {"pass": "先补关键缺口", "high": "查漏巩固", "long": "长期保持"}.get(state.get("goal"), "循证备考"))
    print("考试日期：%s；只使用确认范围与分值，不估计个人通过概率。" % (state.get("exam_date") or "未填写"))
    for line in tasks.card(task):
        print(line)
    if task:
        print("依据：%s" % task.get("why_now", ""))
    if plans[0].note:
        print("安排说明：%s" % plans[0].note)
    if args.detail:
        for line in planner.render_plan(plans, state, w.zh):
            print(line)
    elif len(state["tasks"]) > 1:
        print("另有 %d 项保存在任务队列；当前只执行第一项。" % (len(state["tasks"]) - 1))
    _foot(state, w, "python coach.py next" if task else "python coach.py session finish")
    return 0


def next_step(args):
    ws, state, w = load(args)
    a = at.active(state)
    if a:
        return _show(ws, state, w, a)
    task = tasks.current(state)
    if not task:
        if state.get("tasks"):
            print("本次计划已收束。待巩固和资料待补仍保留，不会自动循环刷题。")
            _foot(state, w, "python coach.py session finish")
            return 0
        state["support_at"] = at.stamp()
        _save(ws, state)
        return _cli()._legacy_next(args)
    tasks.activate(state, task)
    if task['phase'] in ('awaiting_step', 'step_check', 'method_check'):
        print('\n'.join(tasks.card(task)))
        if task['phase'] == 'awaiting_step':
            print('等你补一个关键步骤；重复 next 不会跳过回应。实际回应由 task note 保存。')
        elif task['phase'] == 'step_check':
            print('步骤已保存，尚未核对。先 task assess；不会将“我还不会”或单纯继续当作通过。')
        else:
            print('选项得分保留，方法尚未核验。verify-reason 只能核对首次原答；或 task skip-check 明确暂缓后换未见原题。')
        _save(ws, state)
        _foot(state, w, wf.next_command(state))
        return 0
    if task['phase'] == 'remediation':
        if task.get('guided_round', 0) >= 3:
            tasks.finish(state, task, 'needs_work', '已完成3轮小步骤支持仍未确认，本次暂停巩固，避免无限带做循环。')
            _save(ws, state)
            print('本任务已保留待巩固；可结束本次或继续其他任务。')
            return 0
        task['phase'] = 'guided'
        print('先补更小的前置步骤，保留之前的真实困惑；不直接进入独立测试。')
    if task["kind"] == "cheatsheet":
        _save(ws, state)
        rc = _cli().cmd_cheatsheet(argparse.Namespace(workspace=ws, out=None, cmd="cheatsheet"))
        state = st.load(ws)
        task = tasks.current(state)
        if task:
            tasks.finish(state, task, "completed_unverified", "已生成重点速览；阅读资料不等于验证能力。")
        _save(ws, state)
        return rc
    if at.practice_break(state):
        task["phase"] = "explain"
    if getattr(args, "repeat", False) or getattr(args, "back", False):
        task["phase"] = "explain"
    bank = _eligible(ws, state)
    by_id = {q["id"]: q for q in bank}
    if task["phase"] == "feedback":
        if task.get("needs_remediation"):
            task["phase"] = "explain"
        else:
            task["phase"] = "independent"
    if task["phase"] == "explain":
        n = task.get("chapter")
        if n is None:
            related = next((by_id[q] for q in task["qids"] if q in by_id), None)
            n = related.get("chapter") if related else None
        chs = {c.number: c for c in _cli().load_chapters(ws)}
        ch = chs.get(n)
        parts = _cli().chapter_parts(ch, args.chars or state["slice_chars"]) if ch else []
        cur = st.chapter(state, n)
        print("\n".join(tasks.card(task)))
        if parts:
            k = min((cur or {}).get("part", 0), len(parts) - 1)
            if getattr(args, "back", False):
                k = max(0, k - 1)
            print(safety.wrap(_cli().render_part(parts[k])))
            if cur:
                cur["part"] = min(k + 1, len(parts))
                state["current"] = n
            figs = _cli().figures_for_pages(_cli().load_figures(ws), _cli().part_pages(parts[k]))
            for f in figs:
                _cli()._print_figs(ws, "原资料配图（先查看再讲解）", [f["path"]])
            tasks.teach_step(state, task, "explain", "已提取当前讲解片段；由教练围绕一个解题步骤讲解。",
                             source=[a for a, text in parts[k]])
            print("教练只解释当前规则及其适用条件，先确认学生卡在哪一步；下一步用资料例题补步骤。")
        else:
            candidates = [by_id[q] for q in task["qids"] if q in by_id and by_id[q].get("answer") and not safety.readiness(by_id[q], ws)]
            if candidates:
                task["phase"] = "guided"
                print("没有可读讲义正文；下一步直接用资料内有解答的原题带做，不伪称已经读完章节。")
            else:
                tasks.finish(state, task, "material_blocked", "讲义正文和可用带做原题均不足。")
                print("资料不足，本任务已挂起；可补材料或继续其他任务。")
    elif task["phase"] == "guided":
        candidates = [by_id[q] for q in task["qids"] if q in by_id and by_id[q].get("answer") and not safety.readiness(by_id[q], ws)]
        if not candidates:
            task["phase"] = "independent"
            print("没有可靠参考例题，跳过带做而不编造。下一步尝试可用原题；无答案则保持未核验。")
        else:
            wrong = {m["qid"] for m in state.get("mistakes", []) if m.get("status") == "open"}
            candidates.sort(key=lambda q: (q["id"] not in wrong, q.get("seq", 0)))
            q = candidates[0]
            print("带做例题：只检查一个关键步骤，不能算作独立测试。")
            _cli()._print_question(q, w, ws, with_answer=True)
            tasks.teach_step(state, task, "guided", "使用资料原题及其参考解答带做，要求学生补一个关键步骤。",
                             source=q.get("answer_source") or q["source"], qid=q["id"])
            print("教练先示范第一步，再让学生补下一步；等待学生回答。随后选另一道原题独立验证。")
    else:
        _save(ws, state)
        return quiz(argparse.Namespace(workspace=ws, cmd="quiz", n=1, qid=None, chapter=None,
                                       all=False, stratified=False, outside_scope=False))
    _cli()._remember_shown(ws, state)
    _save(ws, state)
    _foot(state, w, None)
    return 0


def chapter(args):
    ws, state, w = load(args)
    chs = {c.number: c for c in _cli().load_chapters(ws)}
    if args.n not in chs:
        raise at.AttemptError("没有这一章。")
    parts = _cli().chapter_parts(chs[args.n], args.chars or state["slice_chars"])
    if not parts:
        print("该章无可提取正文，可能只有题库或扫描页。请补材料/核对原文件；不视为已讲完。")
        _foot(state, w, "python coach.py task")
        return 0
    if args.part is None:
        print("第%d章 %s｜%d个片段" % (args.n, chs[args.n].title, len(parts)))
        for i, part in enumerate(parts, 1):
            print("%d. %s" % (i, _cli().shorten(part[0][1], 70)))
    else:
        if not 1 <= args.part <= len(parts):
            raise at.AttemptError("片段编号应在1～%d之间。" % len(parts))
        print(safety.wrap(_cli().render_part(parts[args.part - 1])))
    _foot(state, w, None)
    return 0


def goto(args):
    ws, state, w = load(args)
    if at.active(state):
        raise at.AttemptError("先完成或暂缓当前作答，再切换章节；不会静默丢失原答。")
    c = st.chapter(state, args.n)
    if not c:
        raise at.AttemptError("没有该章节，请 status --detail 查看。")
    previous = tasks.current(state)
    target = next((t for t in state.get("tasks", []) if t.get("chapter") == args.n and t["status"] in tasks.OPEN), None)
    if previous and previous is not target:
        tasks.finish(state, previous, "deferred", "用户明确跳转到其他章节；旧作答和教学步骤保留。")
    if not target:
        qids = [q["id"] for q in _eligible(ws, state) if q.get("chapter") == args.n]
        sid = state.setdefault("session", {"id": uuid.uuid4().hex, "started_at": at.stamp(), "status": "active"})["id"]
        target = {"id": uuid.uuid4().hex, "session_id": sid, "kind": "new_chapter", "chapter": args.n,
                  "qids": qids, "remaining_qids": list(qids), "status": "pending", "phase": "explain",
                  "label": "自选章节：" + c["title"], "why_now": "学生明确指定，仍遵守已确认练习范围。",
                  "pass_criteria": "独立完成一道适合验证的资料原题；仅代表本次任务证据。",
                  "estimated_minutes": None, "created_at": at.stamp(), "attempt_ids": [],
                  "teaching_steps": [], "guided_qids": []}
        state["tasks"].insert(0, target)
    if args.restart:
        c["part"] = 0
        target["phase"] = "explain"
    c["status"] = "todo"
    state["current"] = args.n
    tasks.activate(state, target)
    _save(ws, state)
    print("已切换到第%d章：%s；后续 next/quiz 将执行同一任务。" % (args.n, c["title"]))
    _foot(state, w, "python coach.py next")
    return 0


def done(args):
    ws, state, w = load(args)
    if at.active(state):
        raise at.AttemptError("当前还有未结束作答。先提交核对、跳过或暂缓，不能越过它标记章节完成。")
    c = st.chapter(state, getattr(args, "chapter", None))
    if not c:
        raise at.AttemptError("没有可结束的当前章节。")
    latest = {}
    for h in state.get("history", []):
        if h.get("chapter") == c["n"]:
            latest[h["qid"]] = h
    independent = [h for h in latest.values() if h.get("result") == "right" and h.get("is_independent") and evidence.method_ready(h)]
    if not c.get("part") and not independent:
        if not getattr(args, "unverified", False):
            raise at.AttemptError("尚无学习片段或独立作答证据。可先学习；资料不足时显式 done --unverified 暂缓，不伪称学会。")
        c["status"] = "deferred"
    else:
        summary = evidence.summarize([q['id'] for q in _cli().load_bank(ws) if q.get('chapter') == c['n']], latest)
        c['status'] = 'verified' if independent and not summary['wrong'] and not summary['method_pending'] and not summary['untested'] else 'done' 
        c["part"] = c["parts"]
    for task in state.get("tasks", []):
        if task.get("chapter") == c["n"] and task["status"] in tasks.OPEN:
            tasks.finish(state, task, "completed_unverified", "用户结束章节；任务能力只依据独立作答，不以阅读完成代替。")
    nxt = _cli()._advance_to_next_todo(state)
    if not nxt:
        state["current"] = None
    _save(ws, state)
    print("第%d章已%s。" % (c["n"], "暂缓" if c["status"] == "deferred" else "结束"))
    print("本章有%d道当前独立正确证据；不代表全章或所有题型掌握。" % len(independent))
    _foot(state, w, "python coach.py task" if tasks.current(state) else "python coach.py session finish")
    return 0


def status(args):
    ws, state, w = load(args)
    tasks.refresh(state)
    stage = state["workflow"].get("stage")
    print("%s｜考试 %s｜%s" % (state["course"], state.get("exam_id") or "未标识", wf.LABELS.get(stage, "异常阶段：" + str(stage))))
    print("目标：%s｜考试日期：%s" % (state.get("goal", "pass"), state.get("exam_date") or "未填写"))
    if stage == "diagnosing":
        flow = state["workflow"]
        print("摸底提交进度：%d/%d；提交数量不等于有效判分数量。" % (len(flow["diagnostic_submitted"]), len(flow["diagnostic_ids"])))
    else:
        for line in tasks.card(tasks.current(state))[:3]:
            print(line)
    a = at.active(state)
    if a:
        print("当前作答：%s｜%s；resume 或 quiz 可重显，不增加次数。" % (a["qid"], a["status"]))
    counts = {status: sum(a.get("status") == status for a in state["attempts"].values()) for status in
              ("needs_clarification", "awaiting_manual", "material_blocked", "unverified")}
    if any(counts.values()):
        print("待澄清 %d｜待人工核对 %d｜资料阻塞 %d｜无可靠答案 %d" % tuple(counts.values()))
    if args.detail:
        for c in state["chapters"]:
            print("第%d章 %s｜%s｜片段 %d/%d" % (c["n"], c["title"], c["status"], c["part"], c["parts"]))
        for task in state.get("tasks", []):
            print("任务 %s｜%s｜%s｜题号 %s" % (task["id"], task["label"], task["status"], ", ".join(task["qids"])))
    _foot(state, w, wf.next_command(state))
    return 0


def task_command(args):
    ws, state, w = load(args)
    task = tasks.current(state)
    if args.action == "finish":
        if not task:
            print("没有未结束任务。")
            return 0
        a = at.active(state)
        if a and a.get("task_id") == task["id"]:
            at.close(state, a, "deferred", "用户结束当前任务，作答记录仍保留")
        tasks.finish(state, task, args.status, args.note or "用户明确结束当前任务")
        _save(ws, state)
        print("任务已收束；没有将未完成项目标成掌握。")
    elif args.action == 'note':
        if not task:
            raise at.AttemptError('当前没有待执行任务。')
        step = tasks.learner_step(state, task, args.note)
        _save(ws, state)
        print('实际步骤已保存：%s；待核对，不计独立成功。' % step['id'])
    elif args.action == 'assess':
        if not task or not args.step_id or not args.verdict:
            raise at.AttemptError('需指定当前步骤 --step-id 和 --verdict。')
        q = _q(ws, task.get('checkpoint_qid'))
        tasks.assess_step(state, task, args.step_id, args.verdict, args.quote, args.reference_quote, args.note, q)
        _save(ws, state)
        print('步骤核对已保存。通过才进入独立练习；部分/错误/不确定先补小步骤。')
    elif args.action == 'skip-check':
        if not task:
            raise at.AttemptError('没有当前待核对任务。')
        tasks.skip_check(state, task, args.note)
        _save(ws, state)
        print('已明确暂缓当前核对；不把跳过记为步骤掌握。')
    if args.json:
        print(json.dumps(tasks.current(state), ensure_ascii=False, indent=2))
    else:
        print("\n".join(tasks.card(tasks.current(state))))
        _foot(state, w, wf.next_command(state))
    return 0


def session(args):
    ws, state, w = load(args)
    if args.action in ("resume", "recover"):
        wf.resume(state, recover=args.action == "recover")
        # A removed bank item is a local data blocker, not an infinite wait.
        active = at.active(state)
        ids = {q["id"] for q in _cli().load_bank(ws)}
        if active and active["qid"] not in ids:
            at.close(state, active, "material_blocked", "题目已不在当前题库，旧作答保留")
            wf.diagnostic_done(state, active["qid"], "material_blocked")
            tasks.on_closed_attempt(state, active)
        _save(ws, state)
        if at.active(state):
            return _show(ws, state, w, at.active(state))
        print("已恢复保存的阶段和任务；不会重新初始化课程或清空历史。")
    elif args.action in ("pause", "finish"):
        wf.pause(state, finish=args.action == "finish")
        _save(ws, state)
        print("本次已%s；未完成任务与原答已保留。" % ("结束" if args.action == "finish" else "暂停"))
    start = (state.get("session") or {}).get("started_at", "")
    history = [h for h in state.get("history", []) if not start or h.get("ts", "") >= start]
    lines = ["# 本次学习记录", "", "本次结束不等于所有能力已掌握。", "",
             "有效判分 %d 次；独立正确 %d 次；提示下正确 %d 次。" % (
                 len(history), sum(h["result"] == "right" and h.get("is_independent", False) for h in history),
                 sum(h["result"] == "right" and not h.get("is_independent", False) for h in history))]
    for task in state.get("tasks", []):
        lines.append("- %s：%s；%s" % (task["label"], task["status"], task.get("end_reason") or task.get("pass_criteria", "")))
    reviews = [m for m in state.get("mistakes", []) if m.get("next_review_date")]
    if reviews:
        lines += ["", "下次复测（默认间隔为产品配置，不是个人效果保证）："]
        lines += ["- %s：%s" % (m["qid"], m["next_review_date"]) for m in sorted(reviews, key=lambda x: x["next_review_date"])[:8]]
    path = Path(ws) / "session_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("总结已保存：%s" % path)
    if args.action == "summary":
        print("\n".join(lines[4:]))
    _foot(state, w, wf.next_command(state))
    return 0


def resume(args):
    args.action = "resume"
    return session(args)


def evidence_panel(args):
    # At the analysis boundary `evidence` is a real alias, not a misleading
    # report command that leaves the user stuck before `plan`.
    ns = argparse.Namespace(workspace=args.workspace, chapter=args.chapter,
                            detail=False, html=None, no_html=True, cmd="gaps")
    return gaps(ns)


def gaps(args):
    rc = _cli()._legacy_gaps(args)
    if rc:
        return rc
    ws, state, w = load(args)
    names = {"needs_clarification": "原答待澄清", "awaiting_manual": "主观题待核对",
             "material_blocked": "材料不完整", "unverified": "无可靠参考答案", "deferred": "用户暂缓", "skipped": "用户跳过"}
    counts = {key: sum(a.get("status") == key for a in state["attempts"].values()) for key in names}
    if any(counts.values()):
        print("非判分记录：" + "；".join("%s %d" % (names[k], v) for k, v in counts.items() if v))
        print("这些记录不等于答错，不纳入正确率；首次原答与原因均可追溯。")
        _foot(state, w, wf.next_command(state))
    return 0


def attempts_command(args):
    ws, state, w = load(args)
    rows = [state["attempts"][aid] for aid in state["attempt_order"] if aid in state["attempts"]]
    if args.qid:
        rows = [a for a in rows if a["qid"] == args.qid]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for a in rows[-20:]:
            print("%s｜%s｜%s｜%s" % (a["id"], a["qid"], a["status"], a.get("evidence_level", "尚无判分证据")))
            if "raw_answer" in a:
                print("首次原答：%s" % a["raw_answer"])
            if a.get("graded_response") and a.get("graded_response") != a.get("raw_answer"):
                print("格式澄清：%s" % a["graded_response"])
    return 0


def verify_transfer(args):
    ws, state, w = load(args)
    q, base = _q(ws, args.qid), _q(ws, args.base_qid)
    if q["id"] == base["id"] or q["question"] == base["question"]:
        raise at.AttemptError("迁移目标题必须是不同原题，不能用同题重做冒充。")
    mapping = (bp.load(ws) or {}).get("q_map") or {}
    if args.kc not in mapping.get(q["id"], []) or args.kc not in mapping.get(base["id"], []):
        raise at.AttemptError("两道原题必须已映射到指定知识点；先检查并修正蓝图映射。")
    if not args.confirmed or not args.basis.strip():
        raise at.AttemptError("需明确确认题族关系并给出依据；关键词匹配本身不代表迁移关系成立。")
    state.setdefault("transfer_links", {})[q["id"]] = {
        "base_qid": base["id"], "kc": args.kc, "basis": args.basis, "kind": args.kind,
        "confirmed_at": at.stamp(), "source": "host_reviewed_source_items",
        "item_version": questions.question_version(q), "base_version": questions.question_version(base),
        "answer_version": questions.question_answer_version(q), "base_answer_version": questions.question_answer_version(base)}
    _save(ws, state)
    print("题族关系与变化类别已记录为人工核对。参数、表示、情境分别统计；未分类不作情境迁移解释，首次独立异题也不证明普遍泛化。")
    return 0


def workbench(args):
    from . import workbench as view
    ws, state, w = load(args)
    a = at.active(state) or (None if state["workflow"]["stage"] == "diagnosing" else at.lookup(state))
    q = _q(ws, a["qid"]) if a else None
    if a and a["status"] == "graded":
        at.expose(state, a["qid"], "solution", a["id"])
    path = view.write(args.out or str(Path(ws) / "workbench.html"), ws, state, a, q)
    _save(ws, state)
    print("学习工作台：%s" % path)
    print("页面一次显示一题，可填写、冻结并导出原答。将JSON交回教练，用 import-answer 导入后才更新进度。")
    print("未提交题目的参考答案不写入页面；这是离线文件，不是已接通TeleAgent的实时前端。")
    return 0


def import_answer(args):
    from . import workbench as view
    ws, state, w = load(args)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > 300000:
        raise at.AttemptError("作答文件不存在或过大。")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise at.AttemptError("作答文件必须是JSON对象。")
    a = state.get("attempts", {}).get(raw.get("attempt_id"))
    if not a:
        raise at.AttemptError("找不到匹配作答，不能导入另一考试或旧工作区的数据。")
    data = view.read_submission(path, state, a)
    q = _q(ws, a["qid"])
    at.verify_version(a, q)
    current = at.active(state)
    if current and current["id"] != a["id"]:
        raise at.AttemptError("当前另有未结束作答；不能用离线导入静默切换。")
    if data["action"] == "defer":
        at.close(state, a, "deferred", "学生在离线工作台选择暂缓")
        wf.diagnostic_done(state, a["qid"], "deferred")
        tasks.on_closed_attempt(state, a)
        _save(ws, state)
        print("已导入暂缓选择，不记为答错。")
        return 0
    changed = at.submit(state, a, q, data.get("response"), data.get("hinted", False))
    if not changed:
        print("同一份原答已导入；未新增或覆盖记录。")
        return 0
    a["delivery"] = "offline_file_student_reported"
    at.event(state, "offline_answer_imported", attempt_id=a["id"])
    return _after_submission(ws, state, w, a, q)



def rubric_command(args):
    ws, state, w = load(args)
    q = _q(ws, args.qid)
    if args.action == 'draft':
        value = assessment.scaffold(q)
        if not args.out:
            raise at.AttemptError('rubric draft 需 --out 指定教练内部评分文件；不要把参考答案草案给学生。')
        Path(args.out).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        print('评分契约草案已保存：%s。先核对全部要点；它不是学生作答页面。' % args.out)
    elif args.action == 'freeze':
        if not args.file:
            raise at.AttemptError('rubric freeze 需 --file 已核对的完整契约。')
        value = assessment.freeze(state, q, assessment.read_json(args.file))
        _save(ws, state)
        print('完整评分要求已冻结：%s；只作用于未提交/后续作答。' % value['contract_id'])
    elif args.action == 'ratings':
        a = at.lookup(state, q['id'], getattr(args, 'attempt', None))
        if not a or not args.out or not a.get('rubric_contract'):
            raise at.AttemptError('需有已呈题作答，并指定 --out；旧作答无契约时只保留局部反馈。')
        c = a['rubric_contract']
        value = {'contract_id': c.get('contract_id'), 'attempt_id': a['id'], 'source': assessment.source(q),
                 'criteria': [dict(i, status='uncertain', student_quote='') for i in c['criteria']]}
        Path(args.out).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        print('完整评分记录模板已生成；逐项引用首次原答，不得删掉未完成的要求。')
    return 0


def verify_reason(args):
    ws, state, w = load(args)
    q = _q(ws, args.qid)
    a = at.lookup(state, q['id'], args.attempt)
    if not a:
        raise at.AttemptError('找不到对应作答。')
    changed = assessment.verify_reason(state, a, q, args.verdict, args.quote, args.reference_quote, args.note)
    if changed and a.get('status') == 'graded':
        tasks.on_graded(state, a, reconsider=True)
    _save(ws, state)
    print('首次原答的理由核对已保存；不修改选项得分、不把后来解释并入首次作答。')
    return 0
