# -*- coding: utf-8 -*-
r"""Tests for what happens to a table that runs onto a second page.

Two defects, neither of which any count could see, because nothing was
missing from the document -- only from the page the reader was looking at.

Chromium repeats a `<thead>` on every page its table covers, and out of a
two-row header it drops the inline `<math>` when it does. AlphaQ's table 1
said `WikiText2 ↓` and `정확도 ↑` on the first page and neither on the second,
so the continuation never said which direction was better.

And the break fell inside a labelled row group: the page opened with
`PMQ 7.42 ...` under an empty model and an empty bit budget, because the
label prints once, on the group's first row, which had stayed behind.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

ARROW = ('<math display="inline"><semantics><mo>↓</mo>'
         '<annotation encoding="application/x-tex">&#92;downarrow'
         '</annotation></semantics></math>')
FORMULA = ('<math display="inline"><semantics><mrow><mi>x</mi><mo>+</mo>'
           '<mi>y</mi></mrow><annotation encoding="application/x-tex">x+y'
           '</annotation></semantics></math>')

LATEX = ('\\begin{tabular}{lcc}\n'
         '\\toprule\n'
         'Model & Bits & PPL \\\\\n'
         '\\midrule\n'
         'Mixtral & 2.5 & 8.13 \\\\\n'
         ' & 2.5 & 7.42 \\\\\n'
         '\\midrule\n'
         'OLMoE & 3.5 & 7.95 \\\\\n'
         ' & 3.5 & 7.60 \\\\\n'
         '\\bottomrule\n'
         '\\end{tabular}')

HTML = ('<table>\n<thead>\n<tr><th>Model</th><th>Bits</th>'
        '<th>PPL ' + ARROW + '</th></tr>\n</thead>\n<tbody>\n'
        '<tr><td>Mixtral</td><td>2.5</td><td>8.13</td></tr>\n'
        '<tr><td></td><td>2.5</td><td>7.42</td></tr>\n'
        '<tr><td>OLMoE</td><td>3.5</td><td>7.95</td></tr>\n'
        '<tr><td></td><td>3.5</td><td>7.60</td></tr>\n'
        '</tbody>\n</table>')


class SymbolMath(unittest.TestCase):

    def test_a_lone_symbol_in_the_header_becomes_a_character(self):
        got, n = mb.simplify_symbol_math(HTML)
        self.assertEqual(n, 1)
        self.assertIn('↓', got)
        self.assertNotIn('<math', got)

    def test_it_keeps_a_math_class_so_the_check_can_count_it(self):
        # The math check compares formulas asked for against formulas
        # delivered. A symbol dropped from that total is a hole it would
        # stop being able to see.
        got, _n = mb.simplify_symbol_math(HTML)
        self.assertIn('class="math-symbol"', got)
        self.assertTrue(re.search(r'class="[^"]*\bmath\b', got))

    def test_a_real_formula_is_left_as_mathml(self):
        html = '<thead><tr><th>%s</th></tr></thead>' % FORMULA
        got, n = mb.simplify_symbol_math(html)
        self.assertEqual(n, 0)
        self.assertIn('<math', got)

    def test_body_math_is_left_alone(self):
        html = '<tbody><tr><td>%s</td></tr></tbody>' % ARROW
        got, n = mb.simplify_symbol_math(html)
        self.assertEqual(n, 0)
        self.assertIn('<math', got)


class RowGroups(unittest.TestCase):

    def test_groups_are_found_at_the_rules_the_paper_drew(self):
        self.assertTrue(mb.labelled_group_starts(LATEX))

    def test_one_tbody_per_group(self):
        got, groups = mb.split_row_groups(HTML, LATEX)
        self.assertEqual(groups, len(mb.labelled_group_starts(LATEX)) + 1)
        self.assertEqual(got.count('<tbody class="rowgroup">'), groups)

    def test_no_row_is_lost_or_reordered(self):
        got, _groups = mb.split_row_groups(HTML, LATEX)
        before = re.findall(r'(?s)<tr\b.*?</tr>', HTML)
        after = re.findall(r'(?s)<tr\b.*?</tr>', got)
        self.assertEqual(before, after)

    def test_a_table_with_no_group_rule_is_untouched(self):
        flat = ('\\begin{tabular}{lc}\n\\toprule\nA & B \\\\\n\\midrule\n'
                'x & 1 \\\\\ny & 2 \\\\\n\\bottomrule\n\\end{tabular}')
        got, groups = mb.split_row_groups(HTML, flat)
        self.assertEqual(groups, 0)
        self.assertEqual(got, HTML)

    def test_the_print_sheet_holds_a_group_together(self):
        self.assertIn('tbody.rowgroup', print_sheet())

    def test_a_header_is_not_left_without_rows(self):
        # Every group below refusing to break is what stranded a header at
        # the foot of a page with the table starting again on the next one.
        css = print_sheet()
        head = css[css.index('thead {'):css.index('thead {') + 160]
        self.assertIn('break-after: avoid', head)

    def test_an_inline_matrix_gets_room_between_its_rows(self):
        # Measured at 7.5pt between rows of 12.1pt type before this rule --
        # the two rows of a 2x2 overlapped and the worked example could not
        # be read. 14.2pt after.
        self.assertIn('math[display="inline"] mtable', print_sheet())


def print_sheet():
    template = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'scripts', 'template_ebook.html')
    with open(template, encoding='utf-8') as fh:
        return fh.read()


if __name__ == '__main__':
    unittest.main()
