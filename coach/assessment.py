# -*- coding: utf-8 -*-
"""Source-bound assessment contracts, frozen independently of the student's answer.

Coverage is a conservative textual check, NOT a semantic grader. The host must
review the complete task and reference before approving a rubric. It cannot
silently remove unassessed obligations during grading. No invented point values.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from . import grading, questions


def _error(text):
    from .attempts import AttemptError
    raise AttemptError(text)


def normalize(text):
    """Ignore whitespace/punctuation only; keep operators, letters and numbers."""
    return re.sub(r'[\s，。；、：！？,.!?:;\u3000]+', '', str(text or '')).casefold()


def source(q):
    return copy.deepcopy(q.get('answer_source') or q.get('source') or {})


def fingerprint(contract):
    data = {k: contract[k] for k in ('qid', 'item_version', 'answer_version', 'source', 'criteria')}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def scaffold(q):
    """Conservative draft: each reference clause is an obligation, not a score.

    Equations are kept intact unless the source itself uses Chinese punctuation
    or a semicolon. These units require host review; we do not infer pedagogy.
    """
    reference = (q.get('answer') or '').strip()
    clauses = [s.strip() for s in re.split(r'[，；。\n]+', reference) if normalize(s)]
    if not clauses:
        clauses = [reference] if reference else []
    return {'schema': 'crushexam-rubric-v2', 'qid': q['id'],
            'item_version': questions.question_version(q),
            'answer_version': questions.question_answer_version(q),
            'source': source(q), 'question_quote': q.get('question', ''),
            'coverage_confirmed': False,
            'criteria': [{'id': 'r%d' % (i + 1), 'label': '参考要点%d' % (i + 1),
                          'reference_quote': clause} for i, clause in enumerate(clauses)],
            'approval': 'draft_reference_segments'}


def read_json(path):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > 100000:
        _error('评分文件不存在或过大。')
    value = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        _error('评分文件必须是JSON对象。')
    return value


def validate_source(raw, q):
    src = raw.get('source')
    ref = source(q)
    if not isinstance(src, dict) or src.get('file') != ref.get('file') or src.get('page') != ref.get('page'):
        _error('评分点必须引用本题参考答案的真实文件与页码。')
    return copy.deepcopy(src)


def uncovered(reference, quotes):
    """All normalized reference characters must be covered by actual quotes.

    We deliberately do not offer a post-answer `ignore missing` escape hatch.
    For bad or verbose references fix the source or leave the attempt unverified.
    """
    text = normalize(reference)
    covered = [False] * len(text)
    for quote in quotes:
        q = normalize(quote)
        if not q or q not in text:
            _error('reference_quote 必须为本题参考答案中的实际片段。')
        start = 0
        while True:
            pos = text.find(q, start)
            if pos < 0:
                break
            covered[pos:pos + len(q)] = [True] * len(q)
            start = pos + 1
    return ''.join(c for c, present in zip(text, covered) if not present)


def validate_contract(raw, q):
    if raw.get('qid') != q['id']:
        _error('评分契约题号不匹配。')
    for field, actual in [('item_version', questions.question_version(q)),
                          ('answer_version', questions.question_answer_version(q))]:
        if raw.get(field) != actual:
            _error('评分契约对应旧题干/旧答案；请重新生成并核对。')
    src = validate_source(raw, q)
    if raw.get('coverage_confirmed') is not True or raw.get('question_quote') != q.get('question', ''):
        _error('需先核对完整题目与全部参考要点，并设置 coverage_confirmed=true。')
    items = raw.get('criteria')
    if not isinstance(items, list) or not 1 <= len(items) <= 60:
        _error('评分契约需包含1～60个完整要点。')
    seen, quotes, clean = set(), [], []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip() or item['id'] in seen:
            _error('每个评分要点必须有唯一的非空id。')
        seen.add(item['id'])
        if any(key in item for key in ('status', 'score', 'points', 'max_points', 'student_quote')):
            _error('冻结契约只定义要求；不得包含学生评价、答案或虚构分值。')
        if not isinstance(item.get('label'), str) or not item['label'].strip():
            _error('每个评分要点必须命名。')
        quote = item.get('reference_quote')
        if not isinstance(quote, str) or not quote.strip():
            _error('每个要点必须提供真实参考片段。')
        quotes.append(quote)
        clean.append({'id': item['id'], 'label': item['label'], 'reference_quote': quote})
    missing = uncovered(q.get('answer'), quotes)
    if missing:
        _error('评分契约未覆盖全部参考要点，不能冻结。未覆盖片段：' + missing[:160])
    result = {'qid': q['id'], 'item_version': questions.question_version(q),
              'answer_version': questions.question_answer_version(q), 'source': src,
              'question_quote': q.get('question', ''), 'criteria': clean,
              'approval': 'host_reviewed_complete', 'coverage_confirmed': True}
    result['contract_id'] = fingerprint(result)
    return result


def freeze(state, q, raw):
    from . import attempts as at
    contract = validate_contract(raw, q)
    existing = state.setdefault('rubric_contracts', {}).get(q['id'])
    if existing and existing.get('contract_id') == contract['contract_id']:
        return existing
    # Do not retrofit requirements to an already submitted/unresolved answer.
    if any(a.get('qid') == q['id'] and a.get('status') in at.UNRESOLVED and a.get('submitted_at')
           for a in state.get('attempts', {}).values()):
        _error('本题已有提交未收束，不能补写评分要求影响旧原答；先暂缓，冻结后用于下一次呈题。')
    contract['frozen_at'] = at.stamp()
    if existing:
        state.setdefault('rubric_archive', []).append(copy.deepcopy(existing))
    state['rubric_contracts'][q['id']] = contract
    # Presented but not yet submitted: preparation is still pre-answer.
    for a in state.get('attempts', {}).values():
        if a.get('qid') == q['id'] and a.get('status') == 'presented':
            a['rubric_contract'] = copy.deepcopy(contract)
    at.event(state, 'rubric_frozen', qid=q['id'], contract_id=contract['contract_id'])
    return contract


def snapshot(state, q):
    c = state.get('rubric_contracts', {}).get(q['id'])
    if c and c.get('item_version') == questions.question_version(q) and c.get('answer_version') == questions.question_answer_version(q):
        return copy.deepcopy(c)
    c = scaffold(q)
    c['contract_id'] = fingerprint(c)
    return c


def assess(raw, q, a):
    """Overlay ratings onto the frozen obligations, never replace obligations.

    Legacy unregistered rubric files can still record negative/partial feedback.
    They cannot produce whole-question success. Omitted obligations are explicit
    `unassessed`, not `missing` (we do not know whether the learner omitted them).
    """
    validate_source(raw, q)
    items = raw.get('criteria')
    if not isinstance(items, list) or not 1 <= len(items) <= 60:
        _error('评分记录需包含1～60项。')
    c = copy.deepcopy(a.get('rubric_contract') or scaffold(q))
    for field, actual in [('item_version', questions.question_version(q)), ('answer_version', questions.question_answer_version(q))]:
        if c.get(field) != actual:
            _error('本次作答冻结的评分契约已过期，不得套用新答案。')
    approved = c.get('approval') == 'host_reviewed_complete'
    if approved and raw.get('contract_id') != c.get('contract_id'):
        _error('评分记录必须携带本次作答冻结的 contract_id。')
    if approved and raw.get('attempt_id') != a['id']:
        _error('评分记录必须绑定本次 attempt_id，不能复用另一份作答的评分。')
    seen, ratings = set(), []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip() or item['id'] in seen:
            _error('评分记录id无效或重复。')
        seen.add(item['id'])
        if item.get('status') not in ('met', 'partial', 'missing', 'uncertain'):
            _error('状态必须为met/partial/missing/uncertain。')
        if any(key in item for key in ('score', 'points', 'max_points')):
            _error('逐点只记录完成状态，不编造数值分值。')
        quote = item.get('reference_quote')
        if not isinstance(quote, str) or not normalize(quote) or normalize(quote) not in normalize(q.get('answer')):
            _error('评分点必须引用真实参考片段。')
        if approved:
            definition = next((x for x in c['criteria'] if x['id'] == item['id']), None)
            if not definition or quote != definition['reference_quote']:
                _error('不能增删或改变冻结的评分要求；只填写其状态。')
            if item.get('label') not in (None, definition['label']):
                _error('不能在判分时改写评分要点名称。')
            if item['status'] in ('met', 'partial'):
                student = item.get('student_quote')
                if not isinstance(student, str) or not student.strip() or student not in a.get('raw_answer', ''):
                    _error('已完成或部分完成必须引用首次原答中的实际片段；不得替学生补答案。')
            value = dict(definition, status=item['status'], student_quote=item.get('student_quote'), note=item.get('note', ''))
        else:
            value = copy.deepcopy(item)
        ratings.append(value)
    if approved:
        byid = {i['id']: i for i in ratings}
        ratings = [byid.get(i['id'], dict(i, status='unassessed')) for i in c['criteria']]
    else:
        # Legacy feedback remains useful, but absent reference content is visible.
        missing = uncovered(q.get('answer'), [i['reference_quote'] for i in ratings])
        if missing:
            ratings.append({'id': '__unassessed_reference__', 'label': '其余参考要点尚未核对',
                            'status': 'unassessed', 'uncovered_text': missing})
    has_negative = any(i['status'] in ('missing', 'partial') for i in ratings)
    pending = any(i['status'] in ('unassessed', 'uncertain') for i in ratings)
    result = 'wrong' if has_negative else 'right' if approved and not pending else None
    return {'source': source(q), 'contract_id': c.get('contract_id'), 'attempt_id': a['id'],
            'criteria': ratings, 'coverage_status': 'complete' if approved and not pending else 'incomplete_or_unapproved',
            'assessor': 'host_manual_against_frozen_source', 'numeric_score': None,
            'result': result, 'note': raw.get('note', '')}


def reasoning_required(a, q):
    """Detect an explanation to review, not whether that explanation is true."""
    if grading.grade(a.get('graded_response') or '', q.get('answer') or '').get('kind') not in ('single', 'multi', 'choice', 'true_false'):
        return False
    raw = (a.get('raw_answer') or '').strip()
    compact = re.sub(r'[\s，。,:：;；、.()（）]+', '', raw)
    compact = re.sub(r'^(?:我选|选择|选|答案|答|answer|option)', '', compact, flags=re.I)
    option_only = bool(re.fullmatch(r'[A-Ha-h]+|对|错|正确|错误|true|false', compact, re.I))
    return not option_only or a.get('confidence') == 'low'


def method_status(a, q):
    review = a.get('reasoning_review')
    if review:
        return review['verdict']
    return 'pending' if reasoning_required(a, q) else 'not_checked'


def verify_reason(state, a, q, verdict, quote, ref_quote, note):
    from . import attempts as at
    at.verify_version(a, q)
    if a.get('status') not in ('submitted', 'awaiting_manual', 'graded'):
        _error('需先保存可核对的首次原答。')
    if not isinstance(quote, str) or quote not in a.get('raw_answer', '') or len(quote.strip()) < 3:
        _error('理由核对只能引用首次原答中的实际解释（不是后来补答或单个选项）。')
    if not isinstance(ref_quote, str) or not normalize(ref_quote) or normalize(ref_quote) not in normalize(q.get('answer')):
        _error('需引用本题参考答案中实际存在的依据；参考只有字母时保持方法待核验。')
    if len(normalize(ref_quote)) < 3 or not note or not note.strip():
        _error('参考依据或核对说明不足；不能凭一个答案字母证明方法。')
    if verdict not in ('met', 'incorrect', 'uncertain'):
        _error('理由核对状态无效。')
    if a.get('reasoning_review'):
        old = a['reasoning_review']
        if (old['verdict'], old['student_quote'], old['reference_quote'], old['note']) == (verdict, quote, ref_quote, note):
            return False
        _error('首次理由核对已冻结，不能覆盖；纠错需另建作答，历史仍可追溯。')
    review = {'verdict': verdict, 'student_quote': quote, 'reference_quote': ref_quote,
              'note': note, 'source': source(q), 'reviewed_at': at.stamp(), 'assessor': 'host_manual'}
    a['reasoning_review'] = review
    a['method_status'] = verdict
    a['method_pending'] = verdict in ('pending', 'uncertain')
    for h in state.get('history', []):
        if h.get('attempt_id') == a['id']:
            h.update(reasoning_review=copy.deepcopy(review), method_status=verdict, method_pending=a['method_pending'])
    at.event(state, 'reasoning_reviewed', attempt_id=a['id'], verdict=verdict)
    return True
