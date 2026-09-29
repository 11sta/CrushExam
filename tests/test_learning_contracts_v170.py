"""Learning-effect probe regressions: synthetic sources, not human effect sizes.

P01-P13 map to the prior v1.6.0 report. Extra contracts test the *new* gates'
positive paths, recovery paths and immutable source/answer boundaries.
"""
import copy
import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from test_reliability_v160 import FlowFixture
from coach import attempts as at, tasks, assessment, blueprint, ability_view, evidence, state as st, questions


class LearningContracts(FlowFixture):
    def write(self, name, data):
        path = self.base / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return path

    def freeze(self, q):
        draft = assessment.scaffold(q)
        draft['coverage_confirmed'] = True
        self.run_cmd('rubric', 'freeze', q['id'], '--file', self.write('contract.json', draft))
        return self.state()['rubric_contracts'][q['id']]

    def ratings(self, q, values, quotes=None):
        a = at.lookup(self.state(), q['id'])
        c = a['rubric_contract']
        items = [dict(i, status=v, student_quote=(quotes or {}).get(i['id'], i['reference_quote']))
                 for i, v in zip(c['criteria'], values)]
        return {'source': assessment.source(q), 'contract_id': c['contract_id'], 'attempt_id': a['id'], 'criteria': items}

    def guided(self):
        self.planned()
        self.run_cmd('goto', '1', '--restart')
        self.run_cmd('next'); self.run_cmd('next')
        self.assertEqual(tasks.current(self.state())['phase'], 'awaiting_step')
        return tasks.current(self.state())

    def assess_step(self, verdict='met', text='出栈后要删除栈顶元素，保留下面的元素。'):
        self.run_cmd('task', 'note', '--note', text)
        t = tasks.current(self.state())
        q = next(q for q in self.bank() if q['id'] == t['checkpoint_qid'])
        self.run_cmd('task', 'assess', '--step-id', t['pending_step_id'], '--verdict', verdict,
                     '--quote', text, '--reference-quote', q['answer'], '--note', '根据资料例题逐项核对学生补出的步骤。')

    def test_P01_correct_option_with_unchecked_reason_does_not_pass_task(self):
        self.planned(); q = self.q()
        self.run_cmd('quiz', '--qid', q['id'])
        raw = 'B，因为栈是先进先出。'
        self.run_cmd('submit', q['id'], raw, '--confidence', 'low')
        self.run_cmd('clarify', q['id'], 'B')
        self.run_cmd('grade', q['id'])
        h = self.state()['history'][-1]
        self.assertEqual((h['result'], h['response'], h['method_status']), ('right', raw, 'pending'))
        self.assertEqual(tasks.current(self.state())['phase'], 'method_check')
        self.assertNotEqual(self.state()['tasks'][0]['status'], 'passed')
        rows, _ = blueprint.kc_stats(self.state(), self.bank(), None)
        self.assertEqual(rows[0]['strength'], 'method_pending')

    def test_low_confidence_keeps_answer_credit_but_needs_followup(self):
        self.planned(); q = self.q()
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], 'B', '--confidence', 'low')
        self.run_cmd('grade', q['id'])
        self.assertEqual(self.state()['history'][-1]['result'], 'right')
        self.assertEqual(tasks.current(self.state())['phase'], 'method_check')
        self.run_cmd('next'); self.assertFalse(at.active(self.state()))
        self.run_cmd('task', 'skip-check', '--note', '学生选择下一道未见原题验证，不补写首次理由。')
        self.run_cmd('next'); self.assertTrue(at.active(self.state()))

    def test_P02_no_step_response_cannot_advance_by_next_or_quiz(self):
        self.guided()
        for _ in range(3):
            self.run_cmd('next')
            self.assertFalse(at.active(self.state()))
            self.assertEqual(tasks.current(self.state())['phase'], 'awaiting_step')
        self.run_cmd('quiz', expected=4)
        self.run_cmd('quiz', '--qid', self.q(index=2)['id'], expected=4)
        self.assertFalse(self.state()['history'])

    def test_P03_confusion_is_not_a_pass_and_requires_small_step_support(self):
        self.guided()
        self.run_cmd('task', 'note', '--note', '我还是不会，不知道出栈后剩下什么。')
        self.run_cmd('next')
        t = tasks.current(self.state())
        self.assertEqual(t['phase'], 'step_check')
        self.assertFalse(at.active(self.state()))
        self.run_cmd('task', 'assess', '--step-id', t['pending_step_id'], '--verdict', 'uncertain',
                     '--quote', '我还是不会', '--reference-quote', self.q()['answer'], '--note', '先核对出栈后删除哪个元素。')
        self.assertEqual(tasks.current(self.state())['phase'], 'remediation')
        out = self.run_cmd('next')
        self.assertIn('更小', out)
        self.assertEqual(tasks.current(self.state())['phase'], 'awaiting_step')

    def test_guided_success_requires_record_then_review_and_uses_another_question(self):
        old = self.guided(); guided = old['checkpoint_qid']
        self.assess_step()
        self.assertEqual(tasks.current(self.state())['phase'], 'independent')
        self.run_cmd('next')
        a = at.active(self.state())
        self.assertNotEqual(a['qid'], guided)
        q = next(q for q in self.bank() if q['id'] == a['qid'])
        self.run_cmd('submit', q['id'], q['answer']); self.run_cmd('grade', q['id'])
        self.assertEqual(self.state()['tasks'][0]['status'], 'passed')
        self.assertEqual(self.state()['history'][-1]['novelty'], 'first_unseen')

    def test_three_failed_guided_cycles_end_without_infinite_loop(self):
        self.guided()
        for _ in range(3):
            self.assess_step('incorrect', '我还把出栈当作只读没有删除。')
            self.run_cmd('next')
        t = self.state()['tasks'][0]
        self.assertEqual(t['status'], 'needs_work')
        self.assertFalse(at.active(self.state()))
        self.assertEqual(len(t['learner_steps']), 3)

    def test_guided_step_cannot_be_overwritten_before_review(self):
        self.guided()
        self.run_cmd('task', 'note', '--note', '原始步骤一')
        self.run_cmd('task', 'note', '--note', '原始步骤一')
        self.run_cmd('task', 'note', '--note', '改成标准答案', expected=4)
        self.assertEqual(len(tasks.current(self.state())['learner_steps']), 1)

    def test_guided_assessment_must_bind_real_step_and_source(self):
        self.guided(); self.run_cmd('task', 'note', '--note', '原始步骤')
        t = tasks.current(self.state())
        for step, quote, ref in [('wrong-id', '原始步骤', 'B'), (t['pending_step_id'], '编造', 'B'),
                                 (t['pending_step_id'], '原始步骤', '虚构参考答案')]:
            self.run_cmd('task', 'assess', '--step-id', step, '--verdict', 'met', '--quote', quote,
                         '--reference-quote', ref, '--note', '核对', expected=4)
        self.assertEqual(tasks.current(self.state())['phase'], 'step_check')

    def test_explicit_skip_of_guided_step_is_audited_not_mastery(self):
        self.guided(); self.run_cmd('task', 'skip-check', expected=4)
        self.run_cmd('task', 'skip-check', '--note', '学生明确希望直接尝试新题。')
        t = tasks.current(self.state())
        self.assertEqual(t['phase'], 'independent')
        self.assertEqual(t['status'], 'active')
        self.assertTrue(t['skipped_checks'])
        self.assertFalse(self.state()['history'])

    def test_waiting_step_can_pause_resume_and_finish(self):
        self.guided(); old = tasks.current(self.state())['id']
        self.run_cmd('session', 'pause'); self.run_cmd('session', 'resume'); self.run_cmd('next')
        self.assertEqual(tasks.current(self.state())['id'], old)
        self.assertEqual(tasks.current(self.state())['phase'], 'awaiting_step')
        self.run_cmd('task', 'finish', '--status', 'needs_work', '--note', '学生今天结束。')
        self.assertEqual(self.state()['tasks'][0]['status'], 'needs_work')

    def test_P04_one_of_three_legacy_ratings_cannot_be_whole_question_right(self):
        self.planned(); q = self.q(2, 2)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], '空时front=rear。')
        raw = {'source': assessment.source(q), 'criteria': [dict(id='empty', label='判空', status='met', reference_quote='空时front=rear')]}
        self.run_cmd('grade', q['id'], '--rubric', self.write('partial.json', raw), expected=3)
        self.assertFalse(self.state()['history'])
        a = at.lookup(self.state(), q['id'])
        self.assertEqual(a['status'], 'awaiting_manual')
        self.assertTrue(any(i['status'] == 'unassessed' for i in a['rubric']['criteria']))
        self.run_cmd('defer', q['id'])
        self.assertEqual(at.lookup(self.state(), q['id'])['status'], 'deferred')

    def test_rubric_draft_contains_all_three_reference_clauses(self):
        q = self.q(2, 2); out = self.base/'draft.json'
        self.run_cmd('rubric', 'draft', q['id'], '--out', out)
        draft = json.loads(out.read_text())
        self.assertEqual(len(draft['criteria']), 3)
        self.assertFalse(draft['coverage_confirmed'])
        self.assertEqual(draft['question_quote'], q['question'])

    def test_rubric_freeze_rejects_incomplete_reference_coverage(self):
        q = self.q(2, 2); raw = assessment.scaffold(q)
        raw['criteria'] = raw['criteria'][:1]; raw['coverage_confirmed'] = True
        self.run_cmd('rubric', 'freeze', q['id'], '--file', self.write('incomplete.json', raw), expected=4)
        self.assertNotIn(q['id'], self.state().get('rubric_contracts', {}))

    def test_rubric_cannot_be_frozen_retroactively_for_pending_answer(self):
        self.planned(); q = self.q(2, 2)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], '空时front=rear。')
        raw = assessment.scaffold(q); raw['coverage_confirmed'] = True
        self.run_cmd('rubric', 'freeze', q['id'], '--file', self.write('late.json', raw), expected=4)
        self.assertEqual(at.lookup(self.state(), q['id'])['rubric_contract']['approval'], 'draft_reference_segments')

    def test_rubric_may_be_prepared_after_present_but_before_answer(self):
        self.planned(); q = self.q(2, 2); self.run_cmd('quiz', '--qid', q['id'])
        c = self.freeze(q)
        self.assertEqual(at.active(self.state())['rubric_contract']['contract_id'], c['contract_id'])
        self.assertEqual(at.active(self.state())['status'], 'presented')

    def test_frozen_rubric_omitted_ratings_stay_unassessed_not_right(self):
        self.planned(); q = self.q(2, 2); self.freeze(q)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], '空时front=rear。')
        ratings = self.ratings(q, ['met'])
        self.run_cmd('grade', q['id'], '--rubric', self.write('missing.json', ratings), expected=3)
        a = at.lookup(self.state(), q['id'])
        self.assertEqual([c['status'] for c in a['rubric']['criteria']], ['met', 'unassessed', 'unassessed'])
        self.assertFalse(self.state()['history'])

    def test_full_frozen_rubric_accepts_genuine_complete_response(self):
        self.planned(); q = self.q(2, 2); self.freeze(q)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], q['answer'])
        ratings = self.ratings(q, ['met']*3)
        self.run_cmd('grade', q['id'], '--rubric', self.write('full.json', ratings))
        h = self.state()['history'][-1]
        self.assertEqual(h['result'], 'right'); self.assertEqual(h['rubric']['coverage_status'], 'complete')
        self.assertEqual(h['evidence_level'], 'immediate')

    def test_rubric_requires_student_quotes_and_matching_attempt(self):
        self.planned(); q = self.q(2, 2); self.freeze(q)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], '空时front=rear。')
        r = self.ratings(q, ['met']*3)
        self.run_cmd('grade', q['id'], '--rubric', self.write('invented-student.json', r), expected=4)
        r = self.ratings(q, ['met', 'missing', 'missing']); r['attempt_id'] = 'other-attempt'
        self.run_cmd('grade', q['id'], '--rubric', self.write('other.json', r), expected=4)
        self.assertFalse(self.state()['history'])

    def test_freeform_manual_right_does_not_bypass_rubric(self):
        self.planned(); q = self.q(2, 2)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], '空时front=rear。')
        self.run_cmd('answer', q['id'], 'right', '--note', '我觉得全对了', expected=3)
        self.assertFalse(self.state()['history'])

    def test_cannot_rename_frozen_criterion_at_grading(self):
        self.planned(); q = self.q(2, 2); self.freeze(q)
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], q['answer'])
        r = self.ratings(q, ['met']*3); r['criteria'][2]['label'] = '忽略第三问'
        self.run_cmd('grade', q['id'], '--rubric', self.write('rename.json', r), expected=4)

    def test_P05_any_unrepaired_item_keeps_text_and_matrix_in_gap(self):
        self.planned(); base, target = self.q(), self.q(index=2)
        self.attempt(target, 'A')
        self.prior_day(base); self.attempt(base, 'B')
        s = self.state(); rows, mode = blueprint.kc_stats(s, self.bank(), None)
        data, _, _ = ability_view._build_rows(s, self.bank(), rows, mode, True)
        row = next(r for r in rows if r['chapter'] == 1)
        visual = next(r for r in data if r['chapter'] == 1)['summary']
        self.assertEqual(row['strength'], 'gap')
        self.assertEqual(row['status'], visual['status'])
        self.assertEqual(row['wrong'], 1)
        self.assertEqual(row['indep_right'], visual['independent'])

    def test_P06_later_failure_resets_current_evidence(self):
        self.planned(); q = self.q(); self.prior_day(q)
        self.attempt(q, 'B'); self.attempt(q, 'A')
        self.assertEqual(st.current_evidence_level(self.state(), q['id']), 'untested')
        rows, _ = blueprint.kc_stats(self.state(), self.bank(), None)
        self.assertEqual(rows[0]['strength'], 'gap')

    def test_P07_same_item_next_day_is_not_module_strong_or_unseen(self):
        self.planned(); q = self.q(); self.prior_day(q)
        h = self.attempt(q)
        self.assertTrue(h['same_item_retest'])
        self.assertEqual(h['novelty'], 'previously_seen')
        self.assertEqual(h['evidence_level'], 'delayed')
        self.assertIn('非新题', evidence.attempt_label(h))
        row = blueprint.kc_stats(self.state(), self.bank(), None)[0][0]
        self.assertNotEqual(row['strength'], 'strong')
        self.assertEqual(row['unseen_independent'], 0)

    def relation(self, q, base, kind='parameter'):
        path = self.write('kc.json', {'kcs':[{'id':'stack', 'title':'栈', 'chapter':1, 'keywords':['栈'], 'source':'lecture1.txt p.1'}]})
        self.run_cmd('blueprint', '--file', path, '--qmap', base['id']+':stack', q['id']+':stack')
        self.run_cmd('verify-transfer', q['id'], base['id'], '--kc', 'stack', '--kind', kind,
                     '--basis', '对照两道原题，核对其共享规则与任务变化；仅作人工分类。', '--confirmed')

    def test_P08_parameter_variant_has_explicit_type_not_generic_context_mastery(self):
        self.planned(); base, target = self.q(), self.q(index=2)
        self.attempt(base); self.relation(target, base)
        self.run_cmd('quiz', '--qid', target['id']); self.run_cmd('submit', target['id'], 'B')
        self.run_cmd('grade', target['id'], '--transfer-from', base['id'])
        h = self.state()['history'][-1]
        self.assertEqual(h['transfer_kind'], 'parameter')
        self.assertIn('参数变式', evidence.attempt_label(h))
        self.assertNotIn('情境迁移完成', evidence.attempt_label(h))

    def test_P09_unconfirmed_transfer_rejected_but_regular_grade_available(self):
        self.planned(); base, target = self.q(), self.q(index=2); self.attempt(base)
        self.run_cmd('quiz', '--qid', target['id']); self.run_cmd('submit', target['id'], 'B')
        self.run_cmd('grade', target['id'], '--transfer-from', base['id'], expected=4)
        self.run_cmd('grade', target['id'])
        self.assertEqual(self.state()['history'][-1]['evidence_level'], 'immediate')

    def test_target_exposed_on_prior_day_is_not_unseen_transfer(self):
        self.planned(); base, target = self.q(), self.q(index=2); self.attempt(base); self.relation(target, base)
        s = self.state(); s['exposures'].append({'qid':target['id'], 'kind':'solution', 'at':(dt.date.today()-dt.timedelta(days=2)).isoformat()+'T09:00:00'})
        self.save(s)
        self.run_cmd('quiz', '--qid', target['id']); self.run_cmd('submit', target['id'], 'B')
        self.run_cmd('grade', target['id'], '--transfer-from', base['id'], expected=4)
        self.run_cmd('grade', target['id'])
        self.assertEqual(self.state()['history'][-1]['novelty'], 'previously_seen')

    def test_base_last_wrong_cannot_be_hidden_by_old_success_for_transfer(self):
        self.planned(); base, target = self.q(), self.q(index=2); self.attempt(base); self.attempt(base, 'A'); self.relation(target, base)
        self.run_cmd('quiz', '--qid', target['id']); self.run_cmd('submit', target['id'], 'B')
        self.run_cmd('grade', target['id'], '--transfer-from', base['id'], expected=4)

    def test_P10_guided_exposure_remains_assisted_after_explicit_skip(self):
        t = self.guided(); q = next(q for q in self.bank() if q['id'] == t['checkpoint_qid'])
        self.run_cmd('task', 'skip-check', '--note', '学生明确想再试刚才例题。')
        h = self.attempt(q)
        self.assertEqual(h['evidence_level'], 'hinted')
        self.assertFalse(h['is_independent'])

    def test_P11_no_grade_overwrite_even_after_feedback(self):
        self.planned(); q = self.q()
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], 'A'); self.run_cmd('check', q['id'])
        self.run_cmd('grade', q['id'], 'B', expected=4); self.run_cmd('grade', q['id'])
        self.assertEqual(self.state()['history'][-1]['response'], 'A')

    def test_P12_resume_keeps_same_attempt_and_frozen_contract(self):
        self.planned(); q = self.q(2, 2); self.freeze(q); self.run_cmd('quiz', '--qid', q['id'])
        before = at.active(self.state())
        self.run_cmd('session', 'pause'); self.run_cmd('session', 'resume')
        self.assertEqual(at.active(self.state())['id'], before['id'])
        self.assertEqual(at.active(self.state())['rubric_contract'], before['rubric_contract'])

    def test_P13_partial_step_progress_is_visible_without_full_success(self):
        self.planned(); q = self.q(2, 2); self.freeze(q)
        counts = []
        for n in (1, 2):
            text = '，'.join(i['reference_quote'] for i in self.state()['rubric_contracts'][q['id']]['criteria'][:n])
            self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], text)
            r = self.ratings(q, ['met']*n+['missing']*(3-n))
            self.run_cmd('grade', q['id'], '--rubric', self.write('ratings%d.json'%n, r))
            h = self.state()['history'][-1]
            self.assertEqual(h['result'], 'wrong')
            counts.append(sum(i['status']=='met' for i in h['rubric']['criteria']))
        self.assertEqual(counts, [1,2])
        self.assertNotEqual(self.state()['history'][-1]['attempt_id'], self.state()['history'][-2]['attempt_id'])

    def test_new_answer_cannot_be_used_as_original_reason(self):
        self.planned(); q = self.q()
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], 'B'); self.run_cmd('grade', q['id'])
        self.run_cmd('verify-reason', q['id'], '--verdict', 'met', '--quote', '因为后进先出',
                     '--reference-quote', 'B', '--note', '这是学生后来补的理由', expected=4)
        self.assertEqual(self.state()['history'][-1]['response'], 'B')

    def test_reason_review_uses_full_source_and_preserves_option_credit(self):
        self.planned(); bank = self.bank(); q = self.q(); target=next(x for x in bank if x['id']==q['id'])
        target['answer'] = 'B\n栈遵循后进先出，出栈后删除栈顶。'
        (self.ws/'quiz_bank.json').write_text(json.dumps(bank,ensure_ascii=False),encoding='utf-8')
        self.run_cmd('quiz', '--qid', q['id']); self.run_cmd('submit', q['id'], 'B，因为栈先进先出。')
        self.run_cmd('clarify', q['id'], 'B')
        self.run_cmd('verify-reason', q['id'], '--verdict', 'incorrect', '--quote', '栈先进先出',
                     '--reference-quote', '栈遵循后进先出', '--note', '先入先出与参考规则相反。')
        self.run_cmd('grade', q['id'])
        h=self.state()['history'][-1]
        self.assertEqual(h['result'], 'right'); self.assertEqual(h['method_status'], 'incorrect')
        self.assertEqual(blueprint.kc_stats(self.state(), self.bank(), None)[0][0]['strength'], 'gap')

    def test_method_evidence_and_transfer_kind_visible_in_offline_feedback(self):
        self.planned(); q=self.q()
        self.run_cmd('quiz','--qid',q['id']);self.run_cmd('submit',q['id'],'B','--confidence','low');self.run_cmd('grade',q['id']);self.run_cmd('workbench')
        page=(self.ws/'workbench.html').read_text()
        self.assertIn('方法待核验',page)
        self.assertIn('"method_status": "pending"',page)

    def test_v160_migration_backs_up_without_inventing_manual_coverage(self):
        s=self.state(); q=self.q(2,2)
        s.pop('learning_contract_version', None)
        st.record_result(s,q['id'],q['chapter'],'right',evidence_level='immediate',is_independent=True,
                         response='空时front=rear',grading_source='reference_manual')
        path=self.ws/'study_state.json'; path.write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8')
        before=path.read_bytes()
        self.run_cmd('plan','--skip-diagnosis')
        backup=self.ws/'.backups'/'study_state.v7.before-v1.7.0.json'
        self.assertEqual(backup.read_bytes(),before)
        h=self.state()['history'][-1]
        self.assertEqual(h['result'],'right')
        self.assertEqual(h['assessment_coverage'],'legacy_unverified')
        self.assertFalse(evidence.method_ready(h))

    def test_future_learning_schema_is_rejected_without_mutation(self):
        s=self.state();s['learning_contract_version']=99
        path=self.ws/'study_state.json';path.write_text(json.dumps(s),encoding='utf-8');before=path.read_bytes()
        self.run_cmd('status',expected=2)
        self.assertEqual(path.read_bytes(),before)

    def test_changed_source_invalidates_registered_rubric_for_new_attempt(self):
        self.planned();q=self.q(2,2);old=self.freeze(q);bank=self.bank()
        next(x for x in bank if x['id']==q['id'])['answer'] += '另需说明容量限制。'
        (self.ws/'quiz_bank.json').write_text(json.dumps(bank,ensure_ascii=False),encoding='utf-8')
        self.run_cmd('quiz','--qid',q['id'])
        c=at.active(self.state())['rubric_contract']
        self.assertEqual(c['approval'],'draft_reference_segments')
        self.assertNotEqual(c['answer_version'],old['answer_version'])

    def test_rubric_file_cannot_leak_to_unanswered_workbench(self):
        self.planned();q=self.q(2,2);self.freeze(q);self.run_cmd('quiz','--qid',q['id']);self.run_cmd('workbench')
        text=(self.ws/'workbench.html').read_text()
        self.assertNotIn('保留空位用于区分空与满',text)
        self.assertNotIn('reference_quote',text)

    def test_valid_original_reason_review_can_resolve_pending_without_rewriting_score(self):
        self.planned();bank=self.bank();q=self.q()
        next(x for x in bank if x['id']==q['id'])['answer']='B\n栈遵循后进先出，出栈后删除栈顶。'
        (self.ws/'quiz_bank.json').write_text(json.dumps(bank,ensure_ascii=False),encoding='utf-8')
        raw='B，因为栈遵循后进先出。'
        self.run_cmd('quiz','--qid',q['id']);self.run_cmd('submit',q['id'],raw)
        self.run_cmd('clarify',q['id'],'B');self.run_cmd('grade',q['id'])
        before=copy.deepcopy(self.state()['history'][-1])
        self.run_cmd('verify-reason',q['id'],'--verdict','met','--quote','栈遵循后进先出',
                     '--reference-quote','栈遵循后进先出','--note','首次原话与资料规则相符。')
        after=self.state()['history'][-1]
        self.assertEqual(after['response'],before['response'])
        self.assertEqual(after['result'],before['result'])
        self.assertEqual(after['submitted_at'],before['submitted_at'])
        self.assertEqual(after['method_status'],'met')
        self.assertEqual(self.state()['tasks'][0]['status'],'passed')
        self.assertEqual(len(self.state()['history']),1)

    def test_representation_and_context_are_separate_descriptive_evidence(self):
        for kind in ('representation','context'):
            h={'qid':kind,'result':'right','is_independent':True,'evidence_level':'transfer','transfer_kind':kind}
            summary=evidence.summarize([kind],{kind:h})
            self.assertEqual(summary['transfer_kinds'][kind],1)
            self.assertEqual(summary['transfer_kinds']['parameter'],0)
            self.assertNotEqual(summary['strength'],'strong')
            self.assertIn(evidence.TRANSFER_LABELS[kind],evidence.attempt_label(h))

    def test_resume_old_guided_task_reinstates_unverified_checkpoint(self):
        self.planned();s=self.state();t=tasks.current(s)
        t['phase']='independent';t['guided_qids']=[self.q()['id']];t.pop('learning_gate_version',None)
        s.pop('learning_contract_version',None)
        (self.ws/'study_state.json').write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8')
        self.run_cmd('next')
        t=tasks.current(self.state())
        self.assertEqual(t['phase'],'awaiting_step')
        self.assertFalse(at.active(self.state()))
        self.run_cmd('task','skip-check','--note','学生明确跳过旧检查，保留升级记录。')
        self.assertEqual(tasks.current(self.state())['phase'],'independent')

    def test_old_correct_option_wrong_reason_stays_unverified_on_upgrade(self):
        s=self.state();q=self.q();s.pop('learning_contract_version',None)
        st.record_result(s,q['id'],q['chapter'],'right',evidence_level='immediate',is_independent=True,
                         response='B，因为栈先进先出',graded_response='B',confidence='low',grading_source='reference_auto')
        (self.ws/'study_state.json').write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8')
        migrated=self.state()
        self.assertEqual(migrated['history'][-1]['result'],'right')
        self.assertEqual(migrated['history'][-1]['method_status'],'pending')
        self.assertEqual(blueprint.kc_stats(migrated,self.bank(),None)[0][0]['strength'],'method_pending')
