# -*- coding: utf-8 -*-
"""Locks for the things the last sweep found.

Each test here exists because a check passed while the thing it was supposed
to be checking was broken. They are written the same way the defects were
found: put the fault in, and require the check to notice.
"""
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
import xml.dom.minidom as minidom

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)

import merge_and_build as mb                                     # noqa: E402
import format_probe as fp                                        # noqa: E402

TEMPLATE = os.path.join(ROOT, "scripts", "template_ebook.html")


def _page(rows_html, captions=""):
    return (
        "<html><head><style>tbody tr.rule-above > * { border-top: 1px; }"
        "</style></head><body>%s<table><thead><tr><th>A</th></tr></thead>"
        "<tbody>%s</tbody></table></body></html>" % (captions, rows_html)
    )


class TableHeaderCheckTests(unittest.TestCase):
    """A header left in the body does not repeat across a page break."""

    def test_counts_only_tables_that_have_one(self):
        body = ("<table><thead><tr><th>a</th></tr></thead>"
                "<tbody><tr><td>1</td></tr></tbody></table>"
                "<table><tbody><tr><td>2</td></tr></tbody></table>")
        self.assertEqual(fp.check_table_headers(body), (2, 1))

    def test_style_block_is_not_a_table(self):
        page = _page("<tr><td>1</td></tr>")
        self.assertEqual(fp.check_table_headers(fp._STYLE_RE.sub(" ", page)),
                         (1, 1))


class CaptionTextTests(unittest.TestCase):
    """The caption's own words, not the paragraph that follows it."""

    def test_stops_at_the_end_of_the_block(self):
        body = "<p>표 3 (Table 3) Ablation study</p><p>이 표는 한국어다.</p>"
        at = body.index("Table 3)") + len("Table 3)")
        self.assertEqual(fp._caption_text(body, at), "Ablation study")

    def test_a_fixed_window_would_have_reached_the_next_paragraph(self):
        # Why the bound matters: one Hangul syllable anywhere in a fixed
        # window is enough to make an English caption look translated.
        body = "<p>표 3 (Table 3) Ablation study</p><p>이 표는 한국어다.</p>"
        at = body.index("Table 3)") + len("Table 3)")
        self.assertFalse(fp._in_target_script(fp._caption_text(body, at), "ko"))
        self.assertTrue(fp._in_target_script(body[at:at + 400], "ko"))


class CaptionNumberTests(unittest.TestCase):
    """Count captions. Cross-references are not captions."""

    def setUp(self):
        self.dir = os.path.join(HERE, ".sweep_tmp")
        if not os.path.isdir(self.dir):
            os.makedirs(self.dir)
        flat = ("\\begin{table}\\caption{First one}\\end{table}\n"
                "\\begin{table}\\caption{Second one}\\end{table}\n")
        with io.open(os.path.join(self.dir, "flat.tex"), "w",
                     encoding="utf-8") as fh:
            fh.write(flat)

    def tearDown(self):
        for name in ("flat.tex",):
            path = os.path.join(self.dir, name)
            if os.path.isfile(path):
                os.remove(path)
        if os.path.isdir(self.dir):
            os.rmdir(self.dir)

    def check(self, body):
        return fp.check_caption_numbers(self.dir, body, "ko")

    def test_prose_mentions_are_not_counted(self):
        # The bug this replaced: `표\\s*\\d+` matched every cross-reference,
        # deduplicated, and reported a total that happened to look right.
        body = ("<p>표 1 (Table 1) 첫 번째 표</p>"
                "<p>표 2 (Table 2) 두 번째 표</p>"
                "<p>표 1에서 보듯이, 표 2와 표 1을 비교하면</p>")
        want, seen, bad, disagree = self.check(body)
        self.assertEqual((want, sorted(seen)), (2, [1, 2]))
        self.assertEqual((bad, disagree), ([], []))

    def test_a_deleted_caption_is_noticed(self):
        body = "<p>표 1 (Table 1) 첫 번째 표</p><p>표 2에서 보듯이</p>"
        want, seen, _, _ = self.check(body)
        self.assertEqual((want, len(seen)), (2, 1))

    def test_a_double_stamp_is_noticed(self):
        body = ("<p>표 1 (Table 1) 표 1 (Table 1) 첫 번째 표</p>"
                "<p>표 2 (Table 2) 두 번째 표</p>")
        want, seen, _, _ = self.check(body)
        self.assertEqual((want, len(seen)), (2, 3))

    def test_an_untranslated_caption_is_noticed(self):
        body = ("<p>표 1 (Table 1) Average benchmark score per bit width</p>"
                "<p>표 2 (Table 2) 두 번째 표</p>")
        _, _, bad, _ = self.check(body)
        self.assertEqual(len(bad), 1)
        self.assertIn("Average benchmark", bad[0])

    def test_two_numbers_that_disagree_are_noticed(self):
        body = ("<p>표 1 (Table 1) 첫 번째 표</p>"
                "<p>표 2 (Table 5) 두 번째 표</p>")
        _, _, _, disagree = self.check(body)
        self.assertEqual(len(disagree), 1)

    def test_english_target_declines_to_answer(self):
        # "Table 5" is also how the prose refers to it: no anchor exists, and
        # a number this cannot stand behind is worse than no number.
        self.assertIsNone(fp.check_caption_numbers(self.dir, "<p>Table 1 x</p>",
                                                   "en"))


