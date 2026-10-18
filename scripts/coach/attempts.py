# -*- coding: utf-8 -*-
"""Immutable raw submissions and timestamped evidence, schema v7.

`attempts` is authoritative. `pending` and `open_quiz` are compatibility views,
not independent stores. One unresolved presented/submitted attempt is active.
Diagnostic manual answers can be parked without blocking the next item.
"""
import copy
import json
import datetime as dt
import uuid
from . import evidence, grading, policy as policy_mod, questions, state as st, assessment

UNRESOLVED = {"presented", "needs_clarification", "submitted", "awaiting_manual"}
TERMINAL = {"graded", "skipped", "deferred", "cancelled", "material_blocked", "unverified"}


class AttemptError(ValueError):
    pass


def stamp():
    return dt.datetime.now().isoformat(timespec="microseconds")


def event(state, kind, **fields):
    state.setdefault("events", []).append(dict(id=uuid.uuid4().hex, at=stamp(), kind=kind, **fields))


def ensure(state):
    """Idempotent additive migration; never invent missing legacy timing."""
    state.setdefault("attempts", {})
    state.setdefault("attempt_order", [])
    state.setdefault("exposures", [])
    state.setdefault("question_blocks", {})
    state.setdefault("events", [])
    if state.get("attempt_schema") == 1:
        return
    for i, h in enumerate(state.get("history", [])):
        aid = h.get("attempt_id") or "legacy-%d-%s" % (i, uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(h, sort_keys=True, ensure_ascii=False)).hex[:12])
        h["attempt_id"] = aid
        if aid not in state["attempts"]:
            state["attempts"][aid] = dict(
                id=aid, qid=h.get("qid"), status="graded", legacy=True,
                raw_answer=h.get("response"), submitted_at=h.get("ts"),
                result=h.get("result"), evidence_level=h.get("evidence_level", "untested"),
                independent=h.get("is_independent", False), task_id=None,
                item_version=h.get("item_version"), answer_version=h.get("answer_version"),
                events=[], submissions=[])
            state["attempt_order"].append(aid)
    for qid, p in list((state.get("pending") or {}).items()):
        if p.get("recorded"):
            # History is authoritative for already graded legacy diagnostics.
            continue
        aid = p.get("attempt_id") or "legacy-pending-" + uuid.uuid5(uuid.NAMESPACE_URL, qid + str(p.get("ts"))).hex
        a = dict(id=aid, qid=qid, status="submitted", legacy=True, task_id=None,
                 raw_answer=p.get("answer", ""), submitted_at=p.get("ts"),
                 graded_response=p.get("answer", ""), hinted=bool(p.get("hinted")),
                 timing_unknown=bool(p.get("revealed")),
                 confidence=p.get("confidence"), minutes_spent=p.get("minutes_spent"),
                 submissions=[{"response": p.get("answer", ""), "at": p.get("ts"), "kind": "legacy"}])
        state["attempts"][aid] = a
        state["attempt_order"].append(aid)
        p["attempt_id"] = aid
    for qid in state.get("open_quiz", []):
        if not any(a["qid"] == qid and a["status"] in UNRESOLVED for a in state["attempts"].values()):
            aid = "legacy-open-" + uuid.uuid5(uuid.NAMESPACE_URL, str(state.get("exam_id")) + qid).hex
            state["attempts"][aid] = dict(id=aid, qid=qid, status="presented", legacy=True,
                                          task_id=None, presented_at=stamp(), events=[], submissions=[])
            state["attempt_order"].append(aid)
    state["attempt_schema"] = 1
    candidates = [a for a in state["attempts"].values() if a["status"] in UNRESOLVED]
    state["active_attempt_id"] = candidates[-1]["id"] if candidates else None
    sync(state)


def active(state):
    aid = state.get("active_attempt_id")
    a = state.get("attempts", {}).get(aid)
    return a if a and a.get("status") in UNRESOLVED else None


def lookup(state, qid=None, aid=None, unresolved=False):
    ensure(state)
    if aid:
        a = state["attempts"].get(aid)
        if not a or (qid and a["qid"] != qid):
            raise AttemptError("作答编号与当前题目不匹配。")
        return a
    for key in reversed(state["attempt_order"]):
        a = state["attempts"].get(key)
        if a and (qid is None or a["qid"] == qid) and (not unresolved or a["status"] in UNRESOLVED):
            return a
    return None


