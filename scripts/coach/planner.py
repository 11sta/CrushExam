# -*- coding: utf-8 -*-
"""Cross-day scheduling engine with three-goal strategy.

Goal strategies:
  pass  — Cover all chapters → basic competency (immediate evidence). Rush pace.
  high  — Cover all → fill gaps → transfer-level evidence. Balanced pace.
  long  — Build durable knowledge via spaced repetition. Slow pace, more review.

Each DayPlan contains tasks with a "why_now" reasoning string so the agent
can explain to the student why this task is scheduled today.
"""
from . import evidence as evidence_model

import datetime as _dt
from . import blueprint as bpmod


# ------------------------------------------------------------------ data classes

class Task(object):
    """A single study task for one day."""

    def __init__(self, kind, chapter=None, qids=None, why_now="", detail="",
                 pass_criteria="", estimated_minutes=None):
        self.kind = kind          # "new_chapter" | "due_review" | "mistake_review" | "cheatsheet" | "final_review"
        self.chapter = chapter    # chapter number or None
        self.qids = qids or []    # question ids for review tasks
        self.why_now = why_now    # human-readable reasoning
        self.detail = detail      # extra context
        self.pass_criteria = pass_criteria  # "what counts as done"
        self.estimated_minutes = estimated_minutes  # budget estimate, never a score forecast

    def __repr__(self):
        return "Task(%s, ch=%s, qids=%d)" % (self.kind, self.chapter, len(self.qids))


class DayPlan(object):
    """A plan for one study day."""

    def __init__(self, date_str=None, day_index=0, tasks=None, note=""):
        self.date_str = date_str  # ISO date or None
        self.day_index = day_index  # 1-based day number
        self.tasks = tasks or []
        self.note = note          # summary note for this day

    @property
    def chapters(self):
        """Chapter numbers covered by new_chapter tasks."""
        return [t.chapter for t in self.tasks if t.kind == "new_chapter"]

    @property
    def review_count(self):
        """Number of review tasks."""
        return sum(1 for t in self.tasks if t.kind in ("due_review", "mistake_review"))


# ------------------------------------------------------------------ core planner

def _today():
    return _dt.date.today()


def _parse_date(s):
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def days_to_exam(exam_date):
    """Return integer days from today to exam_date, or None."""
    d = _parse_date(exam_date)
    if d is None:
        return None
    return (d - _today()).days


def _due_reviews(state, today_iso):
    """Collect overdue and due-today review question ids."""
    overdue = []
    due_today = []
    for m in state.get("mistakes", []):
        rd = m.get("next_review_date")
        if not rd:
            continue
        if rd < today_iso:
            overdue.append(m["qid"])
        elif rd == today_iso:
            due_today.append(m["qid"])
    return overdue, due_today


def _open_mistake_qids(state):
    """Question ids of open mistakes."""
    return [m["qid"] for m in state.get("mistakes", []) if m.get("status") == "open"]


def _todo_chapters(state):
    """Chapter dicts that are still todo, with current chapter first."""
    todo = [c for c in state["chapters"] if c["status"] == "todo"]
    cur = None
    for c in state["chapters"]:
        if c["n"] == state.get("current"):
            cur = c
            break
    if cur and cur["status"] == "todo":
        todo = [cur] + [c for c in todo if c["n"] != cur["n"]]
    return todo


def _done_count(state):
    return sum(1 for c in state["chapters"] if c["status"] in ("done", "verified"))


def _evidence_summary(state):
    """Count questions at each evidence level."""
    counts = {"untested": 0, "hinted": 0, "immediate": 0, "delayed": 0, "transfer": 0}
    latest = {h['qid']: h for h in state.get('history', []) if h.get('result') in ('right', 'wrong', 'skip')}
    for record in latest.values():
        ev = record.get('evidence_level', 'untested') if record.get('result') == 'right' and evidence_model.method_ready(record) else 'untested'
        if ev in counts:
            counts[ev] += 1
    return counts