class TemplateRuleTests(unittest.TestCase):
    """EPUB and the web page never see a print sheet."""

    def setUp(self):
        with io.open(TEMPLATE, encoding="utf-8") as fh:
            self.css = fh.read()
        self.print_at = self.css.index("@media print")

    def test_group_rules_are_declared_before_the_print_block(self):
        at = self.css.find("tbody tr.rule-above > *")
        self.assertNotEqual(at, -1)
        self.assertLess(at, self.print_at,
                        "the group rules are print-only again: Calibre drops "
                        "a class with no active rule, and the EPUB had none")

    def test_header_underline_is_declared_before_the_print_block(self):
        at = self.css.find("thead th { border-bottom")
        self.assertNotEqual(at, -1)
        self.assertLess(at, self.print_at)

    def test_print_block_still_overrides(self):
        # Same declarations must also exist inside @media print, later in the
        # file, so the PDF keeps its hairline weights.
        after = self.css[self.print_at:]
        self.assertIn("tbody tr.rule-above > *", after)
        self.assertIn("tbody tr.rule-above-soft > *", after)


class SummaryRowLanguageTests(unittest.TestCase):
    """The fallback heuristic served two of the seven supported languages."""

    def test_matches_cjk_summary_labels(self):
        for label in ("평균", "Average", "平均", "合計", "总计", "全体"):
            self.assertTrue(mb._SUMMARY_ROW_RE.match(label),
                            "%s is not recognised as a summary row" % label)

    def test_does_not_match_an_ordinary_first_cell(self):
        for label in ("Qwen3-1.7B", "4비트", "Method"):
            self.assertFalse(mb._SUMMARY_ROW_RE.match(label))


class TableStructureAlignmentTests(unittest.TestCase):
    """Plans are matched to tables by position; say so when they cannot be."""

    def test_mismatch_is_reported(self):
        import io as _io
        plans = [{"header": 1, "rules": {}}, {"header": 1, "rules": {}}]
        html = "<table><tbody><tr><td>1</td></tr></tbody></table>"
        err = _io.StringIO()
        real_stderr, real_plans = sys.stderr, mb.table_structures
        sys.stderr, mb.table_structures = err, lambda _d: plans
        try:
            mb.apply_table_structure(html, "unused")
        finally:
            sys.stderr, mb.table_structures = real_stderr, real_plans
        self.assertIn("2 table(s) in the source, 1 in the HTML", err.getvalue())

    def test_no_warning_when_the_counts_agree(self):
        import io as _io
        plans = [{"header": 1, "rules": {}}]
        html = "<table><tbody><tr><td>1</td></tr></tbody></table>"
        err = _io.StringIO()
        real_stderr, real_plans = sys.stderr, mb.table_structures
        sys.stderr, mb.table_structures = err, lambda _d: plans
        try:
            mb.apply_table_structure(html, "unused")
        finally:
            sys.stderr, mb.table_structures = real_stderr, real_plans
        self.assertEqual(err.getvalue(), "")


