# -*- coding: utf-8 -*-
"""Persistent, source-bound tasks. A finished session is not a mastery claim."""
import copy
import uuid
from . import evidence
from . import attempts as at, state as st

OPEN = {"pending", "active"}
CLOSED = {"passed", "needs_work", "material_blocked", "deferred", "cancelled", "completed_unverified"}
PHASE_LABELS = {"explain": "定位并补讲", "guided": "按资料例题补关键步骤", "independent": "独立做资料原题", "feedback": "核对步骤与反馈", "complete": "任务收束", "awaiting_step": "等待你补一个步骤", "step_check": "核对刚才的步骤", "remediation": "补更小的前置步骤", "method_check": "选项得分保留，核对方法"}
ERROR_ACTIONS = {
    "concept": "先区分概念与反例，再口述适用条件。",
    "method": "先说清使用哪条规则及原因，再列解题步骤。",
    "procedure": "逐步写出中间状态，定位第一个错误步骤。",
    "calculation": "保留代入和中间计算，用另一种方式核对。",
    "reading": "先重述已知、所求和约束，再开始求解。",
    "expression": "按评分点补齐条件、理由和结论。",
    "unknown": "证据不足，先询问卡住的步骤；不猜错因。",
}


def ensure(state):
    state.setdefault("tasks", [])
    state.setdefault("session_archive", [])
    state.setdefault("task_schema", 1)
    for task in state['tasks']:
        if task.get('learning_gate_version') != 2:
            # Existing ended tasks are historical facts; do not erase them.
            if task.get('status') in OPEN and task.get('phase') == 'independent' and task.get('guided_qids'):
                task['phase'] = 'awaiting_step'
                task.setdefault('checkpoint_qid', task['guided_qids'][-1])
            task['learning_gate_version'] = 2
            task.setdefault('guided_round', 0)


def current(state):
    ensure(state)
    aid = state.get("current_task_id")
    active = next((t for t in state["tasks"] if t["id"] == aid and t["status"] in OPEN), None)
    if active:
        return active
    return next((t for t in state["tasks"] if t["status"] in OPEN), None)


def activate(state, task=None):
    task = task or current(state)
    if task:
        if state.get("workflow", {}).get("stage") == "planned":
            state["workflow"]["stage"] = "studying"
        task["status"] = "active"
        task.setdefault("started_at", at.stamp())
        state["current_task_id"] = task["id"]
        if task.get("chapter") is not None:
            state["current"] = task["chapter"]
        refresh(state)
    return task


def refresh(state):
    task = current(state)
    if task:
        state["current_task_id"] = task["id"]
        state["last_plan"] = {"date": st.today(), "today": {
            "task_id": task["id"], "label": task["label"], "minutes": task.get("estimated_minutes"),
            "why": task.get("why_now", ""), "criteria": task.get("pass_criteria", ""),
            "kind": task["kind"], "chapter": task.get("chapter"), "qids": list(task["qids"]),
            "phase": task["phase"], "status": task["status"]}}
    elif state.get("tasks"):
        state["current_task_id"] = None
        state["last_plan"] = {"date": st.today(), "today": {
            "label": "本次计划已收束；待巩固不等于已掌握", "qids": [], "status": "completed",
            "minutes": 0, "kind": "session_summary", "chapter": None,
            "why": "已保留本次作答、未完成项和下次复测安排"}}
    else:
        # Do not leave a v6 stale chapter label once the chapter was closed.
        old = (state.get("last_plan") or {}).get("today") or {}
        ch = st.chapter(state, old.get("chapter")) if old.get("chapter") else None
        if ch and ch.get("status") != "todo":
            state.pop("last_plan", None)


def install(state, day_plan, bank):
    ensure(state)
    if at.active(state):
        raise at.AttemptError("当前作答尚未结束。先提交并判分，或明确暂缓后再重排计划。")
    if state.get("tasks"):
        state["session_archive"].append({"archived_at": at.stamp(), "session": copy.deepcopy(state.get("session")),
                                          "tasks": copy.deepcopy(state["tasks"])})
    sid = uuid.uuid4().hex
    state["session"] = {"id": sid, "status": "active", "started_at": at.stamp(), "date": st.today()}
    state["tasks"] = []
    for raw in day_plan.tasks:
        source_qids = list(dict.fromkeys(raw.qids))
        if raw.kind == "new_chapter":
            source_qids = [q["id"] for q in bank if q.get("chapter") == raw.chapter]
        task = {"id": uuid.uuid4().hex, "session_id": sid, "kind": raw.kind,
                "chapter": raw.chapter, "qids": source_qids, "remaining_qids": list(source_qids),
                "status": "pending", "phase": "explain" if raw.kind in ("new_chapter", "mistake_review") else "independent",
                "label": raw.detail or {"due_review": "到期原题复测", "mistake_review": "修复近期错因",
                                        "cheatsheet": "考前重点速览", "final_review": "考前复盘"}.get(raw.kind, raw.kind),
                "why_now": raw.why_now, "pass_criteria": ("完成一次未见原题独立验证；选项与方法证据分别记录" if raw.kind == "new_chapter" else raw.pass_criteria),
                "estimated_minutes": raw.estimated_minutes, "created_at": at.stamp(),
                "attempt_ids": [], "teaching_steps": [], "guided_qids": [], "learning_gate_version": 2, "guided_round": 0}
        state["tasks"].append(task)
    state["current_task_id"] = state["tasks"][0]["id"] if state["tasks"] else None
    refresh(state)
    at.event(state, "plan_installed", session_id=sid, task_ids=[t["id"] for t in state["tasks"]])


