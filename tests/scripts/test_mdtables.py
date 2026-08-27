"""
Tests for the markdown table alignment tool (``scripts/mdtables.py``):

the MD060 "aligned" style check/realign, CJK-width aware. The tool is a
standalone project script (not part of the ``mycelium`` package), so the
tests load it from ``scripts/`` by path.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "mdtables", Path(__file__).resolve().parents[2] / "scripts" / "mdtables.py"
)
_mdtables = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["mdtables"] = _mdtables
_SPEC.loader.exec_module(_mdtables)

check_text = _mdtables.check_text
fix_text = _mdtables.fix_text
visual_width = _mdtables.visual_width


class TestVisualWidth(unittest.TestCase):
    def test_ascii_counts_one(self):
        self.assertEqual(visual_width("abc|"), 4)

    def test_cjk_counts_two(self):
        self.assertEqual(visual_width("字段"), 4)  # two CJK characters
        self.assertEqual(visual_width("a中b"), 4)  # 1 + 2 + 1

    def test_fullwidth_counts_two(self):
        self.assertEqual(visual_width("（秒）"), 6)  # fullwidth parentheses


class TestCheckText(unittest.TestCase):
    def test_aligned_table_passes(self):
        text = "| A    | BBB  |\n| ---- | ---- |\n| cc   | d    |\n"
        self.assertEqual(check_text(text), [])

    def test_misaligned_table_reported(self):
        text = "| A | BBB |\n| --- | --- |\n| cc | d |\n"
        violations = check_text(text)
        self.assertTrue(violations)
        self.assertEqual(violations[0].line, 1)

    def test_fenced_code_block_skipped(self):
        text = "```text\n| a | b |\n| - | - |\n```\n"
        self.assertEqual(check_text(text), [])

    def test_horizontal_rule_not_a_table(self):
        text = "some text\n\n---\n\nmore text\n"
        self.assertEqual(check_text(text), [])

    def test_indented_code_skipped(self):
        text = "    | a | b |\n    | - | - |\n"
        self.assertEqual(check_text(text), [])


class TestFixText(unittest.TestCase):
    def test_fix_aligns_and_is_idempotent(self):
        text = "| A | BBB |\n| --- | --- |\n| cc | d |\n"
        count, fixed = fix_text(text)
        self.assertEqual(count, 1)
        self.assertEqual(check_text(fixed), [])
        count2, fixed2 = fix_text(fixed)
        self.assertEqual(count2, 0)
        self.assertEqual(fixed2, fixed)

    def test_fix_preserves_alignment_markers(self):
        text = "| A | B |\n| :--- | :---: |\n| c | d |\n"
        count, fixed = fix_text(text)
        self.assertEqual(count, 1)
        self.assertIn(":---", fixed)
        self.assertIn(":---:", fixed)
        self.assertEqual(check_text(fixed), [])

    def test_fix_without_leading_pipes(self):
        text = "A | B\n--- | ---\ncc | d\n"
        count, fixed = fix_text(text)
        self.assertEqual(count, 1)
        self.assertEqual(check_text(fixed), [])

    def test_no_tables_returns_input(self):
        text = "plain text\n\n---\n"
        count, fixed = fix_text(text)
        self.assertEqual(count, 0)
        self.assertEqual(fixed, text)

    def test_escaped_pipe_preserved(self):
        text = "| A | B |\n| --- | --- |\n| a\\|b | c |\n"
        count, fixed = fix_text(text)
        self.assertIn("a\\|b", fixed)
        self.assertEqual(check_text(fixed), [])


if __name__ == "__main__":
    unittest.main()
