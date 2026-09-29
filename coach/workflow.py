# -*- coding: utf-8 -*-
"""Single command policy and recoverable diagnosis/session transitions."""
import copy
import uuid
from . import attempts as at, tasks, state as st

STAGES = {"diagnosing", "analysis", "planning", "planned", "studying", "paused", "session_complete"}
LABELS = {"diagnosing": "摸底", "analysis": "汇总分析", "planning": "安排首轮任务",
          "planned": "今日任务", "studying": "学习与练习", "paused": "已暂停", "session_complete": "本次已结束"}


def ensure(state):
    at.ensure(state)
    tasks.ensure(state)
    if state.get('learning_contract_version', 0) < 2:
        # Retain historic scores; mark old manual coverage and migration kinds
        # unknown, rather than claiming retroactive verification.
        for h in state.get('history', []):
            if h.get('grading_source') == 'reference_auto' and h.get('result') == 'right':
                from . import assessment
                effective = h.get('graded_response') or h.get('response') or ''
                legacy = {'graded_response': effective, 'raw_answer': h.get('response', ''),
                          'confidence': h.get('confidence')}
                if assessment.reasoning_required(legacy, {'answer': effective}):
                    h.setdefault('method_status', 'pending')
                    h.setdefault('method_pending', True)
            if h.get('result') == 'right' and (h.get('rubric') or h.get('grading_source') == 'reference_manual'):
                h.setdefault('assessment_coverage', 'legacy_unverified')
            if h.get('evidence_level') == 'transfer':
                h.setdefault('transfer_kind', 'unclassified')
            a = state.get('attempts', {}).get(h.get('attempt_id'))
            if a:
                if h.get('method_status'):
                    a.setdefault('method_status', h['method_status'])
                    a.setdefault('method_pending', h.get('method_pending', False))
                if h.get('assessment_coverage'):
                    a.setdefault('assessment_coverage', h['assessment_coverage'])
                if h.get('transfer_kind'):
                    a.setdefault('transfer_kind', h['transfer_kind'])
        state['learning_contract_version'] = 2
    if not isinstance(state.get("workflow"), dict):
        state["workflow"] = {"stage": "studying", "legacy_direct": True}
    flow = state["workflow"]
    flow.setdefault("diagnostic_ids", [])
    flow.setdefault("diagnostic_submitted", [])
    flow.setdefault("diagnostic_outcomes", {})
    state.setdefault("diagnosis_archive", [])
    state.setdefault("practice_policy", {"max_attempts_per_item_per_day": 3, "max_consecutive_errors": 3})
    return flow


def remaining(state):
    flow = ensure(state)
    return [q for q in flow["diagnostic_ids"] if q not in flow["diagnostic_submitted"]]


def diagnostic_done(state, qid, outcome):
    flow = ensure(state)
    if flow.get("stage") != "diagnosing":
        return
    if qid in flow["diagnostic_ids"]:
        if qid not in flow["diagnostic_submitted"]:
            flow["diagnostic_submitted"].append(qid)
        flow["diagnostic_outcomes"][qid] = outcome
    if not remaining(state):
        flow["stage"] = "analysis"
        at.event(state, "diagnosis_finished", batch_id=flow.get("batch_id"))


def begin_diagnosis(state, qids, restart=False):
    flow = ensure(state)
    if at.active(state):
        raise at.AttemptError("先暂缓或完成当前作答，再重新摸底；历史原答不会删除。")
    if restart or flow.get("diagnostic_ids"):
        state["diagnosis_archive"].append(copy.deepcopy(flow))
    state["workflow"] = {"stage": "diagnosing" if qids else "analysis", "batch_id": uuid.uuid4().hex,
                         "diagnostic_ids": list(qids), "diagnostic_submitted": [],
                         "diagnostic_outcomes": {}, "started_at": at.stamp()}
    at.event(state, "diagnosis_started", batch_id=state["workflow"]["batch_id"], count=len(qids))


def skip_diagnosis(state):
    flow = ensure(state)
    if flow.get("stage") not in ("diagnosing", "analysis"):
        return
    a = at.active(state)
    if a and a.get("purpose") == "diagnosis":
        at.close(state, a, "deferred", "用户选择跳过本轮摸底")
    for qid in remaining(state):
        flow["diagnostic_outcomes"][qid] = "skipped_by_choice"
    state["diagnosis_archive"].append(copy.deepcopy(flow))
    flow["diagnostic_ids"] = []
    flow["diagnostic_submitted"] = []
    flow["stage"] = "planning"
    at.event(state, "diagnosis_skipped")