def success(a, task):
    return (a.get('result') == 'right' and a.get('independent') and evidence.method_ready(a)
            and (task['kind'] != 'new_chapter' or a.get('novelty') == 'first_unseen'))


def task_observations(state, task):
    latest = {}
    for aid in task.get('attempt_ids', []):
        a = state.get('attempts', {}).get(aid)
        if a:
            latest[a['qid']] = a
    return list(latest.values())


def on_graded(state, attempt, reconsider=False):
    task = next((t for t in state.get('tasks', []) if t['id'] == attempt.get('task_id')), None)
    if not task or task['status'] not in OPEN:
        return
    if attempt['id'] in task['attempt_ids'] and not reconsider:
        return
    if attempt['id'] not in task['attempt_ids']:
        task['attempt_ids'].append(attempt['id'])
    task['remaining_qids'] = [q for q in task['remaining_qids'] if q != attempt['qid']]
    if attempt.get('method_status') == 'incorrect':
        task['needs_remediation'] = True
        task['next_teaching_action'] = '选项得分保留，但首次理由与资料相反；先修正概念或关键步骤。'
        if task['remaining_qids']:
            task['phase'] = 'explain'
            refresh(state)
        else:
            finish(state, task, 'needs_work', '本题选项正确但方法错误，保留原答和待巩固。')
        return
    if attempt['result'] == 'right' and not evidence.method_ready(attempt):
        task['verification_attempt_id'] = attempt['id']
        task['phase'] = 'method_check'
        task['next_teaching_action'] = '选项得分保留。先核对首次原答的理由；没有可核对理由则换未见原题，不能把后来解释改成首次独立。'
        refresh(state)
        return
    seen = task_observations(state, task)
    unresolved = any(a.get('result') != 'right' or not evidence.method_ready(a) for a in seen)
    if task['kind'] == 'new_chapter' and success(attempt, task) and not unresolved:
        finish(state, task, 'passed', '本任务有一道未见资料原题独立成功；只证明该题表现，不代表全章或方法已全面掌握。')
        return
    if not task['remaining_qids']:
        passed = bool(seen) and all(success(a, task) for a in seen)
        finish(state, task, 'passed' if passed else 'needs_work',
               '本批已收束；同题复测只说明保持，遗留错误与方法待核对不会被其他题的成功遮盖。')
        return
    if attempt['result'] == 'wrong':
        task['next_teaching_action'] = ERROR_ACTIONS.get(attempt.get('error_type'), ERROR_ACTIONS['unknown'])
        task['needs_remediation'] = True
        task['phase'] = 'explain' if task['kind'] == 'new_chapter' else 'feedback'
    else:
        task['phase'] = 'independent'
    refresh(state)


def on_closed_attempt(state, attempt):
    task = next((t for t in state.get("tasks", []) if t["id"] == attempt.get("task_id")), None)
    if not task or task["status"] not in OPEN:
        return
    task["remaining_qids"] = [q for q in task["remaining_qids"] if q != attempt["qid"]]
    task.setdefault("inconclusive", []).append({"attempt_id": attempt["id"], "status": attempt["status"]})
    if not task["remaining_qids"]:
        finish(state, task, "material_blocked" if attempt["status"] == "material_blocked" else "needs_work",
               "没有剩余可验证原题；保留未测或待巩固，不虚构通过。")
    else:
        refresh(state)


def finish(state, task, status, reason=""):
    if status not in CLOSED:
        raise at.AttemptError("无效的任务结束状态。")
    if status == "passed":
        valid = [state.get("attempts", {}).get(aid, {}) for aid in task.get("attempt_ids", [])]
        if not any(success(a, task) for a in valid) or any(a.get("result") != "right" or not evidence.method_ready(a) for a in task_observations(state, task)):
            raise at.AttemptError("独立新题证据不足或仍有未修复的题/方法，不能将任务标为通过。")
    task.update(status=status, phase="complete", ended_at=at.stamp(), end_reason=reason)
    at.event(state, "task_finished", task_id=task["id"], status=status)
    refresh(state)


