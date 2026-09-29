#!/usr/bin/env python3
"""Actual subprocess reproduction of v1.7 assessment/checkpoint contracts.

Scripted synthetic answers only. No LLM, no human participants and no effect-size
claims. Writes commands, stdout, state-derived assertions and summaries.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from test_reliability_v160 import LESSON, HW


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('output must be a new empty directory')
    out.mkdir(parents=True, exist_ok=True)
    mat, home = out/'synthetic-materials', out/'isolated-home'
    mat.mkdir(); home.mkdir(); ws=mat/'exam-cram'
    for n in LESSON:
        (mat/('lecture%d.txt'%n)).write_text(LESSON[n],encoding='utf-8')
        (mat/('hw%d.txt'%n)).write_text(HW[n],encoding='utf-8')
    env=dict(os.environ,HOME=str(home),USERPROFILE=str(home),PYTHONUTF8='1')
    records, checks = [], []
    def state(): return json.loads((ws/'study_state.json').read_text(encoding='utf-8'))
    def bank(): return json.loads((ws/'quiz_bank.json').read_text(encoding='utf-8'))
    def call(*cmd, expected=0):
        argv=[sys.executable,str(ROOT/'coach.py')]
        if cmd[0]!='setup':argv+=['-w',str(ws)]
        p=subprocess.run(argv+list(map(str,cmd)),env=env,cwd=ROOT,capture_output=True,text=True,timeout=30)
        records.append({'command':list(map(str,cmd)),'exit':p.returncode,'expected_exit':expected,'stdout':p.stdout,'stderr':p.stderr})
        (out/'commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        if p.returncode!=expected:raise AssertionError('%r expected %s got %s\n%s\n%s'%(cmd,expected,p.returncode,p.stdout,p.stderr))
        return p.stdout
    def check(name, value, observed):
        checks.append({'name':name,'passed':bool(value),'observed':observed})
        (out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
        if not value:raise AssertionError(name)
    def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    call('setup',mat,'--exam','learning-release','--lang','zh','--days','7','--minutes','45')
    call('plan','--skip-diagnosis')
    q=next(q for q in bank() if q['chapter']==2 and '保留空位' in q['question'])
    call('quiz','--qid',q['id']);call('submit',q['id'],'空时front=rear。')
    path=out/'legacy-incomplete-ratings.json'
    write(path,{'source':q.get('answer_source') or q['source'],'criteria':[{'id':'empty','label':'判空','reference_quote':'空时front=rear','status':'met'}]})
    call('grade',q['id'],'--rubric',path,expected=3)
    a=next(a for a in state()['attempts'].values() if a['qid']==q['id'])
    check('P04_partial_rubric_cannot_create_right',not state()['history'] and a['status']=='awaiting_manual',
          {'status':a['status'],'ratings':a['rubric']['criteria'],'history':len(state()['history'])})
    call('skip',q['id'],'--note','合成测试结束未核对原答，完整契约只供下一次作答。')
    contract=out/'contract.json'
    call('rubric','draft',q['id'],'--out',contract)
    c=json.loads(contract.read_text(encoding='utf-8'));c['coverage_confirmed']=True;write(contract,c)
    call('rubric','freeze',q['id'],'--file',contract)
    call('quiz','--qid',q['id']);call('submit',q['id'],q['answer'])
    ratings=out/'ratings.json';call('rubric','ratings',q['id'],'--out',ratings)
    r=json.loads(ratings.read_text(encoding='utf-8'))
    for item in r['criteria']:item['status']='met';item['student_quote']=item['reference_quote']
    write(ratings,r);call('grade',q['id'],'--rubric',ratings)
    h=state()['history'][-1]
    check('complete_source_contract_can_grade_complete_response',h['result']=='right' and len(h['rubric']['criteria'])==3,
          {'result':h['result'],'coverage':h['rubric']['coverage_status'],'requirements':len(h['rubric']['criteria'])})
    call('goto','1','--restart');call('next');call('next');call('next')
    s=state();t=next(t for t in s['tasks'] if t['id']==s['current_task_id'])
    check('P02_continue_cannot_skip_student_response',t['phase']=='awaiting_step' and not s.get('active_attempt_id'),
          {'phase':t['phase'],'active_attempt':s.get('active_attempt_id')})
    call('task','note','--note','我还是不会，不知道出栈后剩下什么。');call('next')
    s=state();t=next(t for t in s['tasks'] if t['id']==s['current_task_id'])
    check('P03_confusion_is_not_promoted_to_independent',t['phase']=='step_check' and not s.get('active_attempt_id'),
          {'phase':t['phase'],'student_text':t['learner_steps'][-1]['text']})
    guided=next(q for q in bank() if q['id']==t['checkpoint_qid'])
    call('task','assess','--step-id',t['pending_step_id'],'--verdict','uncertain','--quote','我还是不会',
         '--reference-quote',guided['answer'],'--note','需补一个更小步骤，当前不能确认。')
    call('next');call('task','skip-check','--note','合成学生明确希望先尝试另一题，保留困惑。')
    q=next(q for q in bank() if q['chapter']==1 and q['id']!=guided['id'])
    call('quiz','--qid',q['id']);call('submit',q['id'],q['answer'].splitlines()[0],'--confidence','low');call('grade',q['id'])
    s=state();h=s['history'][-1];t=next(t for t in s['tasks'] if t['id']==s['current_task_id'])
    check('P01_answer_credit_does_not_auto_pass_method',h['result']=='right' and h['method_status']=='pending' and t['phase']=='method_check',
          {'result':h['result'],'method':h['method_status'],'phase':t['phase']})
    call('gaps','--html');call('workbench','--out',out/'pending-method-feedback.html')
    call('task','finish','--status','needs_work','--note','本次结束，保留方法待核验。');call('session','finish')
    result={'passed':all(x['passed'] for x in checks),'commands':len(records),'checks':len(checks),
            'synthetic_only':True,'real_learning_effect_test':False,'platform_live_test':False}
    write(out/'summary.json',result);write(out/'final-state.json',state())
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
