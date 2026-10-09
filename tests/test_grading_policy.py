"""Grading-policy regression for v1.8.0.

Verifies the machine-readable policy (pass line, multi-select 10/6/0) and that
objective auto-grading records `score / max_score / score_source / score_pass`
on both the attempt and the history entry. Synthetic materials only.
"""
import unittest

from coach import grading, policy

from test_reliability_v160 import FlowFixture


class PolicyUnitTests(unittest.TestCase):
    def test_default_pass_threshold_is_eight(self):
        self.assertEqual(policy.pass_threshold(), 8)

    def test_multi_full_is_ten(self):
        r = grading.grade("ABC", "ABC")
        sc, mx, src = policy.grade_objective_score(r)
        self.assertEqual((sc, mx, src), (10, 10, "policy_default"))
        self.assertGreaterEqual(sc, policy.pass_threshold())

    def test_multi_missing_is_six_not_pass(self):
        r = grading.grade("AB", "ABC")  # 漏选无错选
        self.assertEqual(r["verdict"], "partial")
        sc, mx, src = policy.grade_objective_score(r)
        self.assertEqual((sc, mx, src), (6, 10, "policy_default"))
        self.assertLess(sc, policy.pass_threshold())

    def test_multi_wrong_pick_is_zero(self):
        r = grading.grade("ABD", "ABC")  # 错选 D
        sc, mx, src = policy.grade_objective_score(r)
        self.assertEqual(sc, 0)

    def test_single_true_false_wrong_is_zero(self):
        self.assertEqual(policy.grade_objective_score(grading.grade("C", "A"))[0], 0)
        self.assertEqual(policy.grade_objective_score(grading.grade("错", "正确"))[0], 0)

    def test_no_reference_is_not_scored(self):
        r = grading.grade("随便", "")
        self.assertIsNone(policy.grade_objective_score(r)[0])

    def test_rubric_score_equal_share_and_pass_line(self):
        scoring = {"max_score": 10, "source": "teacher"}
        out = policy.rubric_score(scoring, [{"status": "met"}, {"status": "met"}, {"status": "missing"}])
        self.assertEqual(out["score"], 7)
        self.assertFalse(out["pass"])

    def test_rubric_pending_is_not_pass(self):
        scoring = {"max_score": 10, "source": "teacher"}
        out = policy.rubric_score(scoring, [{"status": "met"}, {"status": "uncertain"}])
        self.assertFalse(out["pass"])
        self.assertTrue(out["pending"])


class GradingScoreFlowTests(FlowFixture):
    def test_objective_right_writes_score_fields(self):
        self.planned()
        q = self.q(1) # 单选题（答案第一行为字母）
        self.attempt(q, response=q["answer"].splitlines()[0])
        h = self.state()["history"][-1]
        self.assertEqual(h["score"], 10)
        self.assertEqual(h["max_score"], 10)
        self.assertEqual(h["score_source"], "policy_default")
        self.assertTrue(h["score_pass"])

    def test_objective_wrong_writes_score(self):
        self.planned()
        q = self.q(1)
        wrong = {"A": "B", "B": "A"}.get(q["answer"].splitlines()[0], "C")
        self.attempt(q, response=wrong)
        h = self.state()["history"][-1]
        self.assertEqual(h["score"], 0)
        self.assertFalse(h["score_pass"])

    def test_red_rubric_without_scoring_stays_unscored(self):
        # 未冻结 scoring / 无主观题契约时，绝不产生数字分值。
        self.planned()
        q = self.q(2, 2)  # 主观简述题（第2章第3题）
        self.run_cmd("quiz", "--qid", q["id"])
        self.run_cmd("submit", q["id"], "空时front=rear，满时(rear+1)%M=front，保留空位用于区分空与满。")
        out = self.run_cmd("grade", q["id"], expected=3)
        # 无冻结契约，不能直接判整题正确
        self.assertIn("主观题原答已保存", out)


if __name__ == "__main__":
    unittest.main()