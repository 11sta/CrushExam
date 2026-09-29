"""Contract tests for diagnosis, evidence summaries, and exam planning.

Run from the skill root with: python3 -m unittest discover -s tests -v
The synthetic questions below are course-independent and contain no user files.
"""

import re
import unittest

from coach import blueprint, planner, state


def question(qid, chapter, qtype, *, points=None):
    return {
        "id": qid,
        "chapter": chapter,
        "type": qtype,
        "points": points,
        "question": "Sample question %s" % qid,
        "options": [],
        "answer": "Sample answer",
        "source": {"file": "teacher-exercises.txt", "page": 1, "kind": "homework"},
    }


def study_state(chapters=(1, 2), *, current=1, exam_days=5):
    return {
        "exam_id": "diagnostic_fixture",
        "goal": "pass",
        "exam_days": exam_days,
        "exam_date": None,
        "current": current,
        "chapters": [
            {"n": ch, "title": "Chapter %d" % ch, "status": "todo",
             "part": 0, "parts": 1, "sources": [], "questions": []}
            for ch in chapters
        ],
        "history": [],
        "mistakes": [],
    }


def confirmed_blueprint():
    return {
        "version": 1,
        "structure": {
            "source": "teacher-confirmed exam format",
            "confirmed": True,
            "sections": [
                {"type": "单选", "count": 10, "points": 20},
                {"type": "简答", "count": 2, "points": 60},
            ],
        },
        "kcs": [
            {"id": "ch1-basic", "chapter": 1, "title": "Basic", "keywords": []},
            {"id": "ch2-procedure", "chapter": 2, "title": "Procedure", "keywords": []},
        ],
        "q_map": {"mc1": ["ch1-basic"], "short1": ["ch2-procedure"]},
    }


def new_chapter_order(days):
    return [task.chapter for day in days for task in day.tasks if task.kind == "new_chapter"]


class StratifiedDiagnosisTests(unittest.TestCase):
    def test_sourced_difficulty_covers_basic_and_advanced_when_available(self):
        bank = [question("a_easy", 1, "choice"), question("b_easy", 1, "choice"),
                question("c_hard", 1, "choice")]
        bp = blueprint.new_blueprint()
        blueprint.import_payload(bp, {"question_meta": {
            "a_easy": {"difficulty": "basic", "difficulty_confirmed": True,
                       "difficulty_source": "teacher key"},
            "b_easy": {"difficulty": "basic", "difficulty_confirmed": True,
                       "difficulty_source": "teacher key"},
            "c_hard": {"difficulty": "hard", "difficulty_confirmed": True,
                       "difficulty_source": "teacher key"},
        }})
        picked = blueprint.stratified_pick(study_state(), bank, 2, bp=bp)
        self.assertEqual([q["id"] for q in picked], ["a_easy", "c_hard"])

    def test_confirmed_chapter_scope_limits_diagnosis_without_guessing(self):
        bank = [question("in-scope", 2, "choice"), question("out-scope", 1, "choice")]
        picked = blueprint.stratified_pick(
            study_state(), bank, 2, exam={"scope": [{"item": "第2章", "confirmed": True}]})
        self.assertEqual([q["id"] for q in picked], ["in-scope"])

    def test_confirmed_types_are_covered_with_one_question_per_major_type(self):
        bank = [question("mc%02d" % i, 1, "choice") for i in range(9)]
        bank.append(question("short1", 2, "subjective"))
        picked = blueprint.stratified_pick(
            study_state(), bank, 2, bp=confirmed_blueprint(),
            exam={"question_types": ["单选", "简答"]},
        )
        self.assertEqual({q["type"] for q in picked}, {"choice", "subjective"})

    def test_question_bank_size_is_not_a_proxy_for_confirmed_exam_marks(self):
        bank = [question("mc%02d" % i, 1, "choice") for i in range(9)]
        bank.append(question("short1", 2, "subjective"))
        first = blueprint.stratified_pick(
            study_state(), bank, 1, bp=confirmed_blueprint(),
            exam={"question_types": ["单选", "简答"]},
        )
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["id"], "short1")


