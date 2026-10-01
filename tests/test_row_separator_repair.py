# -*- coding: utf-8 -*-
r"""`\ ` is the control space, and the row-separator repair ate it.

`math_guard.repair_display_math` restores a row separator that pandoc's LaTeX
reader truncated from `\\` to `\`. Its pattern allowed whitespace between the
backslash and the newline, on the written grounds that "a lone trailing
backslash before a newline is never valid LaTeX".

It is valid: `\ ` is TeX's explicit thin space. Shor writes

    R_j \ = \
    \begin{array}{c|cc|l}

and the repair turned that control space into a row separator inside an
`equation`, which texmath refuses — so both of his gate-transition tables
printed as LaTeX source in a shipped book. Bisected against pandoc, that stray
`\\` was the sole cause; `\\*[.5ex]` renders fine.

Corpus-wide the loose pattern matched two spans and both were this. A
truncated separator has NOTHING between the backslash and the newline, so
requiring that keeps every repair the loose form was written for.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import math_guard  # noqa: E402

NL = '\n'
B = chr(92)


class ATruncatedSeparatorIsStillRepaired(unittest.TestCase):
    def test_a_bare_backslash_before_a_newline(self):
        got = math_guard.repair_display_math('a &= b ' + B + NL + 'c &= d')
        self.assertEqual(got, 'a &= b ' + B + B + NL + 'c &= d')

    def test_several_rows(self):
        src = 'a ' + B + NL + 'b ' + B + NL + 'c'
        self.assertEqual(math_guard.repair_display_math(src),
                         'a ' + B + B + NL + 'b ' + B + B + NL + 'c')

    def test_an_already_doubled_separator_is_left_alone(self):
        src = 'a &= b ' + B + B + NL + 'c &= d'
        self.assertEqual(math_guard.repair_display_math(src), src)


class AControlSpaceSurvives(unittest.TestCase):
    def test_backslash_space_before_a_newline(self):
        src = 'R_j ' + B + ' = ' + B + ' ' + NL + B + 'begin{array}{cc}'
        self.assertEqual(math_guard.repair_display_math(src), src)

    def test_backslash_tab_before_a_newline(self):
        src = 'R ' + B + ' = ' + B + '\t' + NL + 'x'
        self.assertEqual(math_guard.repair_display_math(src), src)

    def test_shors_gate_table_keeps_its_single_backslash(self):
        src = (B + 'begin{equation}' + NL +
               'R_j ' + B + ' = ' + B + ' ' + NL +
               B + 'begin{array}{c|cc|l}' + NL +
               'a & b ' + B + B + '*[.5ex]' + NL +
               B + 'end{array}' + NL + B + 'end{equation}')
        got = math_guard.repair_display_math(src)
        self.assertNotIn('= ' + B + B, got)
        self.assertIn(B + B + '*[.5ex]', got)

    def test_a_control_space_mid_line_was_never_at_risk(self):
        src = 'a ' + B + ' b'
        self.assertEqual(math_guard.repair_display_math(src), src)


class TheBlankLineRepairStillWorks(unittest.TestCase):
    def test_a_blank_line_inside_a_formula_is_collapsed(self):
        got = math_guard.repair_display_math('a' + NL + NL + 'b')
        self.assertEqual(got, 'a' + NL + 'b')

    def test_a_single_newline_is_kept(self):
        self.assertEqual(math_guard.repair_display_math('a' + NL + 'b'),
                         'a' + NL + 'b')


if __name__ == '__main__':
    unittest.main()