def next_command(state):
    flow = ensure(state)
    stage = flow.get("stage")
    if stage not in STAGES:
        return "python coach.py session recover"
    if stage in ("paused", "session_complete"):
        return "python coach.py session resume"
    a = at.active(state)
    if a:
        if a["status"] == "needs_clarification":
            return 'python coach.py clarify %s "<更清楚的选项或对/错>"' % a["qid"]
        if a["status"] == "presented":
            return 'python coach.py submit %s "<你的原答>"' % a["qid"]
        return "python coach.py grade %s" % a["qid"]
    if stage == "diagnosing":
        return "python coach.py quiz --stratified"
    if stage == "analysis":
        return "python coach.py gaps"
    if stage == "planning":
        return "python coach.py plan"
    task = tasks.current(state)
    if task:
        if task['phase'] == 'awaiting_step':
            return 'python coach.py task note --note "<学生实际补出的步骤>"'
        if task['phase'] == 'step_check':
            return 'python coach.py task assess --step-id %s --verdict <met|partial|incorrect|uncertain> --quote "<原话>" --reference-quote "<参考片段>" --note "<核对说明>"' % task.get('pending_step_id')
        if task['phase'] == 'method_check':
            return 'python coach.py task；核对首次理由或 task skip-check --note "<明确暂缓原因>"'
        return "python coach.py next"
    if state.get("tasks"):
        return "python coach.py session finish"
    return "python coach.py plan"


def denied(state, args):
    """Return (message, exit code), or None. Reads also obey no-reveal gates."""
    flow = ensure(state)
    stage = flow.get("stage")
    cmd = args.cmd
    always = {"status", "doctor", "help", "exams", "switch", "session"}
    if cmd in always:
        return None
    if stage not in STAGES:
        return ("工作流阶段未知，已安全停止推进；用 session recover 保留证据并修复阶段。", 4)
    if stage in ("paused", "session_complete"):
        return ("本次学习已暂停或结束。先用 session resume 恢复；不会自动跳过未完成作答。", 4)
    if cmd == "plan" and getattr(args, "skip_diagnosis", False):
        return None
    if cmd in {"diagnose", "skip", "defer", "clarify", "submit", "resume"}:
        return None
    if stage == "diagnosing":
        if cmd == "workbench" and at.active(state):
            return None
        if cmd in {"quiz", "blueprint", "usage", "note", "import-answer"} or (cmd == "rubric" and args.action in ("draft", "freeze")):
            return None
        return ("先完成整轮摸底或明确跳过；当前不讲题、不揭晓、不标记章节完成。",
                5 if cmd == "check" or (cmd == "mistakes" and getattr(args, "answers", False)) else 4)
    if stage == "analysis":
        if cmd in {"gaps", "evidence", "blueprint", "usage", "note"}:
            return None
        return ("先看本轮能力分析，再确认计划；原答已保存。", 5 if cmd == "check" else 4)
    if stage == "planning" and cmd in {"next", "quiz", "chapter", "goto", "done", "task", "workbench"}:
        return ("先用 plan 确认首轮任务，再开始学习或练习。", 4)
    return None


def pause(state, finish=False):
    flow = ensure(state)
    if flow.get("stage") in ("paused", "session_complete"):
        return
    flow["resume_stage"] = flow["stage"]
    flow["stage"] = "session_complete" if finish else "paused"
    state.setdefault("session", {"id": uuid.uuid4().hex, "started_at": at.stamp()})
    state["session"].update(status="completed" if finish else "paused", ended_at=at.stamp())
    at.event(state, "session_finished" if finish else "session_paused")


def resume(state, recover=False):
    flow = ensure(state)
    stage = flow.get("stage")
    if stage not in STAGES:
        if not recover:
            raise at.AttemptError("阶段未知，请显式使用 session recover。")
        flow["recovered_from"] = stage
        # Keep unresolved diagnostic IDs and all attempts intact.
        flow["stage"] = "diagnosing" if remaining(state) else "analysis" if state.get("history") else "planning"
    elif stage in ("paused", "session_complete"):
        flow["stage"] = flow.pop("resume_stage", "studying")
        if flow["stage"] not in STAGES - {"paused", "session_complete"}:
            flow["stage"] = "planning"
    state.setdefault("session", {"id": uuid.uuid4().hex, "started_at": at.stamp()})["status"] = "active"
    at.event(state, "session_resumed", recovery=recover)
    tasks.refresh(state)