def sync(state):
    a = active(state)
    state["open_quiz"] = [a["qid"]] if a and a["status"] in ("presented", "needs_clarification") else []
    pending = {}
    for aid in state.get("attempt_order", []):
        item = state["attempts"].get(aid, {})
        if item.get("status") in ("submitted", "awaiting_manual", "needs_clarification"):
            pending[item["qid"]] = {
                "attempt_id": aid, "answer": item.get("raw_answer", ""),
                "ts": item.get("submitted_at"), "hinted": item.get("hinted", False),
                "confidence": item.get("confidence"), "minutes_spent": item.get("minutes_spent"),
                "revealed": bool(item.get("solution_seen_at")), "origin": "quiz", "recorded": False,
                "status": item["status"]}
    state["pending"] = pending


def verify_version(a, q):
    for field, expected in (("item_version", questions.question_version(q)),
                            ("answer_version", questions.question_answer_version(q))):
        if a.get(field) and a[field] != expected:
            raise AttemptError("题干或参考答案已改变；旧原答保留但不能套用新答案判分，请取消本次作答并重新呈题。")


def present(state, q, task_id=None, purpose="practice"):
    ensure(state)
    a = active(state)
    if a:
        if a["qid"] == q["id"]:
            return a, False
        raise AttemptError("已有未结束的作答；先恢复、提交、跳过或暂缓当前题。")
    prior = lookup(state, q["id"], unresolved=True)
    if prior:
        state["active_attempt_id"] = prior["id"]
        sync(state)
        return prior, False
    aid = uuid.uuid4().hex
    a = dict(id=aid, qid=q["id"], chapter=q.get("chapter"), status="presented",
             task_id=task_id, purpose=purpose, presented_at=stamp(),
             item_version=questions.question_version(q), answer_version=questions.question_answer_version(q),
             hinted=False, submissions=[], events=[], rubric_contract=assessment.snapshot(state, q))
    state["attempts"][aid] = a
    state["attempt_order"].append(aid)
    state["active_attempt_id"] = aid
    event(state, "question_presented", attempt_id=aid, qid=q["id"], task_id=task_id)
    sync(state)
    return a, True


def submit(state, a, q, response, hinted=False, confidence=None, minutes_spent=None):
    verify_version(a, q)
    if a["status"] != "presented":
        if a.get("raw_answer") == response:
            return False  # idempotent retry, not another score
        raise AttemptError("原答已提交，不能覆盖。格式澄清请用 clarify；重新作答必须建立新的 attempt。")
    if not isinstance(response, str) or not response.strip():
        raise AttemptError("原答不能为空；不会做或资料缺失时用 skip/defer，不能替学生填答案。")
    if len(response) > 100000:
        raise AttemptError("本次原答过长，请按单道题提交。")
    if minutes_spent is not None and not (0 <= minutes_spent <= 1440):
        raise AttemptError("答题用时必须为 0～1440 分钟。")
    at = stamp()
    a.update(raw_answer=response, graded_response=response, submitted_at=at,
             hinted=bool(hinted or a.get("hinted")), confidence=confidence,
             minutes_spent=minutes_spent, status="submitted")
    a["submissions"].append({"response": response, "at": at, "kind": "initial"})
    a["independent"] = independent(state, a)
    verdict = grading.grade(response, q.get("answer") or "")
    if verdict["verdict"] == "restate":
        a["status"] = "needs_clarification"
        a["clarification_kind"] = verdict["kind"]
    event(state, "answer_submitted", attempt_id=a["id"], qid=q["id"])
    sync(state)
    return True


def clarify(state, a, q, response):
    verify_version(a, q)
    if a["status"] != "needs_clarification":
        raise AttemptError("只有无法解析的原答可以澄清；已经可判分的答案不能改写。")
    if a.get("solution_seen_at"):
        raise AttemptError("已经揭晓的作答不能再澄清为独立证据；请暂缓后建立新作答。")
    result = grading.grade(response, q.get("answer") or "")
    if result["verdict"] not in ("right", "wrong", "partial"):
        raise AttemptError("仍无法解析。请只给题型要求的选项字母或对/错，也可跳过本题。")
    a["submissions"].append({"response": response, "at": stamp(), "kind": "clarification"})
    a.update(graded_response=response, status="submitted")
    event(state, "answer_clarified", attempt_id=a["id"], qid=q["id"])
    sync(state)


def expose(state, qid, kind="solution", aid=None):
    at = stamp()
    state.setdefault("exposures", []).append({"qid": qid, "kind": kind, "at": at, "attempt_id": aid})
    a = state.get("attempts", {}).get(aid)
    if a:
        a.setdefault("solution_seen_at" if kind == "solution" else "hint_seen_at", at)
        if a["status"] in ("presented", "needs_clarification"):
            a["hinted"] = True
    event(state, "source_exposed", qid=qid, exposure_kind=kind, attempt_id=aid)
    sync(state)