class CaptionNumberingIsIdempotentTests(unittest.TestCase):
    """Run the pass on its own output and nothing may change."""

    def setUp(self):
        self.units = [{"kind": "table", "number": 1},
                      {"kind": "table", "number": 2}]
        self.real = mb.read_float_units
        mb.read_float_units = lambda _d: self.units

    def tearDown(self):
        mb.read_float_units = self.real

    def test_a_second_pass_adds_nothing(self):
        md = ("| a | b |\n|---|---|\n| 1 | 2 |\n\n: 첫 번째 표\n\n"
              "| c | d |\n|---|---|\n| 3 | 4 |\n\n: 두 번째 표\n")
        cfg = mb.get_lang_config("ko")
        once, first = mb.number_table_captions(md, "unused", cfg)
        twice, _ = mb.number_table_captions(once, "unused", cfg)
        self.assertEqual(first, 2)
        self.assertEqual(len(re.findall(r"표 \d+ \(Table \d+\)", once)), 2)
        self.assertEqual(once, twice,
                         "a repair that writes the numbered markdown back "
                         "would give every caption a second badge")


def _docx(path, tables):
    """A .docx with just enough XML to be a document with tables."""
    body = ""
    for rows in tables:
        body += "<w:tbl>" + "".join(rows) + "</w:tbl>"
    doc = ('<?xml version="1.0"?><w:document xmlns:w="w"><w:body>%s'
           "</w:body></w:document>" % body)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", doc)
        zf.writestr("[Content_Types].xml", "<Types/>")
    return path


def _rows(n):
    return ["<w:tr><w:tc><w:p/></w:tc></w:tr>" for _ in range(n)]


class DocxHeaderRowTests(unittest.TestCase):
    """pandoc marks one header row or none; a multi-deck header needs all."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "book.docx")
        self.real = mb.table_structures

    def tearDown(self):
        mb.table_structures = self.real
        shutil.rmtree(self.dir, ignore_errors=True)

    def plan(self, *headers):
        mb.table_structures = lambda _d: [{"header": h, "rules": {}}
                                          for h in headers]

    def body(self):
        with zipfile.ZipFile(self.path) as zf:
            return zf.read("word/document.xml").decode("utf-8")

    def test_marks_every_header_row_of_a_multi_deck_header(self):
        _docx(self.path, [_rows(5)])
        self.plan(2)
        self.assertEqual(mb.mark_docx_header_rows(self.path, "x"), (2, 1))
        rows = re.findall(r"<w:tr\b.*?</w:tr>", self.body(), re.DOTALL)
        self.assertEqual([r.count("tblHeader") for r in rows], [1, 1, 0, 0, 0])

    def test_running_it_twice_changes_nothing(self):
        _docx(self.path, [_rows(3)])
        self.plan(2)
        mb.mark_docx_header_rows(self.path, "x")
        first = self.body()
        self.assertEqual(mb.mark_docx_header_rows(self.path, "x")[0], 0)
        self.assertEqual(self.body(), first)

    def test_tblHeader_goes_after_trHeight_as_the_schema_requires(self):
        # Word rejects the whole file if trPr children are out of order.
        row = ('<w:tr><w:trPr><w:cantSplit/><w:trHeight w:val="20"/>'
               "</w:trPr><w:tc><w:p/></w:tc></w:tr>")
        _docx(self.path, [[row]])
        self.plan(1)
        mb.mark_docx_header_rows(self.path, "x")
        trpr = re.search(r"<w:trPr>(.*?)</w:trPr>", self.body(), re.DOTALL)
        self.assertRegex(trpr.group(1),
                         r"<w:cantSplit/><w:trHeight[^>]*/><w:tblHeader/>$")

    def test_a_count_mismatch_leaves_word_alone(self):
        _docx(self.path, [_rows(2)])
        self.plan(2, 2)
        err = io.StringIO()
        real = sys.stderr
        sys.stderr = err
        try:
            marked, _ = mb.mark_docx_header_rows(self.path, "x")
        finally:
            sys.stderr = real
        self.assertEqual(marked, 0)
        self.assertNotIn("tblHeader", self.body())
        self.assertIn("left as pandoc set them", err.getvalue())

    def test_a_table_with_no_header_in_the_source_is_untouched(self):
        _docx(self.path, [_rows(3)])
        self.plan(0)
        self.assertEqual(mb.mark_docx_header_rows(self.path, "x"), (0, 1))
        self.assertNotIn("tblHeader", self.body())

    def test_the_file_is_still_a_readable_archive(self):
        _docx(self.path, [_rows(3)])
        self.plan(2)
        mb.mark_docx_header_rows(self.path, "x")
        with zipfile.ZipFile(self.path) as zf:
            self.assertIsNone(zf.testzip())
            self.assertIn("[Content_Types].xml", zf.namelist())
        minidom.parseString(self.body())


if __name__ == "__main__":
    unittest.main()
