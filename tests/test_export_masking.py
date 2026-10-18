# -*- coding: utf-8 -*-
"""Output-boundary masking: exported files never leak raw formatted PII.

Input-side masking runs when materials enter the workspace, but file names and
course titles are not part of the extracted text. These tests pin the
second-pass masking applied at the export boundary (cheatsheet, capability
view) so a PII-bearing file name or course title cannot reappear verbatim.
"""
import tempfile
import unittest
from pathlib import Path

from coach import ability_view
from coach.cli import _mask

PHONE = "13800138000"


class CliMaskHelperTest(unittest.TestCase):
    def test_mask_covers_phone_id_email(self):
        masked = _mask("联系%s，证件11010119900307777X，邮箱zhangsan99@example.edu.cn" % PHONE)
        self.assertNotIn(PHONE, masked)
        self.assertNotIn("19900307", masked)
        self.assertNotIn("zhangsan99@", masked)
        self.assertIn("138****", masked)

    def test_mask_keeps_ordinary_text(self):
        raw = "第3章 栈与队列：满队列条件 (rear+1)%M=front。"
        self.assertEqual(_mask(raw), raw)

    def test_mask_handles_none(self):
        self.assertEqual(_mask(None), "")


class CapabilityHtmlMaskTest(unittest.TestCase):
    def test_course_title_and_file_name_masked_in_html(self):
        state = {"course": "数据结构期末%s" % PHONE, "language": "zh",
                 "history": [], "chapters": []}
        bank = [{"id": "q1", "type": "choice", "chapter": 1, "question": "1+1=?",
                 "answer": "2", "source": {"file": "期末卷%s.docx" % PHONE,
                                           "kind": "exam", "page": 1}}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capability.html"
            # rows/mode precomputed (empty) so the test exercises rendering +
            # masking, not the full evidence aggregation pipeline.
            ability_view.write_html(path, state, bank, {}, rows=[], mode="chapter")
            html_text = path.read_text(encoding="utf-8")
        self.assertNotIn(PHONE, html_text)
        self.assertIn("138****", html_text)


class MaskCheckScriptTest(unittest.TestCase):
    def test_standalone_mask_preview_smoke(self):
        import subprocess
        import sys as _sys
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "note.txt"
            sample.write_text("联系电话%s，课后答疑。" % PHONE, encoding="utf-8")
            proc = subprocess.run(
                [_sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "mask_check.py"), str(sample)],
                capture_output=True, text=True, timeout=30, cwd=str(Path(__file__).resolve().parents[1]))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn(PHONE, proc.stdout)
            self.assertIn("138****8000", proc.stdout)
            self.assertIn("phone=1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
