# -*- coding: utf-8 -*-
"""Grading policy for CrushExam (v1.8).

This is the single machine-readable source of the grading conventions the team
agreed on (80% pass line, multi-select 10/6/0, single/true-false 10/0, and a
hint taxonomy). The human-readable companion lives at
`references/grading-policy.md`; the deployable JSON default lives at
`templates/grading-policy.json`.

Policies are *product defaults*, not calibrated score probabilities. They let
a brand-new account reproduce the same pass/score semantics without the host
LLM re-inventing them in every conversation. Nothing here invents marks for a
subjective question that has no frozen contract — that stays `None` and the
host keeps the answer unverified.

Score source flags (never fabricated):
  - `teacher`         : the question itself carries an explicit mark from the teacher.
  - `policy_default`  : the shared 10-point default defined in this policy.
  - `ai_reference`    : an AI-authored reference (explicitly labelled, not teacher text).
"""
import math


POLICY_VERSION = "crushexam-policy-v1"

# The single source of truth for defaults. `templates/grading-policy.json` is a
# serializable copy of this so it can be audited / overridden per workspace.
DEFAULT_POLICY = {
    "version": POLICY_VERSION,
    "max_score": 10,
    "pass_ratio": 0.8,  # 10-point scale => pass at >= 8
    "objective": {
        "single": {"full": 10, "wrong": 0},
        "true_false": {"full": 10, "wrong": 0},
        "multi": {"full": 10, "partial_missing": 6, "wrong": 0},
        # 不定项选择题：按学生答案形态自动分流。单字母按单选判，多字母按多选判。
        "indefinite": {"mode": "auto_split", "full": 10, "partial_missing": 6, "wrong": 0},
    },
    "subjective": {
        # 主观题分值只能来自已冻结契约的 scoring，不能在无契约时猜测。
        "score_source": "rubric_contract",
    },
    "rubric_defaults": {
        # 冻结契约若不指定分配方式，按均分（max_score / 要点数），partial 计半。
        "equal_share": True,
        "partial_share": 0.5,
    },
    "hint_recognition": [
        "viewed_answer",        # 看过答案
        "viewed_courseware",    # 看过课件/讲义
        "viewed_ai",            # 看过 AI 给的提示/解答
        "knowledge_point_hint", # 看过知识点提示
    ],
}


def pass_threshold(policy=None):
    p = policy or DEFAULT_POLICY
    return int(math.ceil(float(p.get("pass_ratio", 0.8)) * int(p.get("max_score", 10))))


def grade_objective_score(auto, policy=None):
    """Turn an objective `grading.grade()` verdict into (score, max, source).

    Returns (None, None, None) when there is nothing machine-graded: no
    reference, a restate request, or a subjective. `score` is on the policy's
    default 10-point scale (multi-select missing counts as 6, wrong as 0).
    """
    p = policy or DEFAULT_POLICY
    kind = auto.get("kind")
    verdict = auto.get("verdict")
    if kind in ("none", "subjective") or verdict in ("manual", "restate"):
        return None, None, None
    table = {"multi": "multi", "indefinite": "indefinite",
             "single": "single", "choice": "single", "true_false": "true_false"}.get(kind)
    if not table:
        return None, None, None
    obj = p.get("objective", {}).get(table, {})
    if verdict == "right":
        score = obj.get("full", p["max_score"])
    elif verdict == "partial":
        score = obj.get("partial_missing", 0)
    elif verdict == "wrong":
        score = obj.get("wrong", 0)
    else:
        return None, None, None
    return score, int(p.get("max_score", 10)), "policy_default"


def rubric_score(scoring, ratings, policy=None):
    """Compute a numeric score from a frozen contract's `scoring` and ratings.

    `scoring` (top-level of a frozen rubric contract):
      {max_score: int, pass_threshold: int, source: "teacher"|"default"|"ai_reference",
       partial_share: 0.5}

    Ratings are the per-item met/partial/missing/uncertain list already bound
    to the contract. Equal-share of `max_score` is the default allocation; an
    item status of `partial` gets `partial_share` of its share; `uncertain` /
    `unassessed` items get 0 and make the score provisional (`pass=None`)
    because the rubric is not complete.
    """
    if not scoring or not ratings:
        return None
    mx = int(scoring.get("max_score") or 0)
    if mx <= 0:
        return None
    share = mx / float(len(ratings))
    partial_share = float(scoring.get("partial_share", 0.5))
    total, pending = 0.0, False
    for item in ratings:
        status = item.get("status")
        if status == "met":
            total += share
        elif status == "partial":
            total += share * partial_share
        elif status in ("uncertain", "unassessed"):
            pending = True
    score = int(round(total))
    threshold = int(scoring.get("pass_threshold") or pass_threshold(policy))
    return {
        "max_score": mx,
        "score": score,
        "pass_threshold": threshold,
        "pass": (score >= threshold) and not pending,
        "pending": pending,
        "source": scoring.get("source", "default"),
    }