# -*- coding: utf-8 -*-
r"""Tests for the built-table-vs-source-LaTeX probe.

The probe exists to find table content that never reached the page. It only
works if it is quiet about tables that are fine: it reported 34 findings
against SINQ and 10 against AlphaQ, nearly all of them its own rules being
wrong, and a check with that much noise is one nobody reads. The real defect
this session -- a footnote asterisk spliced out of CafeQ's table 3 -- was
found by hand, not by the probe, while 34 false alarms stood.

So these run in both directions: the probe must stay silent on a faithful
table and still speak up on one that lost a row.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import table_probe as tp


class Colspec(unittest.TestCase):

    def test_star_repeat_is_expanded(self):
        self.assertEqual(tp.colspec_columns('l*{11}{c}'), 12)

    def test_colspec_is_read_to_its_matching_brace(self):
        # `{l*{11}{c}}` stops at the `}` of `{11}` if the brace is not
        # matched, and the probe then claims three columns for twelve.
        tex = ('\\begin{tabular}{l*{11}{c}}\n'
               'a & 1 & 2 & 3 & 4 & 5 & 6 & 7 & 8 & 9 & 10 & 11 \\\\\n'
               '\\end{tabular}')
        units = tp.tabular_units(tex)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0][0], 12)

    def test_tabularx_width_argument_is_not_the_colspec(self):
        tex = ('\\begin{tabularx}{\\textwidth}{lXX}\n'
               'a & b & c \\\\\n'
               '\\end{tabularx}')
        self.assertEqual(tp.tabular_units(tex)[0][0], 3)

    def test_p_columns_still_count(self):
        self.assertEqual(tp.colspec_columns('l p{2cm} c'), 3)


class PrintedNumbers(unittest.TestCase):

    def test_citation_year_is_not_a_table_value(self):
        nums = tp.printed_numbers(r'method \cite{adepu2024framequant} & 46.6')
        self.assertNotIn('2024', nums)
        self.assertIn('46.6', nums)

    def test_citep_with_optional_arguments(self):
        self.assertNotIn('2022', tp.printed_numbers(
            r'x \citep[see][p.~3]{frantar2022gptq} & 1.5'))

    def test_multicolumn_span_is_not_a_value(self):
        nums = tp.printed_numbers(r'\multicolumn{3}{c}{48.0}')
        self.assertNotIn('3', nums)
        self.assertIn('48.0', nums)

    def test_a_real_value_survives(self):
        self.assertEqual(tp.printed_numbers('a & 46.6 & 47.6')['46.6'], 1)


class BlankFirstCell(unittest.TestCase):

    def test_multirow_continuation_is_blank(self):
        self.assertTrue(tp._blank_first_cell(r' & 3 bits & 4 bits'))

    def test_a_labelled_row_is_not_blank(self):
        self.assertFalse(tp._blank_first_cell(r'CafeQ & 46.6 & 47.6'))

    def test_a_cell_holding_only_spacing_is_blank(self):
        self.assertTrue(tp._blank_first_cell(r'\addlinespace & 1 & 2'))


SOURCE = ('\\begin{tabular}{lcc}\n'
          '\\toprule\n'
          '\\multirow{2}{*}{Method} & \\multicolumn{2}{c}{Gemma} \\\\\n'
          ' & 3 bits & 4 bits \\\\\n'
          '\\midrule\n'
          'Uniform & 23.3 & 41.3 \\\\\n'
          'CafeQ & 46.6 & 47.6 \\\\\n'
          '\\bottomrule\n'
          '\\end{tabular}')

FAITHFUL = ('<table><tr><th>Method</th><th colspan="2">Gemma</th></tr>'
            '<tr><td></td><td>3 bits</td><td>4 bits</td></tr>'
            '<tr><td>Uniform</td><td>23.3</td><td>41.3</td></tr>'
            '<tr><td>CafeQ</td><td>46.6</td><td>47.6</td></tr></table>')


class SpacingArguments(unittest.TestCase):
    r"""`\addlinespace[2pt]` is glue, and its `2` is not a table value."""

    def test_bracket_length_is_not_a_value(self):
        nums = tp.printed_numbers(r'\addlinespace[2pt] CafeQ & 46.6')
        self.assertNotIn('2', nums)
        self.assertIn('46.6', nums)

    def test_the_optional_argument_leaves_with_its_command(self):
        # Left behind, `[2pt]` lands in the next row's first cell and a
        # `\multirow` continuation reads as a labelled row.
        rows = tp.source_rows('\\addlinespace[2pt]\n'
                              '& \\multirow{6}{*}{2.5} & Uniform & 6.16 \\\\\n')
        self.assertTrue(rows)
        self.assertTrue(tp._blank_first_cell(rows[0]), rows[0])

    def test_a_length_in_braces_still_goes(self):
        self.assertNotIn('6', tp.printed_numbers(r'\vspace{6pt} a & 1.5'))


class PageMarkup(unittest.TestCase):

    def test_a_table_named_in_a_style_comment_is_not_a_table(self):
        html = ('<style>/* no break-inside on <table> — Chromium ignores'
                ' it */</style>\n<p>text</p>\n<table><tr><td>a</td></tr>'
                '</table>')
        self.assertEqual(len(tp.TABLE_EL_RE.findall(tp._page_markup(html))), 1)

    def test_a_real_table_survives(self):
        html = '<table><tr><td>a</td></tr></table>'
        self.assertEqual(tp._page_markup(html), html)


class Annotations(unittest.TestCase):

    def test_tex_annotation_is_not_page_text(self):
        cell = ('<math><mo>↓</mo><annotation encoding="application/x-tex">'
                '&#92;downarrow</annotation></math>')
        self.assertNotIn('92', tp.strip_tags(cell))

    def test_the_rendered_part_is_kept(self):
        cell = ('46.6<annotation encoding="application/x-tex">x^{*}'
                '</annotation>')
        self.assertIn('46.6', tp.strip_tags(cell))


class CheckTable(unittest.TestCase):

    def units(self):
        return tp.tabular_units(SOURCE)[0]

    def test_faithful_table_produces_no_finding(self):
        columns, body = self.units()
        self.assertEqual(tp.check_table(1, columns, body, FAITHFUL), [])

    def test_a_dropped_row_is_found(self):
        # This is the CafeQ table 4 defect in miniature: the label reaches
        # the page and the three numbers behind it do not.
        columns, body = self.units()
        broken = FAITHFUL.replace('<td>46.6</td><td>47.6</td>', '')
        findings = tp.check_table(1, columns, body, broken)
        self.assertTrue(any('not on the page' in f for f in findings),
                        findings)

    def test_a_stranded_label_is_found(self):
        columns, body = self.units()
        broken = FAITHFUL.replace('<td>Uniform</td>', '<td></td>')
        findings = tp.check_table(1, columns, body, broken)
        self.assertTrue(any('no row label' in f for f in findings), findings)

    def test_a_lost_column_span_is_found(self):
        columns, body = self.units()
        broken = FAITHFUL.replace('<th colspan="2">Gemma</th>',
                                  '<th>Gemma</th>')
        findings = tp.check_table(1, columns, body, broken)
        self.assertTrue(any('span' in f for f in findings), findings)


if __name__ == '__main__':
    unittest.main()