class CapabilityEvidenceTests(unittest.TestCase):
    def test_without_kc_dictionary_chapter_fallback_keeps_unmeasured_type_visible(self):
        record = study_state()
        bank = [question("mc1", 1, "choice"), question("essay1", 1, "subjective")]
        state.record_result(record, "mc1", 1, "wrong", is_independent=True)
        rows, mode = blueprint.kc_stats(record, bank, None)
        self.assertEqual(mode, "chapter")
        self.assertEqual(rows[0]["tested"], 1)
        self.assertEqual(rows[0]["untested"], 1)
        self.assertEqual(rows[0]["by_type"]["choice"]["recent_status"], "wrong")
        self.assertEqual(rows[0]["by_type"]["subjective"]["recent_status"], "untested")

    def test_latest_wrong_overrides_historical_independent_right(self):
        record = study_state()
        q = question("mc1", 1, "choice")
        bp = {"kcs": [{"id": "k1", "chapter": 1, "title": "Basics"}],
              "q_map": {"mc1": ["k1"]}}
        state.record_result(record, "mc1", 1, "right", evidence_level="immediate",
                            is_independent=True)
        state.record_result(record, "mc1", 1, "wrong", evidence_level="untested",
                            is_independent=True)
        rows, mode = blueprint.kc_stats(record, [q], bp)
        self.assertEqual(mode, "kc")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tested"], 1)
        self.assertEqual(rows[0]["indep_right"], 0)
        self.assertEqual(rows[0]["wrong"], 1)
        self.assertEqual(rows[0]["strength"], "gap")
        self.assertEqual(rows[0]["recent_status"], "wrong")
        self.assertEqual(rows[0]["by_type"]["choice"]["recent_status"], "wrong")

    def test_one_question_mapped_to_two_kcs_counts_once_in_chapter_summary(self):
        record = study_state()
        bank = [question("q1", 1, "choice"), question("q2", 1, "subjective")]
        bp = {
            "kcs": [
                {"id": "k1", "chapter": 1, "title": "Concept"},
                {"id": "k2", "chapter": 1, "title": "Application"},
            ],
            "q_map": {"q1": ["k1", "k2"], "q2": ["k1"]},
        }
        state.record_result(record, "q1", 1, "wrong", is_independent=True)
        state.record_result(record, "q2", 1, "wrong", is_independent=True)
        rows, mode = blueprint.kc_stats(record, bank, bp)
        self.assertEqual(mode, "kc")
        self.assertEqual({row["kc_id"]: row["tested"] for row in rows}, {"k1": 2, "k2": 1})
        weak, n_attempted = blueprint.weak_spots(record, bank, bp, k=3)
        self.assertEqual(n_attempted, 2)
        self.assertEqual(len(weak), 1)
        self.assertEqual(weak[0]["chapter"], 1)
        self.assertIn("0/2", weak[0]["detail"])


class PlannerDecisionTests(unittest.TestCase):
    def test_explicit_daily_minutes_override_weekly_average(self):
        record = study_state()
        record["study_minutes"] = 18
        bank = [question("mc1", 1, "choice"), question("mc2", 2, "choice")]
        plans = planner.generate_plan(
            record, today="2026-09-28", bank=bank,
            exam={"weekly_hours": 14}, weekly_hours=14,
        )
        self.assertEqual(sum(t.estimated_minutes for t in plans[0].tasks), 18)

    def test_unconfirmed_marks_and_large_bank_do_not_rank_a_chapter_higher(self):
        record = study_state()
        bank = [question("first", 1, "choice")]
        bank.extend(question("other%d" % n, 2, "choice", points=100)
                    for n in range(20))
        plans = planner.generate_plan(record, today="2026-09-28", bank=bank)
        self.assertEqual(new_chapter_order(plans)[0], 1)

    def test_confirmed_high_mark_weak_chapter_becomes_first_task(self):
        record = study_state()
        bank = [question("mc1", 1, "choice"), question("short1", 2, "subjective")]
        state.record_result(record, "mc1", 1, "right", evidence_level="immediate",
                            is_independent=True)
        state.record_result(record, "short1", 2, "wrong", is_independent=True)
        plans = planner.generate_plan(
            record, today="2026-09-28", bank=bank, bp=confirmed_blueprint(),
            exam={"exam_id": "diagnostic_fixture", "weekly_hours": 7},
        )
        self.assertEqual(new_chapter_order(plans)[0], 2)
        first = next(task for task in plans[0].tasks if task.kind == "new_chapter")
        self.assertTrue(first.why_now)
        self.assertTrue(first.pass_criteria)

    def test_unknown_marks_do_not_create_numeric_score_predictions(self):
        record = study_state()
        bank = [question("mc1", 1, "choice", points=1),
                question("short1", 2, "subjective", points=100)]
        bp = confirmed_blueprint()
        bp["structure"]["confirmed"] = False
        bp["structure"]["source"] = "unverified student recollection"
        plans = planner.generate_plan(record, today="2026-09-28", bank=bank, bp=bp)
        # A printed exercise's 100 points and an unconfirmed format are not the
        # exam's confirmed marks and must not become a personal score forecast.
        self.assertEqual(new_chapter_order(plans)[0], 1)
        visible = " ".join(
            [day.note for day in plans]
            + [task.why_now for day in plans for task in day.tasks]
        )
        self.assertNotRegex(visible, re.compile(
            r"(?:得分概率|通过概率|预计得分|预测得分|预计提分|pass probability)\s*[:：]?\s*\d",
            re.I,
        ))

    def test_tiny_weekly_budget_caps_today_and_flags_insufficient_time(self):
        record = study_state(chapters=(1, 2, 3, 4), exam_days=4)
        bank = [question("q%d" % ch, ch, "choice") for ch in (1, 2, 3, 4)]
        plans = planner.generate_plan(
            record, today="2026-09-28", bank=bank,
            exam={"weekly_hours": 1}, weekly_hours=1,
        )
        self.assertTrue(plans)
        today_tasks = plans[0].tasks
        self.assertLessEqual(
            sum(task.estimated_minutes or 0 for task in today_tasks), 60 // 7,
            "A one-hour weekly budget cannot silently produce a 25-minute first day",
        )
        note = " ".join([plans[0].note] + [task.why_now for task in today_tasks])
        self.assertRegex(note, "时间不足|建议|调整|短任务")


if __name__ == "__main__":
    unittest.main()