def _daily_minutes(state, exam, weekly_hours):
    """Default one 25-minute focus task; honor an explicit weekly time budget."""
    # An explicit daily budget is more precise than averaging a weekly budget.
    daily = state.get("study_minutes")
    if not isinstance(daily, bool):
        try:
            daily_value = float(daily)
            if 1 <= daily_value <= 1440:
                return int(daily_value)
        except (TypeError, ValueError, OverflowError):
            pass
    hours = weekly_hours
    if hours is None:
        hours = (exam or {}).get("weekly_hours", state.get("weekly_hours"))
    try:
        minutes = int(float(hours) * 60 // 7)
    except (TypeError, ValueError, OverflowError):
        return 25
    return minutes if minutes > 0 else 25


def _prioritized_chapters(state, bank, bp, exam):
    """Rank by actual latest errors, verified exam importance and known scope.

    A printed exercise's points and chapter question count never become marks.
    When marks are unknown we rank the observed gap and mark the reason unknown.
    """
    todo = _todo_chapters(state)
    if bank is None:
        return [(c, "当前章节" if c["n"] == state.get("current") else "按顺序推进")
                for c in todo]
    eligible = bpmod.eligible_questions(state, bank, bp, exam)
    allowed = bpmod._scope_chapters(state, bp, exam)
    if allowed is not None:
        todo = [c for c in todo if c["n"] in allowed]
    latest = bpmod._latest_attempts(state)
    qmap = (bp or {}).get("q_map") or {}
    marks_by_type = bpmod.confirmed_type_points(bp)
    marks_by_kc = bpmod.confirmed_kc_points(bp)
    structure_source = ((bp or {}).get("structure") or {}).get("source")
    kc_source = {k["id"]: k.get("weight_source") for k in (bp or {}).get("kcs") or []}
    ranked = []
    for ch in todo:
        questions = [q for q in eligible if q.get("chapter") == ch["n"]]
        errors = independent = helped = 0
        touched = set()
        points = []
        for q in questions:
            qid = q["id"]
            if qid in touched:
                continue
            touched.add(qid)
            h = latest.get(qid)
            if h and evidence_model.observation(h) in ("gap", "method_pending"):
                errors += 1
            elif h and h["result"] == "right":
                if evidence_model.observation(h) in ("immediate", "retention", "variation"):
                    independent += 1
                else:
                    helped += 1
            kind = bpmod.question_type(q.get("type"))
            if kind in marks_by_type:
                points.append((marks_by_type[kind], "%s（%s）" % (kind, structure_source)))
            for kid in qmap.get(qid, []):
                if kid in marks_by_kc:
                    points.append((marks_by_kc[kid], "%s（%s）" % (kid, kc_source[kid])))
        # A KC without a mapped question can still have explicitly verified marks.
        for kc in (bp or {}).get("kcs") or []:
            if kc.get("chapter") == ch["n"] and kc["id"] in marks_by_kc:
                points.append((marks_by_kc[kc["id"]], "%s（%s）" %
                               (kc["title"], kc_source[kc["id"]])))
        known = max(points, default=None, key=lambda x: x[0])
        untested = max(0, len(touched) - errors - independent - helped)
        # A demonstrated error outranks not-yet-tested areas; unknown is not zero.
        gap_rank = 0 if errors or helped else 1 if untested or not touched else 2
        reason = ("最近独立错/跳 %d 题、提示后对 %d 题；" % (errors, helped)) if errors or helped else (
            "尚未摸底；" if untested or not touched else "已有 %d 题独立成功；" % independent)
        reason += ("已核实题型或知识点分值 %g 分 %s" % (known[0], known[1])
                   if known else "考试对应分值未知")
        reason += "；基于本章 %d 道已测题" % (len(touched) - untested)
        ranked.append(((gap_rank, -known[0] if known else 0, -errors,
                        ch["n"] != state.get("current"), ch["n"]), ch, reason))
    ranked.sort(key=lambda item: item[0])
    return [(ch, why) for _, ch, why in ranked]


# ------------------------------------------------------------------ goal strategies

def _chapters_per_day(n_todo, n_days, goal):
    """How many new chapters to tackle per day, by goal.

    pass:  distribute evenly, last day(s) for review only
    high:  slightly slower, reserve more review time
    long:  slower pace, more review days

    Returns (chapters_per_day, study_days) where study_days is the
    number of days that actually have new chapters.
    """
    if n_days <= 0 or n_todo <= 0:
        return 0, 0
    if goal == "pass":
        study_days = max(1, n_days - 1)  # last day for review
    elif goal == "high":
        study_days = max(1, n_days - 2)  # last 2 days for review
    else:  # long
        study_days = max(1, n_days - 3)  # last 3 days for review
    study_days = min(study_days, n_todo)  # don't have more study days than chapters
    cpd = max(1, -(-n_todo // study_days))  # ceil division
    return cpd, study_days


def generate_plan(state, exam_date=None, goal=None, today=None,
                  bank=None, bp=None, exam=None, weekly_hours=None):
    """Generate a day-by-day study plan.

    Args:
        state: study_state dict
        exam_date: ISO date string (overrides state["exam_date"])
        goal: "pass" | "high" | "long" (overrides state["goal"])
        today: ISO date string (for testing); defaults to today
        bank, bp, exam: optional current exam data; omitted for legacy callers
        weekly_hours: confirmed available time; overrides exam entry

    Returns:
        list[DayPlan]
    """
    if exam_date is None:
        exam_date = state.get("exam_date")
    if goal is None:
        goal = state.get("goal", "pass")
    if today is None:
        today = _today().isoformat()
    daily_budget = _daily_minutes(state, exam, weekly_hours)

    today_date = _parse_date(today)
    exam_d = _parse_date(exam_date)

    # If no exam date, fall back to exam_days
    if exam_d is None:
        n_days = state.get("exam_days")
        if not n_days or n_days < 1:
            return _single_day_plan(state, goal, today, bank, bp, exam, daily_budget)
        # Use exam_days as a countdown
        n_days = int(n_days)
        date_list = None  # no real dates
    else:
        n_days = (exam_d - today_date).days
        if n_days <= 0:
            # Exam is today or past — all review
            return _final_review_plan(state, goal, today, exam_date, daily_budget)
        date_list = None  # will build from dates

    ordered = _prioritized_chapters(state, bank, bp, exam)
    todo = [ch for ch, _ in ordered]
    reasons = {ch["n"]: why for ch, why in ordered}
    n_todo = len(todo)
    overdue, due_today = _due_reviews(state, today)
    open_mistakes = [qid for qid in _open_mistake_qids(state) if qid not in set(overdue + due_today)]

    # No todo chapters left — plan is just review
    if n_todo == 0:
        return _final_review_plan(state, goal, today, exam_date, daily_budget)

    # Compute chapters per day and study days
    _, study_days = _chapters_per_day(n_todo, n_days, goal)

    # Build day plans
    plans = []
    ch_idx = 0
    review_idx = 0

    # Distribute chapters evenly across study_days using divmod
    base_per_day, extra_days = divmod(n_todo, study_days) if study_days > 0 else (0, 0)

    for day_num in range(1, n_days + 1):
        day_date = None
        if exam_d:
            day_date = (today_date + _dt.timedelta(days=day_num - 1)).isoformat()

        tasks = []
        day_note_parts = []
        remaining = daily_budget

        # 1. Due reviews first (overdue + due today)
        day_reviews = []
        if day_num == 1:
            # On day 1, include all currently overdue + due today
            day_reviews = list(dict.fromkeys(overdue + due_today))
        # For subsequent days, we don't know future review dates yet
        # (they get set when the student actually answers)

        if day_reviews:
            # Never silently create a task longer than the student's available time.
            total_reviews = len(day_reviews)
            review_budget = remaining if not n_todo else max(6, int(remaining * (0.6 if goal == "long" else 0.4)))
            n_review = min(len(day_reviews), min(remaining, review_budget) // 6)
            day_reviews = day_reviews[:n_review]
            if n_review < total_reviews:
                day_note_parts.append("复测尚有 %d 道未排" % (total_reviews - n_review))
        if day_reviews:
            review_minutes = min(remaining, max(6, 6 * len(day_reviews)))
            tasks.append(Task(
                kind="due_review",
                qids=day_reviews,
                why_now=("到期复测：%d 道题需在今天复测（逾期 %d + 今日 %d）"
                         % (len(day_reviews), len(overdue), len(due_today)))
                        if day_num == 1 else
                        "到期复测：今日到期题目",
                pass_criteria="每道题独立作答正确（无提示）",
                estimated_minutes=review_minutes,
            ))
            day_note_parts.append("复测 %d" % len(day_reviews))
            remaining -= review_minutes

        # 2. New chapters (only on study days)
        is_study_day = (day_num <= study_days) if study_days > 0 else False

        day_chapters = []
        if is_study_day and ch_idx < n_todo:
            day_count = base_per_day + (1 if day_num <= extra_days else 0)
            while len(day_chapters) < day_count and ch_idx < n_todo and remaining:
                if tasks and remaining < 15:
                    break
                ch = todo[ch_idx]
                time_needed = min(25, remaining)
                if not bank or any(q.get("chapter") == ch["n"] for q in bank):
                    criteria = "完成对应例题；材料原题独立做对 1 道并核对步骤"
                else:
                    criteria = "读完对应例题并口述步骤；无材料题则保持未测"
                tasks.append(Task(
                    kind="new_chapter",
                    chapter=ch["n"],
                    why_now=reasons[ch["n"]],
                    detail=ch["title"],
                    pass_criteria=criteria,
                    estimated_minutes=time_needed,
                ))
                remaining -= time_needed
                day_chapters.append(ch)
                ch_idx += 1
            if day_chapters:
                day_note_parts.append(", ".join("ch%d" % ch["n"] for ch in day_chapters))

        # 3. Open mistakes (if not too many new chapters)
        n_new = sum(1 for t in tasks if t.kind == "new_chapter")
        if open_mistakes and remaining >= 8 and n_new == 0:
            # Add a few open mistakes to review alongside new chapters
            mistake_slice = open_mistakes[review_idx:review_idx + 3]
            if mistake_slice:
                tasks.append(Task(
                    kind="mistake_review",
                    qids=mistake_slice,
                    why_now="错题复习：趁记忆还新，重做近期错题",
                    pass_criteria="独立答对即为通过；仍错则记录错因并缩短复测间隔",
                    estimated_minutes=min(remaining, max(8, len(mistake_slice) * 6)),
                ))
                remaining -= tasks[-1].estimated_minutes
                review_idx += len(mistake_slice)
                day_note_parts.append("错题 %d" % len(mistake_slice))

        # 4. Review days (days after study_days with no new chapters)
        if not is_study_day and not tasks and remaining:
            tasks.append(Task(
                kind="due_review",
                why_now="预留复测日；实际到期题将在作答后更新",
                pass_criteria="到期复测全部独立答对",
                estimated_minutes=min(15, remaining),
            ))
            remaining -= tasks[-1].estimated_minutes
            day_note_parts.append("复习日")

        # 5. Cheatsheet on last day
        if day_num == n_days and remaining >= 5:
            tasks.append(Task(
                kind="cheatsheet",
                why_now="最后一天：生成小抄，集中复习错题",
                pass_criteria="小抄已生成，错题至少过一遍",
                estimated_minutes=min(10, remaining),
            ))
            remaining -= tasks[-1].estimated_minutes
            day_note_parts.append("小抄")

        if daily_budget < 15:
            day_note_parts.append("时间不足：短任务，建议调整备考时间")
        note = " · ".join(day_note_parts) if day_note_parts else ""
        plans.append(DayPlan(
            date_str=day_date,
            day_index=day_num,
            tasks=tasks,
            note=note,
        ))

    if ch_idx < n_todo:
        warning = "时间不足：尚有 %d 章未排，请增加时间或缩小确认范围" % (n_todo - ch_idx)
        plans[0].note = " · ".join(filter(None, [plans[0].note, warning]))
    return plans


def _single_day_plan(state, goal, today, bank=None, bp=None, exam=None, daily_budget=25):
    """When no exam date is set, return a simple one-day plan."""
    ordered = _prioritized_chapters(state, bank, bp, exam)
    tasks = []
    remaining = daily_budget
    overdue, due = _due_reviews(state, today)
    review_ids = list(dict.fromkeys(overdue + due))
    # No exam date must not disable evidence-driven spaced review.
    review_budget = remaining if not ordered else max(6, int(remaining * (0.6 if goal == "long" else 0.4)))
    selected = review_ids[:max(0, min(remaining, review_budget) // 6)]
    if selected:
        minutes = 6 * len(selected)
        tasks.append(Task(kind="due_review", qids=selected,
                          why_now="已到期的独立复测；未知考期不影响复测安排",
                          pass_criteria="逐题提交新原答并核对；未通过可结束为待巩固",
                          estimated_minutes=minutes))
        remaining -= minutes
    for ch, why in ordered:
        if remaining <= 0 or (tasks and remaining < 15):
            break
        minutes = min(25, remaining)
        tasks.append(Task(
            kind="new_chapter",
            chapter=ch["n"],
            why_now=why,
            detail=ch["title"],
            pass_criteria="完成对应例题，独立做对 1 道材料题；无题则标未测",
            estimated_minutes=minutes,
        ))
        remaining -= minutes
    om = [qid for qid in _open_mistake_qids(state) if qid not in set(review_ids)]
    if om and remaining >= 8:
        tasks.append(Task(
            kind="mistake_review",
            qids=om[:5],
            why_now="错题复习",
            pass_criteria="独立答对",
            estimated_minutes=min(remaining, 15),
        ))
    note = "无考试日期，先安排当天任务"
    if daily_budget < 15:
        note += " · 时间不足：短任务，建议调整备考时间"
    return [DayPlan(date_str=today, day_index=1, tasks=tasks, note=note)]


def _final_review_plan(state, goal, today, exam_date, daily_budget=25):
    """All chapters done or exam is today — pure review plan."""
    tasks = []
    om = _open_mistake_qids(state)
    overdue, due_today = _due_reviews(state, today)
    all_reviews = list(dict.fromkeys(overdue + due_today + om))
    if all_reviews and daily_budget >= 6:
        minutes = min(daily_budget, max(8, 6 * min(3, len(all_reviews))))
        tasks.append(Task(
            kind="due_review",
            qids=all_reviews[:min(3, max(1, minutes // 6))],
            why_now="考前复习：到期复测 + 待复习错题",
            pass_criteria="全部独立答对",
            estimated_minutes=minutes,
        ))
    left = daily_budget - sum(t.estimated_minutes or 0 for t in tasks)
    if left >= 5:
        tasks.append(Task(
            kind="cheatsheet",
            why_now="生成小抄，集中复习",
            pass_criteria="小抄已生成，错题至少过一遍",
            estimated_minutes=min(10, left),
        ))
    date_str = today
    note = "考前复习" if daily_budget >= 15 else "考前复习 · 时间不足，建议调整备考时间"
    return [DayPlan(date_str=date_str, day_index=1, tasks=tasks, note=note)]


# ------------------------------------------------------------------ rendering

def render_plan(plans, state, zh=True):
    """Render a list of DayPlans as plain text lines for CLI output.

    Returns a list of strings (one per line).
    """
    lines = []
    total = len(state["chapters"])
    done = _done_count(state)
    goal = state.get("goal", "pass")
    goal_labels = {
        "pass": "求过" if zh else "pass",
        "high": "查漏" if zh else "high score",
        "long": "长期" if zh else "long-term",
    }

    exam_date = state.get("exam_date")
    d_left = days_to_exam(exam_date)

    # Header
    if d_left is not None:
        date_str = " (%s)" % exam_date if exam_date else ""
        lines.append("%s: %s %d %s%s · %d/%d %s · %s: %s" % (
            "学习计划" if zh else "Study plan",
            "距考试" if zh else "exam in", d_left,
            "天" if zh else "day(s)", date_str,
            done, total,
            "章已完成" if zh else "chapters done",
            "目标" if zh else "goal",
            goal_labels.get(goal, goal),
        ))
    else:
        lines.append("%s: %d/%d %s · %s: %s" % (
            "学习计划" if zh else "Study plan",
            done, total,
            "章已完成" if zh else "chapters done",
            "目标" if zh else "goal",
            goal_labels.get(goal, goal),
        ))

    # Due reviews summary
    today_iso = _today().isoformat()
    overdue, due_today = _due_reviews(state, today_iso)
    if overdue or due_today:
        lines.append("  %s: %d %s, %d %s" % (
            "到期复测" if zh else "Due reviews",
            len(overdue), "逾期" if zh else "overdue",
            len(due_today), "今日到期" if zh else "due today",
        ))

    lines.append("")

    # Long-term planning is revised after each attempt. Showing every day at
    # once adds noise and wrongly implies later review dates are already fixed.
    for plan in plans[:4]:
        # Day header
        if plan.date_str:
            lines.append("  %s %s: %s" % (
                "第 %d 天" % plan.day_index if zh else "Day %d" % plan.day_index,
                plan.date_str, plan.note))
        else:
            lines.append("  %s: %s" % (
                "第 %d 天" % plan.day_index if zh else "Day %d" % plan.day_index,
                plan.note))

        # Only today's task needs its complete why/standard; future days are
        # a short preview that may change after the next independent attempt.
        if plan.day_index != 1:
            continue

        # Tasks
        for t in plan.tasks:
            crit = "  → %s" % t.pass_criteria if t.pass_criteria else ""
            duration = " [%d %s]" % (t.estimated_minutes, "分钟" if zh else "min") if t.estimated_minutes is not None else ""
            if t.kind == "new_chapter":
                ch_info = ""
                for c in state["chapters"]:
                    if c["n"] == t.chapter:
                        ch_info = c["title"]
                        break
                lines.append("    %s ch%d %s%s — %s%s" % (
                    "新章节" if zh else "New", t.chapter,
                    ch_info[:28], duration, t.why_now, crit))
            elif t.kind == "due_review":
                if t.qids:
                    lines.append("    %s (%d %s)%s — %s%s" % (
                        "到期复测" if zh else "Due review",
                        len(t.qids), "道" if zh else "q",
                        duration, t.why_now, crit))
                else:
                    lines.append("    %s%s — %s%s" % (
                        "复习日" if zh else "Review day",
                        duration, t.why_now, crit))
            elif t.kind == "mistake_review":
                lines.append("    %s (%d %s)%s — %s%s" % (
                    "错题复习" if zh else "Mistake review",
                    len(t.qids), "道" if zh else "q",
                    duration, t.why_now, crit))
            elif t.kind == "cheatsheet":
                lines.append("    %s%s — %s%s" % (
                    "生成小抄" if zh else "Cheatsheet",
                    duration, t.why_now, crit))

        # Today's target summary
        if plan.day_index == 1:
            ch_list = ", ".join("ch%d" % c for c in plan.chapters)
            review_list = plan.review_count
            target_parts = []
            if ch_list:
                target_parts.append(ch_list)
            if review_list:
                target_parts.append("%s %d" % ("复测" if zh else "review", review_list))
            lines.append("")
            lines.append("  %s: %s" % (
                "今日目标" if zh else "Today's target",
                " · ".join(target_parts) if target_parts else "复习"))

    if len(plans) > 4:
        lines.append("  …另有 %d 天，按作答结果滚动调整" % (len(plans) - 4)
                     if zh else "  …%d more days; revise after each attempt" % (len(plans) - 4))
    return lines
