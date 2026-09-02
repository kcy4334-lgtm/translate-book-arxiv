# -*- coding: utf-8 -*-
r"""A `\\` inside `\substack{}` is not a row break.

`source_probe.check_equations` used to model an align block as
`body.count('\\\\') + 1`. Maynard writes 74 `\substack{a\\b}` and three
`\begin{cases}...\\...\end{cases}`, so the probe claimed 167 numbered
equations about a paper that prints 106 and failed a book whose numbering was
never in question. That is K124's shape — a check reading structure it should
have skipped, then reporting the difference as damage.

`source_probe.py` is deliberately not named `test_*.py` (it needs PyMuPDF and
a reference PDF, and CI runs stdlib-only), so this file tests the one function
in it that is pure string work and can be exercised without either.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import source_probe as sp  # noqa: E402


class RowsBreakOnlyAtTheTopLevel(unittest.TestCase):
    def test_a_single_row(self):
        self.assertEqual(sp.align_rows(r'a &= b'), 1)

    def test_two_rows(self):
        self.assertEqual(sp.align_rows('a &= b' + '\\\\' + 'c &= d'), 2)

    def test_a_break_inside_substack_is_not_a_row(self):
        body = r'S_1 &= \sum_{\substack{N\le n<2N\\ n\equiv v_0}} f(n)'
        self.assertEqual(sp.align_rows(body), 1)

    def test_two_rows_each_carrying_a_substack(self):
        body = (r'S_1 &= \sum_{\substack{a\\b}} f'
                '\\\\'
                r'S_2 &= \sum_{\substack{c\\d}} g')
        self.assertEqual(sp.align_rows(body), 2)

    def test_a_break_inside_cases_is_not_a_row(self):
        body = r'\gamma(p) &= \begin{cases}1, &p\nmid W,\\ 0,&\text{else}\end{cases}'
        self.assertEqual(sp.align_rows(body), 1)

    def test_a_break_inside_a_nested_matrix_is_not_a_row(self):
        body = r'M &= \begin{pmatrix}1&0\\0&1\end{pmatrix}'
        self.assertEqual(sp.align_rows(body), 1)

    def test_an_escaped_brace_does_not_shift_the_depth(self):
        # `\{` and `\}` are literal braces in maths and must not open or close
        # a group, or every row after one would be miscounted.
        body = r'A &= \{x\}' '\\\\' r'B &= \{y\}'
        self.assertEqual(sp.align_rows(body), 2)

    def test_an_unbalanced_brace_does_not_go_negative(self):
        self.assertEqual(sp.align_rows('a} &= b' + '\\\\' + 'c &= d'), 2)

    def test_the_naive_model_would_disagree_here(self):
        # The regression this file exists for, stated as a comparison.
        body = r'S &= \sum_{\substack{a\\b\\c}} f'
        self.assertEqual(body.count('\\\\') + 1, 3)
        self.assertEqual(sp.align_rows(body), 1)


if __name__ == '__main__':
    unittest.main()
