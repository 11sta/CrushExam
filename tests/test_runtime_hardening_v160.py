"""Bounded lock, source identity and real command recovery contracts."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from coach import attempts as at, blueprint, exams, questions
from coach.workspace_lock import locked
from test_reliability_v160 import FlowFixture, ROOT


class RuntimeHardening(FlowFixture):
    def relationship(self, target, base):
        dictionary = self.base / "kc.json"
        dictionary.write_text(json.dumps({"kcs":[{"id":"stack-order","chapter":1,"title":"栈操作顺序","keywords":["栈"],"source":"lecture1.txt p.1"}]}), encoding="utf-8")
        self.run_cmd("blueprint", "--file", dictionary, "--qmap", base["id"]+":stack-order", target["id"]+":stack-order")
        self.run_cmd("verify-transfer", target["id"], base["id"], "--kc", "stack-order",
                     "--basis", "两道资料原题均要求按后进先出追踪中间状态，操作序列不同。", "--confirmed")

    def test_chapter_mapping_is_not_driven_by_options_or_example_numbers(self):
        for q in self.bank():
            expected = int(q["source"]["file"][2])
            self.assertEqual(q["chapter"], expected, q["question"])
            self.assertTrue(q["chapter_guessed"])

    def test_undefined_kc_override_is_rejected_not_silently_discarded(self):
        self.planned()
        self.run_cmd("blueprint", "--qmap", self.q()["id"]+":not-imported-kc", expected=2)

    def test_transfer_requires_verified_relationship_and_real_novel_attempt(self):
        self.planned(); base, target = self.q(), self.q(index=2)
        self.attempt(base); self.relationship(target, base)
        self.run_cmd("quiz", "--qid", target["id"])
        self.run_cmd("submit", target["id"], "B")
        self.run_cmd("grade", target["id"], "--transfer-from", base["id"])
        self.assertEqual(self.state()["history"][-1]["evidence_level"], "transfer")

    def test_unconfirmed_transfer_is_rejected_but_normal_grade_can_proceed(self):
        self.planned(); base, target = self.q(), self.q(index=2)
        self.attempt(base)
        self.run_cmd("quiz", "--qid", target["id"]); self.run_cmd("submit", target["id"], "B")
        self.run_cmd("grade", target["id"], "--transfer-from", base["id"], expected=4)
        self.run_cmd("grade", target["id"])
        self.assertEqual(self.state()["history"][-1]["evidence_level"], "immediate")

    def test_hinted_target_cannot_be_promoted_to_transfer(self):
        self.planned(); base, target = self.q(), self.q(index=2)
        self.attempt(base); self.relationship(target, base)
        self.run_cmd("quiz", "--qid", target["id"])
        self.run_cmd("submit", target["id"], "B", "--hinted")
        self.run_cmd("grade", target["id"], "--transfer-from", base["id"], expected=4)
        self.run_cmd("grade", target["id"])
        self.assertEqual(self.state()["history"][-1]["evidence_level"], "hinted")

    def test_changed_base_answer_invalidates_transfer_link(self):
        self.planned(); base, target = self.q(), self.q(index=2)
        self.attempt(base); self.relationship(target, base)
        bank = self.bank()
        next(q for q in bank if q["id"] == base["id"])["answer"] = "A"
        (self.ws / "quiz_bank.json").write_text(json.dumps(bank), encoding="utf-8")
        self.run_cmd("quiz", "--qid", target["id"]); self.run_cmd("submit", target["id"], "B")
        self.run_cmd("grade", target["id"], "--transfer-from", base["id"], expected=4)
        self.assertEqual(len(self.state()["history"]), 1)

    def test_goto_binds_same_task_to_next_and_quiz(self):
        self.planned(); old = self.state()["current_task_id"]
        self.run_cmd("goto", "2")
        s = self.state(); self.assertEqual(s["last_plan"]["today"]["chapter"], 2)
        self.assertEqual(next(t for t in s["tasks"] if t["id"] == old)["status"], "deferred")
        self.assertIn("先进先出", self.run_cmd("next"))
        self.run_cmd("quiz")
        self.assertEqual(at.active(self.state())["chapter"], 2)
        self.assertEqual(at.active(self.state())["task_id"], self.state()["current_task_id"])

    def test_goto_cannot_abandon_unsubmitted_item(self):
        self.planned(); self.run_cmd("quiz"); aid=self.state()["active_attempt_id"]
        self.run_cmd("goto", "2", expected=4)
        self.assertEqual(self.state()["active_attempt_id"], aid)

    def test_diagnostic_workbench_imports_without_revealing_key(self):
        self.run_cmd("quiz", "--stratified", "-n", "2"); self.run_cmd("workbench")
        a=at.active(self.state()); q=next(q for q in self.bank() if q["id"] == a["qid"])
        text=(self.ws / "workbench.html").read_text(encoding="utf-8")
        self.assertIn('"feedback": null', text)
        data={"schema":"crushexam-submission-v1", "exam_id":"synth", "attempt_id":a["id"], "qid":a["qid"],
              "item_version":a["item_version"], "delivery_token":a["delivery_token"],
              "action":"submit", "response":q["answer"].splitlines()[0], "hinted":False}
        p=self.base/"reply.json";p.write_text(json.dumps(data), encoding="utf-8")
        self.run_cmd("import-answer",p)
        self.assertEqual(len(self.state()["workflow"]["diagnostic_submitted"]),1)
        self.run_cmd("workbench",expected=4)  # do not show last graded diagnostic key
        self.run_cmd("quiz", "--stratified")

    def test_parked_subjective_attempt_is_not_recycled_into_new_diagnosis(self):
        self.planned(); q=self.q(2,2)
        self.run_cmd("quiz","--qid",q["id"]);self.run_cmd("submit",q["id"],"我写到空时front=rear。")
        self.run_cmd("grade",q["id"],expected=3)
        aid=at.lookup(self.state(),q["id"])["id"]
        self.run_cmd("diagnose","--restart","-n","8")
        self.assertNotIn(q["id"],self.state()["workflow"]["diagnostic_ids"])
        self.assertEqual(self.state()["attempts"][aid]["status"],"awaiting_manual")

    def test_bad_rubric_shapes_return_clean_error_without_overwriting_raw(self):
        self.planned();q=self.q(2,2)
        self.run_cmd("quiz","--qid",q["id"]);self.run_cmd("submit",q["id"],"空时front=rear")
        for data in ([], {"source":[]}, {"source":[1]}, {"source":{"file":q["source"]["file"],"page":q["source"]["page"]},
                  "criteria":[{"id":[1],"label":"x","status":"met","reference_quote":"空"}]}):
            p=self.base/"rubric.json";p.write_text(json.dumps(data),encoding="utf-8")
            self.run_cmd("grade",q["id"],"--rubric",p,expected=4)
        self.assertEqual(at.active(self.state())["raw_answer"],"空时front=rear")
        self.assertFalse(self.state()["history"])

    def test_plan_execution_enters_studying_and_wrong_remediation_starts_with_teaching(self):
        from coach import planner, tasks
        self.planned(); self.run_cmd("next")
        self.assertEqual(self.state()["workflow"]["stage"], "studying")
        s=self.state()
        plan=planner.DayPlan(tasks=[planner.Task("mistake_review",chapter=1,qids=[self.q()["id"]])])
        tasks.install(s,plan,self.bank())
        self.assertEqual(tasks.current(s)["phase"],"explain")

    def test_bad_state_is_not_silently_reinitialized(self):
        path=self.ws/"study_state.json";path.write_text("[]",encoding="utf-8")
        out=self.run_cmd("status",expected=2)
        self.assertIn("JSON object",out); self.assertEqual(path.read_text(),"[]")


class ProcessLocks(unittest.TestCase):
    def test_lock_times_out_in_bounded_interval_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            start=time.monotonic()
            with locked(d):
                with self.assertRaises(TimeoutError):
                    with locked(d,timeout=.15):
                        self.fail("second lock must not succeed")
            self.assertLess(time.monotonic()-start,2)
            with locked(d,timeout=.2):
                pass

    def test_crashed_process_releases_lock_without_stale_file_deletion(self):
        with tempfile.TemporaryDirectory() as d:
            script="from coach.workspace_lock import locked; import sys,time\nwith locked(sys.argv[1]):\n print('locked',flush=True)\n time.sleep(60)\n"
            p=subprocess.Popen([sys.executable,"-c",script,d],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(p.stdout.readline().strip(),"locked")
                p.kill();p.wait(timeout=5)
                with locked(d,timeout=.3):
                    self.assertTrue((Path(d)/".crushexam.lock").is_file())
            finally:
                if p.poll() is None:p.kill();p.wait()
                p.stdout.close();p.stderr.close()

    def test_concurrent_exam_registration_preserves_every_entry(self):
        with tempfile.TemporaryDirectory() as d:
            script="""import sys,os
from coach import exams
base,eid=sys.argv[1:]
exams.REGISTRY_DIR=os.path.join(base,'reg')
exams.REGISTRY_FILE=os.path.join(exams.REGISTRY_DIR,'exam_registry.json')
exams.OLD_POINTER=os.path.join(base,'pointer')
exams.register(eid,eid,'final',None,'pass',os.path.join(base,eid),base)
"""
            ps=[subprocess.Popen([sys.executable,"-c",script,d,"exam%d"%i],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(6)]
            for p in ps:
                stdout,stderr=p.communicate(timeout=10)
                self.assertEqual(p.returncode,0,stderr.decode())
            reg=json.loads((Path(d)/"reg"/"exam_registry.json").read_text())
            self.assertEqual(set(reg["exams"]),{"exam%d"%i for i in range(6)})
            self.assertFalse(list((Path(d)/"reg").glob("*.tmp")))


if __name__ == "__main__": unittest.main()
