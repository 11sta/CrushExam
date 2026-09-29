# -*- coding: utf-8 -*-
"""Evidence levels and spaced review scheduling.

Evidence levels (borrowed from ko-lesson mastery levels, adapted to 5):
  untested  — never attempted
  hinted    — answered correctly but had seen teaching/hints first
  immediate — answered correctly without hints, same session
  delayed   — answered correctly on a delayed re-test (≥1 day later)
  transfer  — answered a novel variant / new context correctly
"""
import datetime as _dt

LEVELS = ["untested", "hinted", "immediate", "delayed", "transfer"]

LEVEL_LABELS = {
    "untested": ("未测", "untested"),
    "hinted": ("提示下完成", "hinted"),
    "immediate": ("即时独立", "immediate"),
    "delayed": ("隔日同题独立", "same-item later-day"),
    "transfer": ("异题验证（查看类别）", "cross-item verification"),
}


def label(level, zh=True):
    return LEVEL_LABELS.get(level, (level, level))[0 if zh else 1]


def is_higher(new, old):
    """Is `new` a higher evidence level than `old`?"""
    try:
        return LEVELS.index(new) > LEVELS.index(old)
    except (ValueError, IndexError):
        return False


def best(levels):
    """Return the highest evidence level from a list."""
    result = "untested"
    for lv in levels:
        if is_higher(lv, result):
            result = lv
    return result


def compute_review_date(current_level, days_ahead=1):
    """Compute the next review date based on current evidence level.

    This is a product default, not a universal optimal interval.
    - untested / hinted: review next study day
    - immediate: review after 1 day (verify it sticks)
    - delayed: review after 3 days (extend interval)
    - transfer: review after 7 days (well-established)
    """
    intervals = {
        "untested": 1,
        "hinted": 1,
        "immediate": 1,
        "delayed": 3,
        "transfer": 7,
    }
    days = intervals.get(current_level, 1)
    return (_dt.date.today() + _dt.timedelta(days=days)).isoformat()


def shorten_review_date(date_str, current_level):
    """Shorten the review interval after a failed re-test."""
    if not date_str:
        return compute_review_date("immediate")
    try:
        d = _dt.date.fromisoformat(date_str)
        # Push to tomorrow for a failed re-test
        return (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    except ValueError:
        return compute_review_date(current_level)


def is_overdue(review_date, today=None):
    """Check if a review date is past due."""
    if not review_date:
        return False
    if today is None:
        today = _dt.date.today().isoformat()
    return review_date <= today


def is_due_today(review_date, today=None):
    """Check if a review date is exactly today."""
    if not review_date:
        return False
    if today is None:
        today = _dt.date.today().isoformat()
    return review_date == today


def classify_attempt(is_independent, is_correct, saw_hint=False, is_delayed=False, is_variant=False):
    """Classify an attempt into an evidence level.

    is_independent: student answered without seeing the solution first
    is_correct: student got the right answer
    saw_hint: student had seen teaching/hints before answering
    is_delayed: this is a re-test on a different day
    is_variant: this is a novel variant / new context question
    """
    if not is_correct:
        return "untested"  # wrong answer doesn't advance evidence
    if is_variant and is_independent and not saw_hint:
        return "transfer"
    if is_delayed and is_independent and not saw_hint:
        return "delayed"
    if is_independent and not saw_hint:
        return "immediate"
    if saw_hint:
        return "hinted"
    return "hinted"  # no independent evidence must not become independent by default

# v1.7: orthogonal descriptive dimensions. No blanket "strong" label.
TRANSFER_LABELS = {'parameter': '参数变式', 'representation': '表示变化',
                   'context': '情境迁移', 'unclassified': '异题关系待细分'}


def method_ready(record):
    """Outcome credit is preserved even when the reasoning is still disputed."""
    return (record.get('method_status') not in ('pending', 'uncertain', 'incorrect')
            and record.get('assessment_coverage') != 'legacy_unverified')


def attempt_label(record, zh=True):
    level = record.get('evidence_level', 'untested')
    if level == 'transfer':
        kind = record.get('transfer_kind') or 'unclassified'
        value = (TRANSFER_LABELS.get(kind, '异题关系待细分') + '完成（仅限本题）') if zh else kind + ' verification (this item only)'
    elif level == 'delayed':
        value = '隔日同题复测（非新题验证）' if zh else 'Later-day same-item retest (not unseen-item skill)'
    else:
        value = label(level, zh)
    if not method_ready(record):
        value += '；选项得分保留，方法待核验' if zh else '; answer credit kept, reasoning unresolved'
    return value


def observation(record):
    if record.get('result') in ('wrong', 'skip') or record.get('method_status') == 'incorrect':
        return 'gap'
    if not method_ready(record):
        return 'method_pending'
    independent = record.get('is_independent', record.get('independent', False))
    if not independent and record.get('evidence_level') not in ('immediate', 'delayed', 'transfer'):
        return 'hinted'
    if record.get('evidence_level') == 'delayed':
        return 'retention'
    if record.get('evidence_level') == 'transfer':
        return 'variation'
    return 'immediate'


def summarize(qids, latest):
    """One aggregation used by text, HTML and scheduling. Latest per item only.

    Any unresolved incorrect item wins over another item's earlier success.
    Historical maximum remains separate; no sample proves general mastery.
    """
    ids = set(qids)
    records = [latest[q] for q in ids if q in latest]
    counts = {k: 0 for k in ('gap', 'method_pending', 'hinted', 'immediate', 'retention', 'variation')}
    kinds = {k: 0 for k in TRANSFER_LABELS}
    for h in records:
        counts[observation(h)] += 1
        if observation(h) == 'variation':
            kinds[h.get('transfer_kind') if h.get('transfer_kind') in kinds else 'unclassified'] += 1
    unseen = sum(h.get('novelty') == 'first_unseen' and h.get('result') == 'right'
                 and h.get('is_independent', False) and method_ready(h) for h in records)
    untested = len(ids) - len(records)
    if counts['gap']:
        status, strength = 'gap', 'gap'
    elif counts['method_pending']:
        status, strength = 'retest', 'method_pending'
    elif not records:
        status, strength = 'untested', 'untested'
    elif counts['hinted']:
        status, strength = 'retest', 'weak'
    elif untested or counts['immediate']:
        status, strength = 'retest', 'medium'
    elif counts['variation']:
        status, strength = 'delayed', 'variation'
    else:
        status, strength = 'delayed', 'retention'
    return dict(total=len(ids), n=len(records), tested=len(records),
                independent=counts['immediate'] + counts['retention'] + counts['variation'],
                wrong=counts['gap'], hinted=counts['hinted'], method_pending=counts['method_pending'],
                untested=untested, status=status, strength=strength,
                retention=counts['retention'], variation=counts['variation'],
                transfer_kinds=kinds, unseen_independent=unseen)