def independent(state, a):
    """Post-submission feedback is not assistance to the frozen raw response."""
    if a.get("hinted") or a.get("timing_unknown"):
        return False
    submitted = a.get("submitted_at") or stamp()
    day = submitted[:10]
    return not any(e.get("qid") == a["qid"] and e.get("at", "")[:10] == day
                   and e.get("at", "") <= submitted for e in state.get("exposures", []))


def park(state, a, status="awaiting_manual"):
    a["status"] = status
    if state.get("active_attempt_id") == a["id"]:
        state["active_attempt_id"] = None
    sync(state)


def close(state, a, status, reason=""):
    if status not in TERMINAL - {"graded"}:
        raise AttemptError("无效的作答结束状态。")
    if a["status"] in TERMINAL:
        return False
    a.update(status=status, closed_at=stamp(), close_reason=reason)
    if status == "material_blocked":
        state.setdefault("question_blocks", {})[a["qid"]] = {"reason": reason, "at": stamp()}
    if state.get("active_attempt_id") == a["id"]:
        state["active_attempt_id"] = None
    event(state, "attempt_closed", attempt_id=a["id"], status=status, reason=reason)
    sync(state)
    return True


def record(state, a, q, result, grading_source, note="", rubric=None, error_type=None, transfer=False):
    verify_version(a, q)
    if a["status"] == "graded":
        return False
    if a["status"] not in ("submitted", "awaiting_manual"):
        raise AttemptError("先提交可判定的原答，再判分；澄清、跳过和材料阻塞不等于答错。")
    if not (q.get("answer") or "").strip():
        raise AttemptError("无可靠参考答案，保持未核验；不能记录确定的对错。")
    auto = grading.grade(a.get("graded_response", a["raw_answer"]), q["answer"])
    if auto["verdict"] in ("right", "wrong", "partial"):
        expected = "right" if auto["verdict"] == "right" else "wrong"
        if result != expected:
            raise AttemptError("所填结果与已保存原答和参考答案不一致，不能覆盖自动判分。")
    if result not in ("right", "wrong"):
        raise AttemptError("跳过不是判分；请用 skip 命令。")
    indep = independent(state, a)
    # Numeric score: objective auto-grading uses the shared policy default;
    # subjective uses the frozen contract's scoring (or none if not frozen).
    score_fields = {}
    if rubric and isinstance(rubric.get("numeric_score"), dict):
        numeric = rubric["numeric_score"]
        score_fields = {
            "score": numeric.get("score"),
            "max_score": numeric.get("max_score"),
            "score_source": numeric.get("source"),
            "score_pass": numeric.get("pass"),
            "score_pass_threshold": numeric.get("pass_threshold"),
        }
    else:
        sc, mx, src = policy_mod.grade_objective_score(auto)
        if sc is not None:
            threshold = policy_mod.pass_threshold()
            score_fields = {
                "score": sc,
                "max_score": mx,
                "score_source": src,
                "score_pass": sc >= threshold,
                "score_pass_threshold": threshold,
            }
    prior = [h for h in state.get("history", []) if h.get("qid") == q["id"]]
    day = a["submitted_at"][:10]
    delayed = bool(prior) and max(h.get("ts", "")[:10] for h in prior) < day
    level = evidence.classify_attempt(indep, result == "right", saw_hint=not indep,
                                      is_delayed=delayed, is_variant=bool(transfer and indep))
    method = assessment.method_status(a, q)
    previous_seen = any(old.get('qid') == q['id'] and old.get('id') != a['id']
                        for old in state.get('attempts', {}).values())
    prior_exposure = any(e.get('qid') == q['id'] and e.get('at', '') <= a['presented_at']
                         for e in state.get('exposures', []))
    dimensions = {'method_status': method, 'method_pending': method in ('pending', 'uncertain'),
                  'novelty': 'first_unseen' if not prior and not previous_seen and not prior_exposure else 'previously_seen',
                  'same_item_retest': delayed,
                  'transfer_kind': transfer.get('kind', 'unclassified') if isinstance(transfer, dict) else None,
                  'transfer_basis': copy.deepcopy(transfer) if isinstance(transfer, dict) else None}
    if a.get('reasoning_review'):
        dimensions['reasoning_review'] = copy.deepcopy(a['reasoning_review'])
    h = st.record_result(state, q["id"], q.get("chapter"), result, note,
                     evidence_level=level, is_independent=indep, response=a["raw_answer"],
                     answer_version=questions.question_answer_version(q),
                     grading_source=grading_source, confidence=a.get("confidence"),
                     minutes_spent=a.get("minutes_spent"), item_version=questions.question_version(q),
                     attempt_id=a["id"], rubric=rubric, error_type=error_type,
                     graded_response=a.get("graded_response"), submitted_at=a["submitted_at"],
                     score=score_fields.get("score"), max_score=score_fields.get("max_score"),
                     score_source=score_fields.get("score_source"), score_pass=score_fields.get("score_pass"))
    a.update(copy.deepcopy(dimensions))
    a.update(copy.deepcopy(score_fields))
    h.update(copy.deepcopy(dimensions))
    h.update(copy.deepcopy(score_fields))
    h["verdict"] = auto["verdict"] if auto["verdict"] in ("right", "wrong", "partial") else result
    # Original submission time, not later grading time, determines the study day.
    h["graded_at"] = stamp()
    h["ts"] = a["submitted_at"]
    a.update(status="graded", result=result, evidence_level=level, independent=indep,
             graded_at=h["graded_at"], rubric=copy.deepcopy(rubric), error_type=error_type,
             grading_source=grading_source, note=note, verdict=h["verdict"])
    st.set_review_date(state, q["id"], evidence.compute_review_date(level))
    m = next((m for m in state["mistakes"] if m["qid"] == q["id"]), None)
    if m:
        m["review_count"] = m.get("review_count", 0) + int(bool(prior))
        if result == "right" and (not indep or not evidence.method_ready(a)) and m.get("count", 0):
            m["status"] = "open"  # assisted success does not repair an independent gap
    if state.get("active_attempt_id") == a["id"]:
        state["active_attempt_id"] = None
    event(state, "attempt_graded", attempt_id=a["id"], result=result, evidence_level=level)
    sync(state)
    return True


