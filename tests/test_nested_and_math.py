# -*- coding: utf-8 -*-
r"""Tests for three faults a fourth paper found in one afternoon.

Three papers of the same shape had exercised none of them.

A multi-line header cell is a `tabular` of its own, and taking the first
`\end{tabular}` cut the outer table off inside that cell: three of
DeeR-VLA's tables arrived as fragments pandoc could not read, and its eleven
tables were counted as fourteen.

`\setlength\abovedisplayskip{3pt}` sits inside all eight of that paper's
equations. texmath has no reader for it and refuses the whole formula, so
the `$$` printed as text. Taking only the command leaves a blank line, a
blank line ends the display block, and the dollars print anyway — measured,
8 unrendered spans became 12. The whole line has to go.

`\sideset{}{_{X}}\sum` has no reader either, but it has an EQUIVALENT:
`\sum\nolimits_{X}` says the same thing, and the same equation already used
`\nolimits` further along. The boundary is not where a command is
unimplemented, it is where the supported subset has no way to say it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

NESTED = (
    '\\begin{table}\n\\caption{Outer}\n'
    '\\begin{tabular}{cc}\n'
    'Method & \\begin{tabular}[c]{@{}c@{}}Only RGB\\\\ Input\\end{tabular} \\\\\n'
    'DeeR & yes \\\\\n'
    '\\end{tabular}\n\\end{table}\n')


class NestedTabular(unittest.TestCase):

    def test_the_outer_table_is_taken_whole(self):
        found = mb.find_raw_latex_tables(NESTED)
        self.assertEqual(len(found), 1)
        self.assertIn('DeeR & yes', found[0]['bare'])
        self.assertTrue(found[0]['bare'].rstrip().endswith('\\end{tabular}'))

    def test_the_inner_one_is_not_a_table_of_its_own(self):
        self.assertEqual(len(mb.find_raw_latex_tables(NESTED)), 1)

    def test_two_tables_side_by_side_are_still_two(self):
        doc = NESTED + '\n' + NESTED
        self.assertEqual(len(mb.find_raw_latex_tables(doc)), 2)

    def test_an_unbalanced_begin_does_not_cost_the_ones_before_it(self):
        doc = NESTED + '\n\\begin{tabular}{c}\nx \\\\\n'
        self.assertEqual(len(mb.find_raw_latex_tables(doc)), 1)


class SetLength(unittest.TestCase):

    def clean(self, text):
        return mb.normalize_latex_leftovers(text)[0]

    def test_the_whole_line_goes(self):
        got = self.clean('$$\\begin{equation}\n'
                         '\\setlength\\abovedisplayskip{3pt}\n'
                         'x = 1\n\\end{equation}$$\n')
        self.assertNotIn('setlength', got)
        # No blank line left behind: that is what ends the display block.
        self.assertNotIn('\n\n', got.strip())

    def test_the_braced_spelling_too(self):
        self.assertNotIn('setlength',
                         self.clean('a \\setlength{\\parskip}{0pt} b'))

    def test_ordinary_text_is_untouched(self):
        text = 'The length of the sequence is 3pt in the figure.'
        self.assertEqual(self.clean(text), text)


class Sideset(unittest.TestCase):

    def test_an_empty_left_argument_becomes_nolimits(self):
        got, n = mb.rewrite_sideset(
            r'\sideset{}{_{s \in \{s_1, s_2\}}} \sum x')
        self.assertEqual(got, r'\sum\nolimits_{s \in \{s_1, s_2\}} x')
        self.assertEqual(n, 1)

    def test_a_superscript_works_the_same(self):
        got, _n = mb.rewrite_sideset(r'\sideset{}{^{*}}\prod y')
        self.assertEqual(got, r'\prod\nolimits^{*} y')

    def test_both_sides_have_no_equivalent_and_are_left_alone(self):
        text = r'\sideset{_a^b}{_c^d}\sum x'
        self.assertEqual(mb.rewrite_sideset(text), (text, 0))

    def test_nothing_else_is_touched(self):
        text = r'\sum\nolimits_{i=0}^{H-1} f(i)'
        self.assertEqual(mb.rewrite_sideset(text), (text, 0))


if __name__ == '__main__':
    unittest.main()
