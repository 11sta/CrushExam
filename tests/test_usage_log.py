# -*- coding: utf-8 -*-
"""Usage log parsing and the usage command attribution report."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coach import cli  # noqa: E402
from coach import state as st  # noqa: E402
from coach import usage_log as usemod  # noqa: E402


LOG = {
    "sessions": {
        "ses_aaa": {"totalCalls": 20, "seenCallIds": ["c%d" % i for i in range(20)],
                    "updatedAt": "2026-09-21T08:00:42.037Z", "endedAt": "2026-09-21T08:00:42.037Z"},
        "ses_bbb": {"totalCalls": 0, "seenCallIds": [],
                    "updatedAt": "2026-09-22T14:03:29.130Z", "endedAt": "2026-09-22T14:03:29.130Z"},
        "ses_ccc": {"totalCalls": 52, "seenCallIds": ["b%d" % i for i in range(52)],
                    "updatedAt": "2026-09-28T02:47:03.444Z", "endedAt": "2026-09-28T02:47:03.444Z"},
        "ses_bad": "not a dict",
    }
}


class UsageLogModuleTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="usage-")
        self.log = os.path.join(self.dir, ".tool-usage-log.json")
        with open(self.log, "w", encoding="utf-8") as fh:
            json.dump(LOG, fh, ensure_ascii=False)
        self._roots = usemod.SEARCH_ROOTS
        usemod.SEARCH_ROOTS = ()

    def tearDown(self):
        usemod.SEARCH_ROOTS = self._roots
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_load_log_parses_and_skips_bad_records(self):
        sessions = usemod.load_log(self.log)
        self.assertEqual(len(sessions), 3)   # ses_bad skipped
        # sorted by day then id, ascending: 09-21 first, 09-28 last
        self.assertEqual(sessions[0]["total_calls"], 20)
        self.assertEqual(sessions[0]["day"], "2026-09-21")
        self.assertEqual(sessions[-1]["session_id"], "ses_ccc")
        self.assertEqual(sessions[-1]["total_calls"], 52)

    def test_load_log_missing_file_returns_none(self):
        self.assertIsNone(usemod.load_log(os.path.join(self.dir, "nope.json")))

    def test_load_log_malformed_returns_none(self):
        bad = os.path.join(self.dir, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertIsNone(usemod.load_log(bad))

    def test_find_log_explicit(self):
        self.assertEqual(usemod.find_log(self.log), os.path.abspath(self.log))
        # explicit path that does not exist: never silently fall back to detection
        self.assertIsNone(usemod.find_log(os.path.join(self.dir, "missing.json")))
    def test_summarize_counts_empty_sessions(self):
        sessions = usemod.load_log(self.log)
        rep = usemod.summarize(sessions)
        self.assertEqual(rep["calls_total"], 52 + 20)
        self.assertEqual(rep["sessions_total"], 3)
        self.assertEqual(rep["sessions_nonempty"], 2)
        self.assertIn("2026-09-21", rep["by_day"])
        self.assertEqual(rep["by_day"]["2026-09-21"]["calls"], 20)
        self.assertEqual(rep["heaviest"][0]["session_id"], "ses_ccc")

    def test_summarize_days_window_filters(self):
        sessions = usemod.load_log(self.log)
        # 1-day window keeps only the 09-28 session
        rep = usemod.summarize(sessions, days=1)
        self.assertEqual(rep["sessions_total"], 1)
        rep_all = usemod.summarize(sessions, days=30)
        self.assertEqual(rep_all["sessions_total"], 3)

    def test_estimate_ocr_counts_images(self):
        ocr = os.path.join(self.dir, "ocr")
        os.makedirs(ocr)
        for i in range(3):
            with open(os.path.join(ocr, "p%d.png" % i), "wb") as fh:
                fh.write(b"x")
        sub = os.path.join(ocr, "comb")
        os.makedirs(sub)
        with open(os.path.join(sub, "c1.jpg"), "wb") as fh:
            fh.write(b"x")
        with open(os.path.join(ocr, "ignore.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        n, files = usemod.estimate_ocr([ocr])
        self.assertEqual(n, 4)
        self.assertEqual(len(files), 4)


class UsageCliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="usagecli-")
        self._roots = usemod.SEARCH_ROOTS
        usemod.SEARCH_ROOTS = ()
        self.ws = os.path.join(self.dir, "exam-cram")
        os.makedirs(self.ws)
        os.environ["CRUSHEXAM_WORKSPACE"] = self.ws
        os.environ["EXAM_CRAM_WORKSPACE"] = self.ws
        home = os.path.join(self.dir, "home")
        os.makedirs(home)
        self._pointer = cli.POINTER
        cli.POINTER = os.path.join(home, "last_workspace")
        import coach.exams as exammod
        self._reg_dir = exammod.REGISTRY_DIR
        exammod.REGISTRY_DIR = os.path.join(home, ".crushexam")
        exammod.REGISTRY_FILE = os.path.join(exammod.REGISTRY_DIR, "exam_registry.json")
        exammod.OLD_POINTER = os.path.join(home, "last_workspace")
        state = {
            "version": 6, "exam_id": None, "course": "T", "language": "zh", "exam_days": 3,
            "exam_date": None, "goal": "pass", "materials": [], "created": "t", "updated": "t",
            "slice_chars": 3000, "current": 1,
            "chapters": [{"n": 1, "title": "ch1", "status": "todo", "part": 0, "parts": 1,
                          "sources": ["t.txt"], "questions": 2}],
            "history": [], "mistakes": [], "notes": [],
        }
        with open(os.path.join(self.ws, "study_state.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)

    def tearDown(self):
        usemod.SEARCH_ROOTS = self._roots
        cli.POINTER = self._pointer
        os.environ.pop("CRUSHEXAM_WORKSPACE", None)
        os.environ.pop("EXAM_CRAM_WORKSPACE", None)
        import coach.exams as exammod
        exammod.REGISTRY_DIR = self._reg_dir
        exammod.REGISTRY_FILE = os.path.join(exammod.REGISTRY_DIR, "exam_registry.json")
        exammod.OLD_POINTER = cli.POINTER
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(list(argv))
        return rc, buf.getvalue()

    def test_usage_without_log_hints(self):
        rc, out = self.run_cli("usage")
        self.assertEqual(rc, 2)
        self.assertIn("找不到", out)

    def test_usage_report_with_log_and_ocr(self):
        log = os.path.join(self.dir, ".tool-usage-log.json")
        with open(log, "w", encoding="utf-8") as fh:
            json.dump(LOG, fh, ensure_ascii=False)
        ocr = os.path.join(self.dir, "ocr")
        os.makedirs(ocr)
        for i in range(2):
            with open(os.path.join(ocr, "p%d.png" % i), "wb") as fh:
                fh.write(b"x")
        rc, out = self.run_cli("usage", "--log", log, "--ocr-dir", ocr)
        self.assertEqual(rc, 0)
        self.assertIn("用量与积分归因", out)
        self.assertIn("72", out)                    # 20 + 52 calls
        self.assertIn("ses_ccc", out)
        self.assertIn("本地渲染图文件数", out)      # file count, NOT a vision-call estimate
        self.assertIn("2", out)                     # 2 rendered images
        self.assertIn("≠", out)                     # honesty note: calls != credits


if __name__ == "__main__":
    unittest.main()