def eligibility_reason(state, qid):
    if qid in state.get("question_blocks", {}):
        return "资料待补，先修复题干或配图"
    today = st.today()
    limit = state.get("practice_policy", {}).get("max_attempts_per_item_per_day", 3)
    tried = [a for a in state.get("attempts", {}).values() if a.get("qid") == qid
             and (a.get("submitted_at") or "")[:10] == today and a.get("raw_answer") is not None]
    if len(tried) >= limit:
        return "同题今日尝试已达上限；换题、补讲或次日复测"
    if any(a.get("qid") == qid and a.get("status") == "deferred"
           and a.get("closed_at", "")[:10] == today for a in state.get("attempts", {}).values()):
        return "本题已暂缓到下一学习日"
    return None


def practice_break(state):
    cutoff = state.get("support_at", "")
    limit = state.get("practice_policy", {}).get("max_consecutive_errors", 3)
    streak = 0
    for h in reversed(state.get("history", [])):
        if h.get("ts", "")[:10] != st.today() or h.get("ts", "") <= cutoff:
            break
        if h.get("result") != "wrong":
            break
        streak += 1
    return streak >= limit


def reconcile_runtime(state, old, old_bank, new_bank):
    """Preserve v7 ledgers across setup; quarantine changed identities.

    History reconciliation remains in state.reconcile_question_records. This
    companion migrates the task/attempt ledger instead of silently dropping it.
    """
    if not old or old.get("exam_id") != state.get("exam_id"):
        return
    ensure(old)
    new_by_fingerprint = {questions.question_fingerprint(q): q for q in new_bank}
    mapping = {}
    for q in old_bank:
        qid = questions.question_fingerprint(q)
        current = new_by_fingerprint.get(qid)
        if current and questions.question_answer_version(q) == questions.question_answer_version(current):
            mapping[q["id"]] = current["id"]
    for field in ("attempts", "attempt_order", "attempt_schema", "exposures", "events", "tasks", "session",
                  "session_archive", "current_task_id", "active_attempt_id", "practice_policy", "support_at", "transfer_links",
                  "rubric_contracts", "rubric_archive", "learning_contract_version"):
        if field in old:
            state[field] = copy.deepcopy(old[field])
    for a in state.get("attempts", {}).values():
        old_id = a["qid"]
        if old_id not in mapping:
            a["previous_status"] = a["status"]
            a["status"] = "quarantined"
            a["quarantine_reason"] = "question_or_answer_changed_at_setup"
            if state.get("active_attempt_id") == a["id"]:
                state["active_attempt_id"] = None
        else:
            a["qid"] = mapping[old_id]
    for task in state.get("tasks", []):
        valid = [mapping[qid] for qid in task.get("qids", []) if qid in mapping]
        if len(valid) != len(task.get("qids", [])) and task["status"] in ("pending", "active"):
            task.update(status="needs_work", phase="complete", end_reason="题库已改变，请依据新材料重新计划")
        task["qids"] = valid
        task["remaining_qids"] = [mapping[qid] for qid in task.get("remaining_qids", []) if qid in mapping]
    # Re-extraction is an explicit material repair. Permanent local blockers
    # are re-evaluated by readiness(), not blindly copied to an updated bank.
    state["question_blocks"] = {}
    for exposure in state.get("exposures", []):
        exposure["qid"] = mapping.get(exposure["qid"], exposure["qid"])
    sync(state)
