"""Regression tests for exam isolation and conservative evidence inheritance."""
import os
import tempfile
import unittest
from unittest.mock import patch

from coach import exams, questions, state


def _question(answer="B", body="已知条件保持不变。求最终计算结果。"):
    return {
        "label": "1", "question": body, "options": ["A. 3", "B. 4"],
        "answer": answer, "type": "choice", "chapter": 1,
        "source": {"file": "hw1.txt", "page": 1, "head": "1. 已知条件保持不变。"},
        "answer_source": {"file": "hw1-sol.txt", "page": 1},
    }


def _study(exam_id):
    return state.new_state("course", "zh", 7, "/materials", [{
        "n": 1, "title": "模块", "parts": 1, "sources": ["hw1.txt"], "questions": 1,
    }], 1200, exam_id=exam_id)


class QuestionIdentityTests(unittest.TestCase):
    def test_full_stem_changes_id_while_answer_changes_only_version(self):
        original = _question()
        edited_body = _question(body="已知条件保持不变。求另外一个完全不同的计算结果。")
        edited_answer = _question(answer="A")
        self.assertEqual(questions.legacy_question_fingerprint(original),
                         questions.legacy_question_fingerprint(edited_body))
        self.assertNotEqual(questions.question_fingerprint(original),
                            questions.question_fingerprint(edited_body))
        self.assertEqual(questions.question_fingerprint(original),
                         questions.question_fingerprint(edited_answer))
        self.assertNotEqual(questions.question_answer_version(original),
                            questions.question_answer_version(edited_answer))

    def test_safe_legacy_migration_carries_original_response(self):
        original = _question()
        legacy = dict(original, id=questions.legacy_question_fingerprint(original))
        prior, fresh = _study("final-a"), _study("final-a")
        state.record_result(prior, legacy["id"], 1, "right", evidence_level="immediate",
                            is_independent=True, response="B", grading_source="hw1-sol.txt p.1")
        state.set_review_date(prior, legacy["id"], "2026-09-30")
        result = state.reconcile_question_records(fresh, prior, [legacy], [original], exam_id="final-a")
        newid = questions.question_fingerprint(original)
        self.assertEqual(result["qid_map"], {legacy["id"]: newid})
        self.assertEqual(fresh["history"][0]["response"], "B")
        self.assertEqual(fresh["history"][0]["qid"], newid)
        self.assertEqual(fresh["mistakes"][0]["next_review_date"], "2026-09-30")

    def test_rescan_answer_or_stem_change_quarantines_old_grade(self):
        original = _question()
        old = dict(original, id=questions.legacy_question_fingerprint(original))
        previous = _study("final-a")
        state.record_result(previous, old["id"], 1, "right", evidence_level="immediate")
        for edited, reason in ((_question(answer="A"), "answer_or_scoring_source_changed"),
                               (_question(body="已知条件保持不变。求另一问的最后结果。"),
                                "question_changed_or_missing")):
            current = _study("final-a")
            result = state.reconcile_question_records(current, previous, [old], [edited],
                                                      exam_id="final-a")
            self.assertFalse(current["history"])
            self.assertEqual(result["quarantined_history"], 1)
            self.assertEqual(current["unassigned_records"][0]["reason"], reason)

    def test_different_exam_never_inherits_even_same_bank(self):
        q = _question()
        old = dict(q, id=questions.question_fingerprint(q))
        previous, current = _study("final-a"), _study("final-b")
        state.record_result(previous, old["id"], 1, "right", evidence_level="immediate")
        result = state.reconcile_question_records(current, previous, [old], [q], exam_id="final-b")
        self.assertFalse(current["history"])
        self.assertEqual(result["quarantined_history"], 1)

    def test_unlabelled_legacy_state_remains_readable_without_attribution(self):
        q = _question()
        old = dict(q, id=questions.legacy_question_fingerprint(q))
        previous, current = _study(None), _study("final-b")
        state.record_result(previous, old["id"], 1, "right", evidence_level="immediate")
        result = state.reconcile_question_records(current, previous, [old], [q], exam_id="final-b")
        self.assertEqual(result["qid_map"], {})
        self.assertFalse(current["history"])
        self.assertEqual(current["unassigned_records"][0]["reason"],
                         "different_or_unidentified_exam")

    def test_history_version_blocks_reuse_if_bank_was_edited_in_place(self):
        original = _question()
        edited = _question(answer="A")
        old_bank_entry = dict(edited, id=questions.question_fingerprint(edited))
        previous, current = _study("final-a"), _study("final-a")
        state.record_result(previous, old_bank_entry["id"], 1, "right",
                            answer_version=questions.question_answer_version(original),
                            item_version=questions.question_version(original))
        state.reconcile_question_records(current, previous, [old_bank_entry], [edited], exam_id="final-a")
        self.assertFalse(current["history"])
        self.assertEqual(current["unassigned_records"][0]["reason"],
                         "stored_attempt_version_mismatch")

    def test_most_recent_wrong_resets_current_evidence(self):
        s = _study("final-a")
        state.record_result(s, "q-one", 1, "right", evidence_level="immediate",
                            is_independent=True, response="B")
        state.record_result(s, "q-one", 1, "wrong", response="A")
        self.assertEqual(state.latest_attempt(s, "q-one")["response"], "A")
        self.assertEqual(state.get_evidence_level(s, "q-one"), "untested")
        state.record_result(s, "q-one", 1, "right", evidence_level="hinted")
        self.assertEqual(state.current_evidence_level(s, "q-one"), "hinted")


class ExamWorkspaceTests(unittest.TestCase):
    def test_same_materials_different_exam_ids_have_isolated_workspaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(exams, "REGISTRY_DIR", os.path.join(tmp, "registry")), \
                    patch.object(exams, "REGISTRY_FILE", os.path.join(tmp, "registry", "exams.json")), \
                    patch.object(exams, "OLD_POINTER", os.path.join(tmp, "pointer", "last_workspace")):
                materials = os.path.join(tmp, "materials")
                os.mkdir(materials)
                ws_a = exams.suggest_workspace(materials, "a")
                exams.register("a", "class", "final", None, "pass", ws_a, materials)
                ws_b = exams.suggest_workspace(materials, "b")
                self.assertNotEqual(ws_a, ws_b)
                self.assertEqual(os.path.basename(os.path.dirname(ws_b)), "exams")
                self.assertIn("exam-cram", ws_b)
                with self.assertRaises(ValueError):
                    exams.register("b", "class", "final", None, "pass", ws_a, materials)


if __name__ == "__main__":
    unittest.main()
