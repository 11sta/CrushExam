"""Cold-start subprocess regressions for the student-facing CrushExam flow."""

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CommandFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.materials = self.base / "materials"
        self.materials.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.environment = dict(os.environ, HOME=str(self.home), PYTHONUTF8="1")
        # Windows: expanduser("~") reads USERPROFILE, not HOME — set both so the
        # subprocess isolates its exam registry the same way on every platform.
        if os.name == "nt":
            self.environment["USERPROFILE"] = str(self.home)
        (self.materials / "lecture1.txt").write_text(
            "Lecture 1: Arithmetic and comparisons\n"
            "Addition combines quantities. Subtraction finds a difference.\n"
            "Compare results after the calculation.\n", encoding="utf-8")
        self.hw_path = self.materials / "hw1.txt"
        self.hw_path.write_text(
            "1. Two plus two equals which result? (4分)\n"
            "A. 3\nB. 4\nAnswer: B\n"
            "2. Three plus two equals which result? (3分)\n"
            "A. 5\nB. 6\nAnswer: A\n"
            "3. Which comparison is correct for five and four? (3分)\n"
            "A. Five is smaller\nB. Five is greater\nAnswer: B\n",
            encoding="utf-8")
        self.exam_date = (dt.date.today() + dt.timedelta(days=9)).isoformat()

    def command(self, *args, expected=0):
        process = subprocess.run(
            [sys.executable, str(ROOT / "coach.py"), *map(str, args)],
            cwd=str(ROOT), env=self.environment, capture_output=True,
            text=True, timeout=25,
        )
        self.assertEqual(process.returncode, expected,
                         "command %s: exit=%s\nSTDOUT:\n%s\nSTDERR:\n%s" %
                         (args, process.returncode, process.stdout, process.stderr))
        return process.stdout

    def setup_exam(self, exam_id):
        self.command("setup", self.materials, "--exam", exam_id, "--date", self.exam_date,
                     "--minutes", "45", "--goal", "pass", "--lang", "zh")
        registry = json.loads((self.home / ".crushexam" / "exam_registry.json").read_text(
            encoding="utf-8"))
        return Path(registry["exams"][exam_id]["workspace"])

    @staticmethod
    def read_state(workspace):
        return json.loads((workspace / "study_state.json").read_text(encoding="utf-8"))

    @staticmethod
    def bank(workspace):
        return json.loads((workspace / "quiz_bank.json").read_text(encoding="utf-8"))

    def test_first_use_diagnosis_analysis_plan_and_one_question(self):
        workspace = self.setup_exam("math-final")
        self.assertEqual(len(self.bank(workspace)), 3)
        self.assertIn("摸底", self.command("status"))
        self.command("plan", expected=4)
        self.command("next", expected=4)
        first = self.command("quiz", "--stratified", "-n", "3")
        self.assertIn("摸底 1/3", first)
        first_qid = self.read_state(workspace)["open_quiz"][0]
        # A tutor-only bypass must not reveal a diagnostic answer.
        self.command("check", first_qid, "--force", expected=5)
        self.command("grade", first_qid, "B", expected=4)
        self.command("answer", first_qid, "right", expected=4)
        bank_by_id = {q["id"]: q for q in self.bank(workspace)}
        for attempt in range(3):
            if attempt:
                self.command("quiz", "--stratified")
            qid = self.read_state(workspace)["open_quiz"][0]
            correct = bank_by_id[qid]["answer"].strip()
            raw_answer = "A" if attempt == 0 and correct != "A" else (
                "B" if attempt == 0 else correct)
            output = self.command("submit", qid, raw_answer,
                                  "--confidence", "medium", "--minutes-spent", "2")
            self.assertNotIn("--- 参考答案 ---", output)
            self.assertEqual(len(self.read_state(workspace)["history"]), attempt + 1)
            if attempt < 2:
                self.command("check", qid, expected=5)
                self.command("plan", expected=4)
        state = self.read_state(workspace)
        self.assertEqual(state["workflow"]["stage"], "analysis")
        self.assertEqual(len(state["history"]), 3)
        self.assertEqual(len({h["qid"] for h in state["history"]}), 3)
        self.assertTrue(all("response" in h and "minutes_spent" in h for h in state["history"]))
        self.command("check", first_qid, expected=5)
        self.command("plan", expected=4)
        self.command("next", expected=4)

        gaps = self.command("gaps")
        self.assertIn("模块 | 最近证据", gaps)
        self.assertIn("文件 | 内容 | 用途", gaps)
        html_file = workspace / "capability.html"
        self.assertTrue(html_file.is_file())
        html = html_file.read_text(encoding="utf-8")
        self.assertIn("<html", html)
        self.assertIn("<table", html)
        self.assertEqual(self.read_state(workspace)["workflow"]["stage"], "planning")

        summary = self.command("plan")
        self.assertIn("今日计划", summary)
        self.assertIn("依据：", summary)
        self.assertLess(len(summary), 2600)
        self.assertEqual(self.read_state(workspace)["workflow"]["stage"], "planned")

        self.command("review", first_qid, "--result", "right", expected=4)
        self.command("quiz", "--qid", first_qid)
        self.command("check", first_qid, expected=5)
        self.command("submit", first_qid, bank_by_id[first_qid]["answer"].strip())
        check = self.command("check", first_qid)
        self.assertIn("参考答案", check)
        result = self.command("grade", first_qid, "--independent")
        self.assertNotIn("python coach.py quiz", result)
        updated = self.read_state(workspace)
        self.assertEqual(len(updated["history"]), 4)
        self.assertFalse(updated.get("open_quiz"))
        self.assertFalse(updated.get("pending", {}).get(first_qid))
        self.command("review", first_qid, "--result", "right", expected=4)

    def test_same_materials_two_exams_do_not_share_attempts_or_bank_outputs(self):
        one = self.setup_exam("math-one")
        self.command("quiz", "--stratified", "-n", "1")
        qid = self.read_state(one)["open_quiz"][0]
        self.command("submit", qid, "A")
        self.assertEqual(len(self.read_state(one)["history"]), 1)
        two = self.setup_exam("math-two")
        self.assertNotEqual(one, two)
        self.assertEqual(len(self.bank(two)), 3)
        self.assertFalse(self.read_state(two)["history"])
        self.assertFalse(self.read_state(two)["unassigned_records"])
        self.assertIn("math-two", self.command("status"))
        self.command("switch", "math-one")
        self.assertIn("math-one", self.command("status"))
        self.assertEqual(len(self.read_state(one)["history"]), 1)

    def test_rescan_changed_reference_answer_quarantines_old_verdict(self):
        workspace = self.setup_exam("math-rescan")
        self.command("quiz", "--stratified", "-n", "1")
        qid = self.read_state(workspace)["open_quiz"][0]
        question = next(q for q in self.bank(workspace) if q["id"] == qid)
        answer = question["answer"].strip()
        self.command("submit", qid, answer)
        self.assertEqual(len(self.read_state(workspace)["history"]), 1)
        original = self.hw_path.read_text(encoding="utf-8")
        source_line = "Answer: %s" % answer
        replacement = "Answer: %s" % ("B" if answer == "A" else "A")
        self.assertIn(source_line, original)
        # The sampled question may be the third one, so change every source
        # answer with this key rather than only the first matching line.
        self.hw_path.write_text(original.replace(source_line, replacement), encoding="utf-8")
        self.setup_exam("math-rescan")
        rescanned = self.read_state(workspace)
        self.assertFalse(rescanned["history"])
        self.assertEqual(rescanned["workflow"]["stage"], "diagnosing")
        self.assertTrue(any(entry.get("reason") == "answer_or_scoring_source_changed"
                            for entry in rescanned["unassigned_records"]))


if __name__ == "__main__":
    unittest.main()
