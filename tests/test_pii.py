# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import unittest

from coach import extract
from coach.pii import mask_pii


class MaskPiiTest(unittest.TestCase):
    def test_phone_masked_keep_edges(self):
        text, counts = mask_pii("联系电话13800138000，课后答疑。")
        self.assertIn("138****8000", text)
        self.assertNotIn("13800138000", text)
        self.assertEqual(counts.get("phone"), 1)

    def test_id_card_masked(self):
        text, counts = mask_pii("身份证号11010119900307777X。")
        self.assertIn("110101********777X", text)
        self.assertEqual(counts.get("id_card"), 1)

    def test_email_masked(self):
        text, counts = mask_pii("邮箱：zhangsan99@example.edu.cn")
        self.assertIn("zha***@example.edu.cn", text)
        self.assertNotIn("zhangsan99@", text)
        self.assertEqual(counts.get("email"), 1)

    def test_labeled_student_id_masked(self):
        text, counts = mask_pii("学号：2021010113\n姓名：张三")
        self.assertIn("20******13", text)
        self.assertNotIn("2021010113", text)
        self.assertEqual(counts.get("student_id"), 1)

    def test_unlabeled_number_kept(self):
        text, counts = mask_pii("某工厂编号 2021010113 的产品合格率…")
        self.assertIn("2021010113", text)
        self.assertNotIn("student_id", counts)

    def test_name_field_counted_not_masked(self):
        text, counts = mask_pii("姓名：李四\n班级：高三2班")
        self.assertIn("李四", text)
        self.assertEqual(counts.get("name_fields"), 1)

    def test_problem_text_untouched(self):
        raw = "已知三角形三边长分别为3、4、5，小明求其面积。130002 不是手机号。"
        text, counts = mask_pii(raw)
        self.assertEqual(text, raw)
        self.assertEqual(counts, {})

    def test_none_and_empty(self):
        self.assertEqual(mask_pii(None), ("", {}))
        self.assertEqual(mask_pii(""), ("", {}))


class ExtractPiiIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ecc-pii-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_source_masked_and_warned(self):
        path = os.path.join(self.dir, "hw1.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("作业一\n姓名：王五 学号：2021010113 电话13800138000\n"
                     "1. 已知空队列条件 front=rear，求满队列条件。\n参考答案：满时(rear+1)%M=front。\n")
        src = extract.extract_source(self.dir, path)
        self.assertIsNone(src.error)
        self.assertIn("138****8000", src.text)
        self.assertIn("20******13", src.text)
        self.assertIn("王五", src.text)
        joined = "\n".join(src.warnings)
        self.assertIn("pii_masked", joined)
        self.assertIn("pii_name_field", joined)

    def test_clean_source_has_no_pii_warning(self):
        path = os.path.join(self.dir, "notes.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("第一章 队列\n队列是先进先出的线性表，front 指向队头，rear 指向队尾。\n")
        src = extract.extract_source(self.dir, path)
        self.assertIsNone(src.error)
        self.assertFalse(any(w.startswith("pii_") for w in src.warnings))


if __name__ == "__main__":
    unittest.main()
