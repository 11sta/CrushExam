"""Evidence integrity and safe offline rendering for the capability view."""
import os
import tempfile
import unittest

from coach import ability_view, blueprint, usage_log


def _q(qid, kind, chapter=1, source="作业.txt"):
    return {"id": qid, "type": kind, "chapter": chapter,
            "source": {"file": source, "kind": "homework"}}


def _attempt(qid, result, independent=False, evidence="untested"):
    return {"qid": qid, "result": result, "is_independent": independent,
            "evidence_level": evidence}


class AbilityViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "capability.html")
        self.bank = [_q("q1", "choice", source="<script>alert(1)</script>.txt"),
                     _q("q2", "subjective")]
        self.state = {"course": '<img src=x onerror="alert(1)">',
                      "language": "zh", "history": [], "mistakes": [],
                      "chapters": [{"n": 1, "title": "基础"}]}
        self.bp = {"kcs": [{"id": "k1", "title": "<script>alert(2)</script>", "chapter": 1},
                           {"id": "k2", "title": "应用", "chapter": 1}],
                   "q_map": {"q1": ["k1"], "q2": ["k2"]}}

    def _render(self):
        rows, mode = blueprint.kc_stats(self.state, self.bank, self.bp)
        self.assertEqual(self.path, ability_view.write_html(
            self.path, self.state, self.bank, self.bp, rows=rows, mode=mode))
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def test_latest_wrong_overrides_earlier_success_and_unknown_stays_gray(self):
        self.state["history"] = [
            _attempt("q1", "right", True, "immediate"),
            _attempt("q1", "wrong"),
        ]
        page = self._render()
        self.assertIn("最近答错", page)
        self.assertIn("N=1/1", page)
        self.assertIn("class='gap'", page)
        self.assertIn("class='untested'", page)
        self.assertIn("未测 / 灰色：没有有效作答，不代表零分", page)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;.txt", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn("<img src=x", page)

    def test_delayed_evidence_and_six_cards_have_no_fabricated_score(self):
        for i in range(3, 7):
            self.bp["kcs"].append({"id": "k%d" % i, "title": "模块%d" % i, "chapter": 1})
        self.state["history"] = [_attempt("q1", "right", True, "delayed")]
        page = self._render()
        self.assertIn("六模块概览", page)
        self.assertIn("class='delayed'", page)
        self.assertIn("不是六项等分的能力分数", page)
        self.assertNotIn("<script", page)
        self.assertNotIn("https://", page)

    def test_only_confirmed_marks_reorder_equally_observed_gaps(self):
        self.state["history"] = [_attempt("q1", "wrong"), _attempt("q2", "wrong")]
        self.bp["kcs"][1].update(exam_points=20, weight_confirmed=True,
                                  weight_source="老师确认的评分规则 p.1")
        page = self._render()
        priorities = page.split("下一步优先看", 1)[1].split("</section>", 1)[0]
        self.assertLess(priorities.find("应用"), priorities.find("&lt;script&gt;"))
        self.assertIn("已确认知识点分值 20", priorities)

    def test_fallback_without_blueprint_does_not_claim_knowledge_gaps(self):
        page_path = ability_view.write_html(self.path, self.state, self.bank, None)
        with open(page_path, encoding="utf-8") as fh:
            page = fh.read()
        self.assertIn("暂按章节展示；不能据此断言具体知识缺口", page)

    def test_render_files_are_not_vision_calls_and_overlapping_dirs_dedup(self):
        inner = os.path.join(self.tmp.name, "cache")
        os.mkdir(inner)
        with open(os.path.join(inner, "render.png"), "wb") as fh:
            fh.write(b"image")
        count, files = usage_log.estimate_ocr([self.tmp.name, inner])
        self.assertEqual(count, 1)
        self.assertEqual(files, [os.path.join(inner, "render.png")])


if __name__ == "__main__":
    unittest.main()