def teach_step(state, task, phase, note="", source=None, qid=None):
    if phase not in ("explain", "guided", "independent"):
        raise at.AttemptError("无效的教学步骤。")
    task.setdefault("teaching_steps", []).append({"phase": phase, "at": at.stamp(), "note": note, "source": source})
    if qid and phase == "guided":
        if qid not in task["guided_qids"]:
            task["guided_qids"].append(qid)
        at.expose(state, qid, "hint")
    task['phase'] = {'explain': 'guided', 'guided': 'awaiting_step', 'independent': 'independent'}[phase]
    if phase == 'guided':
        task['checkpoint_qid'] = qid
        task['checkpoint_id'] = uuid.uuid4().hex
        task['guided_round'] = task.get('guided_round', 0) + 1
        task.pop('pending_step_id', None)
    state["support_at"] = at.stamp()
    refresh(state)


def card(task):
    if not task:
        return ["本次暂无待执行任务。已结束不代表全部掌握，可查看总结或安排下一次。"]
    return ["当前任务：%s" % task["label"],
            "步骤：%s｜预算 %s 分钟" % (PHASE_LABELS.get(task["phase"], task["phase"]), task.get("estimated_minutes") or "待定"),
            "完成依据：%s" % task.get("pass_criteria", "保留实际作答证据"),
            "原因：%s" % task.get("next_teaching_action", task.get("why_now", ""))]


WAIT_PHASES = {'awaiting_step', 'step_check', 'remediation', 'method_check'}


def learner_step(state, task, text):
    if task['phase'] not in {'awaiting_step', 'step_check'}:
        raise at.AttemptError('只有带做步骤等待回应时可提交步骤；其他困惑请使用 note。')
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise at.AttemptError('需要保存学生实际步骤，不能提交空文本。')
    previous = next((x for x in task.get('learner_steps', []) if x['id'] == task.get('pending_step_id')), None)
    if previous and previous['status'] == 'pending':
        if previous['text'] == text:
            return previous
        raise at.AttemptError('上一条步骤尚未核对，不覆盖原文；先评估或明确暂缓。')
    item = {'id': uuid.uuid4().hex, 'text': text, 'at': at.stamp(), 'assisted': True,
            'checkpoint_id': task.get('checkpoint_id'), 'qid': task.get('checkpoint_qid'), 'status': 'pending'}
    task.setdefault('learner_steps', []).append(item)
    task['pending_step_id'] = item['id']
    task['phase'] = 'step_check'
    at.event(state, 'guided_response_submitted', task_id=task['id'], step_id=item['id'])
    refresh(state)
    return item


def assess_step(state, task, step_id, verdict, quote, reference_quote, note, q):
    from . import assessment
    item = next((x for x in task.get('learner_steps', []) if x['id'] == step_id), None)
    if not item or step_id != task.get('pending_step_id') or item.get('qid') != q['id']:
        raise at.AttemptError('步骤编号不匹配当前待核对的带做回应。')
    if item['status'] != 'pending':
        if item['status'] == verdict and item.get('review', {}).get('note') == note:
            return False
        raise at.AttemptError('步骤评价已冻结，不能改写旧评价。')
    if task['phase'] != 'step_check':
        raise at.AttemptError('当前阶段不允许核对旧步骤。')
    if not quote or quote not in item['text'] or not note or not note.strip():
        raise at.AttemptError('需引用学生刚才的实际步骤，并给出核对说明。')
    ref = assessment.normalize(reference_quote)
    if not ref or ref not in assessment.normalize(q.get('answer')):
        raise at.AttemptError('需引用带做原题参考解答的真实片段。')
    if verdict not in {'met', 'partial', 'incorrect', 'uncertain'}:
        raise at.AttemptError('步骤评价无效。')
    item['status'] = verdict
    item['review'] = {'student_quote': quote, 'reference_quote': reference_quote, 'source': assessment.source(q),
                      'note': note, 'at': at.stamp(), 'assessor': 'host_manual'}
    task['phase'] = 'independent' if verdict == 'met' else 'remediation'
    task['next_teaching_action'] = '换另一道未见资料原题验证。' if verdict == 'met' else '先补一个更小的前置步骤，不重复整段讲义。'
    task['needs_remediation'] = verdict != 'met'
    at.event(state, 'guided_response_reviewed', task_id=task['id'], step_id=step_id, verdict=verdict)
    refresh(state)
    return True


def skip_check(state, task, reason):
    if task['phase'] not in WAIT_PHASES or not reason or not reason.strip():
        raise at.AttemptError('需处于待回应/待核对阶段，并明确记录学生选择跳过或暂缓的原因。')
    old = task['phase']
    task.setdefault('skipped_checks', []).append({'phase': old, 'reason': reason, 'at': at.stamp(),
                                                'step_id': task.get('pending_step_id')})
    task['phase'] = 'independent'
    at.event(state, 'checkpoint_explicitly_skipped', task_id=task['id'], phase=old, reason=reason)
    if not task.get('remaining_qids'):
        finish(state, task, 'needs_work', '本次明确暂缓核对，待巩固仍保留。')
    else:
        refresh(state)
