# -*- coding: utf-8 -*-
"""Words may change. Numbers, rows, cells and spans may not.

Step 4.6 has sub-agents edit raw LaTeX in place and then asks them to check
their own arithmetic. This is that check, done by something that has no stake
in the answer. Fixtures are synthetic and stdlib-only; the same cases run
against a real book in the scratchpad harness (KNOWLEDGE K71).
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import verify_tables as vt                                       # noqa: E402

TABLE = (
    "\\begin{table}\n\\caption{Accuracy by bit width}\n"
    "\\begin{tabular}{lrr}\n\\toprule\n"
    "Method & Bits & Score \\\\\n\\midrule\n"
    "\\multicolumn{2}{c}{Baseline} & 62.4 \\\\\n"
    "RTN & 4 & 58.1 \\\\\n"
    "Ours & 4 & 61.9 \\\\\n"
    "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
)


class TableCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="vtables_")
        self.sidecar = os.path.join(self.dir, "chunk0001.math.json")
        self.put(TABLE)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, latex):
        with io.open(self.sidecar, "w", encoding="utf-8", newline="") as fh:
            json.dump([{"token": "⟦T0001⟧", "latex": latex}], fh,
                      ensure_ascii=False)

    def check(self):
        return vt.check(self.dir)


class SnapshotContractTests(TableCase):

    def test_check_refuses_without_a_snapshot(self):
        findings, total = self.check()
        self.assertIsNone(findings,
                          "a baseline the editor could have touched is not a "
                          "baseline; refuse instead of inventing one")

    def test_snapshot_reports_what_it_recorded(self):
        files, tables = vt.snapshot(self.dir)
        self.assertEqual((files, tables), (1, 1))

    def test_an_untouched_book_is_clean(self):
        vt.snapshot(self.dir)
        findings, total = self.check()
        self.assertEqual(findings, [])
        self.assertEqual(total, 1)


class WordsMayChangeTests(TableCase):

    def test_translating_a_header_cell_is_silent(self):
        vt.snapshot(self.dir)
        self.put(TABLE.replace("Method & Bits & Score",
                               "방법 & 비트 수 & 점수"))
        self.assertEqual(self.check()[0], [])

    def test_translating_the_caption_is_silent(self):
        vt.snapshot(self.dir)
        self.put(TABLE.replace("Accuracy by bit width", "비트 폭에 따른 정확도"))
        self.assertEqual(self.check()[0], [])

    def test_a_bold_wrapper_around_a_header_is_silent(self):
        vt.snapshot(self.dir)
        self.put(TABLE.replace("Method", "\\textbf{방법}"))
        self.assertEqual(self.check()[0], [])


class StructureMayNotChangeTests(TableCase):

    def altered(self, latex):
        vt.snapshot(self.dir)
        self.put(latex)
        findings, _ = self.check()
        return " ".join(p for f in findings for p in f["problems"])

    def test_a_retyped_number_is_caught(self):
        self.assertIn("numbers changed", self.altered(TABLE.replace("62.4", "62.9")))

    def test_a_deleted_number_is_caught(self):
        self.assertIn("numbers changed", self.altered(TABLE.replace("58.1", "")))

    def test_a_dropped_ampersand_is_caught(self):
        self.assertIn("cells per row",
                      self.altered(TABLE.replace("RTN & 4", "RTN 4")))

    def test_merged_rows_are_caught(self):
        self.assertIn("rows:",
                      self.altered(TABLE.replace("58.1 \\\\", "58.1 ")))

    def test_a_widened_span_is_caught(self):
        problems = self.altered(TABLE.replace("\\multicolumn{2}",
                                              "\\multicolumn{3}"))
        self.assertTrue(problems, "a changed column span must be reported")

    def test_a_table_that_disappeared_is_caught(self):
        vt.snapshot(self.dir)
        self.put("\\begin{table}\\caption{gone}\\end{table}")
        findings, _ = self.check()
        self.assertIn("1 table(s) before, 0 after",
                      " ".join(p for f in findings for p in f["problems"]))

    def test_a_deleted_file_is_caught(self):
        vt.snapshot(self.dir)
        os.remove(self.sidecar)
        findings, _ = self.check()
        self.assertIn("the file is gone",
                      " ".join(p for f in findings for p in f["problems"]))


class NumberDiffTests(unittest.TestCase):
    """The message has to name the number that moved."""

    def test_a_repeated_value_does_not_hide_the_change(self):
        before = {"numbers": ["3", "3", "4"], "rows": 1, "ampersands": [1],
                  "spans": []}
        after = {"numbers": ["3", "4", "4"], "rows": 1, "ampersands": [1],
                 "spans": []}
        problems = vt._describe(before, after)
        self.assertIn("['3'] -> ['4']", problems[0])


class MarkdownTableTests(unittest.TestCase):
    """A table that reached the page as markdown is watched too."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="vtables_md_")
        self.path = os.path.join(self.dir, "chunk0001.md")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, text):
        with io.open(self.path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def test_a_raw_table_in_a_chunk_file_is_fingerprinted(self):
        self.write("Some prose.\n\n" + TABLE)
        vt.snapshot(self.dir)
        self.write("Some prose.\n\n" + TABLE.replace("61.9", "71.9"))
        findings, total = vt.check(self.dir)
        self.assertEqual(total, 1)
        self.assertTrue(findings)


if __name__ == "__main__":
    unittest.main()
