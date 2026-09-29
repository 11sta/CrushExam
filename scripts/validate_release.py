#!/usr/bin/env python3
"""Reproduce a synthetic CLI study session in an isolated HOME.

Uses only included synthetic test fixtures. Does not connect to a model or
TeleAgent. The recorded responses are scripted test inputs, not real students.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_reliability_v160 import LESSON, HW
from coach import grading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="new empty validation output directory")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("output directory must be empty; no existing learner files will be overwritten")
    out.mkdir(parents=True, exist_ok=True)
    materials, home = out / "synthetic_materials", out / "isolated_home"
    materials.mkdir(); home.mkdir()
    ws = materials / "exam-cram"
    for n in LESSON:
        (materials / ("lecture%d.txt" % n)).write_text(LESSON[n], encoding="utf-8")
        (materials / ("hw%d.txt" % n)).write_text(HW[n], encoding="utf-8")
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    records = []

    def state():
        return json.loads((ws / "study_state.json").read_text(encoding="utf-8"))

    def bank():
        return json.loads((ws / "quiz_bank.json").read_text(encoding="utf-8"))

    def call(*command, expected=0):
        argv = [sys.executable, str(ROOT / "coach.py")]
        if command[0] != "setup": argv += ["-w", str(ws)]
        argv += list(map(str, command))
        p = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        snapshot = state() if (ws / "study_state.json").exists() else {}
        item = {"step": len(records)+1, "command": list(map(str, command)), "exit":p.returncode,
                "expected_exit":expected,"stdout":p.stdout,"stderr":p.stderr,
                "stage":snapshot.get("workflow",{}).get("stage"),
                "active_attempt_id":snapshot.get("active_attempt_id"),
                "history_count":len(snapshot.get("history",[])),
                "tasks":[{"kind":t["kind"],"phase":t["phase"],"status":t["status"]} for t in snapshot.get("tasks",[])]}
        records.append(item)
        (out / "journey.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
        if p.returncode != expected:
            raise AssertionError("%r expected=%s got=%s\n%s\n%s"%(command,expected,p.returncode,p.stdout,p.stderr))
        return p.stdout

    call("setup",materials,"--exam","synthetic-release","--name","数据结构·发布合成测试",
         "--lang","zh","--goal","pass","--days","7","--minutes","45")
    assert len(bank()) == 9
    call("quiz","--stratified","-n","4")
    first_aid = state()["active_attempt_id"]
    call("session","pause"); call("session","resume")
    assert state()["active_attempt_id"] == first_aid
    diagnostics = 0
    while state()["workflow"]["stage"] == "diagnosing":
        s=state()
        if not s.get("active_attempt_id"):call("quiz","--stratified");s=state()
        if s["workflow"]["stage"] != "diagnosing":break
        a=s["attempts"][s["active_attempt_id"]];q=next(q for q in bank() if q["id"]==a["qid"])
        kind=grading.grade(q.get("answer") or "", q.get("answer") or "")["kind"]
        if kind in ("choice","true_false"):
            right=q["answer"].splitlines()[0]
            response=("A" if right != "A" else "B") if diagnostics==0 and kind=="choice" else right
        elif q.get("type")=="subjective":response="空时front=rear；满条件和空位原因还不清楚。"
        else:response=q.get("answer") or "未能作答"
        call("submit",q["id"],response)
        diagnostics+=1
    assert diagnostics==4
    call("gaps","--html")
    # Deliberately keep subjective pending rather than invent a correct score.
    call("plan")
    call("task")
    # Simulated student's explicit choice: start with stack operation skills.
    call("goto","1","--restart")
    call("next")
    call("next")
    # Repeated continue cannot advance before an actual response and review.
    call("next")
    assert not state().get("active_attempt_id")
    call("task","note","--note","合成学生：先标记栈顶，再删除最后入栈的元素。")
    task=next(t for t in state()["tasks"] if t["id"]==state()["current_task_id"])
    guided=next(q for q in bank() if q["id"]==task["checkpoint_qid"])
    call("task","assess","--step-id",task["pending_step_id"],"--verdict","met",
         "--quote","先标记栈顶，再删除最后入栈的元素", "--reference-quote",guided["answer"],
         "--note","合成输入核对：参考选项对应弹出栈顶，实际学生步骤已保存。")
    call("next")
    s=state();a=s["attempts"][s["active_attempt_id"]];qid=a["qid"]
    q=next(q for q in bank() if q["id"]==qid)
    call("workbench","--out",out/"student_question.html")
    call("submit",qid,q["answer"].splitlines()[0])
    call("check",qid)
    call("grade",qid,"--error-type","procedure")
    last=state()["history"][-1]
    assert last["is_independent"] is True
    assert last["response"]==q["answer"].splitlines()[0]
    call("workbench","--out",out/"student_feedback.html")
    call("done","--chapter","1")
    call("session","finish")
    call("next",expected=4)
    assert state()["workflow"]["stage"]=="session_complete"
    call("session","resume")
    call("status")
    call("session","finish")
    summary={"synthetic_only":True,"platform_live_test":False,"real_learning_effect_test":False,
             "commands":len(records),"passed":True,"diagnostic_submissions":diagnostics,
             "last_independent_result":last["result"],"last_evidence":last["evidence_level"],
             "python":sys.version.split()[0],"final_stage":state()["workflow"]["stage"]}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 合成学生命令旅程", "", "仅验证脚本流程。以下回答为预设合成输入，不是对真人学习效果的测量。", ""]
    for r in records:
        lines += ["## %d. %s"%(r["step"]," ".join(r["command"])),"", "退出码 %s；阶段 %s；有效判分 %s。"%(r["exit"],r["stage"],r["history_count"]),"", "```text",r["stdout"].strip(),"```",""]
    (out/"journey.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == "__main__":main()
