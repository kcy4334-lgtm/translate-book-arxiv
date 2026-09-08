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

# `source_probe` puts scripts/ on the path when it is imported.
import latex_rows  # noqa: E402
import merge_and_build as mb  # noqa: E402

ROW = '\\\\'


def block(env, rows, arg=''):
    joined = (' %s\n' % ROW).join('a_%d &= b' % n for n in range(rows))
    return '\\begin{%s}%s\n%s\n\\end{%s}' % (env, arg, joined, env)


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


class OneCounterNotTwo(unittest.TestCase):
    r"""The probe and the build used to count equations separately, and the
    two drifted in opposite directions.

    This file's rule -- a `\\` breaks a row only at brace and environment
    depth zero -- was written for the probe and copied nowhere, so the
    build had to learn it again. Meanwhile the build learned that `gather`
    numbers row by row, that `alignat` and `IEEEeqnarray` exist, and that
    `empheq` names its environment in an argument, and the probe never
    heard any of it. Neither list was wrong on purpose; each was simply
    the older one somewhere else.

    Measured on 2609.05354, which carries two `alignat` blocks and four
    `subequations`: with the counters merged and the printed markers
    counted properly, 57 numbered against 57 printed, exactly.
    """

    BODIES = [
        'a &= b',
        'a &= b %s c &= d' % ROW,
        '\\substack{i %s j} &= b %s c &= d' % (ROW, ROW),
        '\\begin{cases} a %s b \\end{cases} %s c &= d' % (ROW, ROW),
        '\\thead{Total %s Time}' % ROW,
    ]

    def test_align_rows_is_the_shared_splitter(self):
        for body in self.BODIES:
            self.assertEqual(sp.align_rows(body),
                             len(latex_rows.split_rows(body)), body[:40])

    def test_the_probe_counts_what_the_build_assigns(self):
        """The gate. Any environment the build learns, the probe sees."""
        for tex in (block('align', 3), block('gather', 3),
                    block('alignat', 2, '{2}'), block('equation', 1),
                    block('multline', 4), block('IEEEeqnarray', 2),
                    '\\begin{dmath}a = b\\end{dmath}',
                    '\\begin{empheq}[box=\\fbox]{align}\na &= b %s\nc &= d\n'
                    '\\end{empheq}' % ROW):
            counted, _printed = sp.check_equations(tex, [])
            self.assertEqual(counted, mb._numbers_for_block(tex), tex[:40])

    def test_the_environments_the_probe_used_to_miss(self):
        """Named one by one, because a shared call that silently returned
        zero would satisfy the test above."""
        self.assertEqual(sp.check_equations(block('gather', 3), [])[0], 3)
        self.assertEqual(sp.check_equations(block('alignat', 2, '{2}'),
                                            [])[0], 2)
        self.assertEqual(sp.check_equations(
            '\\begin{dmath}a = b\\end{dmath}', [])[0], 1)


class ASubequationsMarkerIsStillAMarker(unittest.TestCase):
    r"""`(2a)` and `(2.1a)` are equation numbers the reader sees. The
    printed-marker pattern took digits and dots only, so fourteen of
    2609.05354's fifty-seven were invisible to it -- an undercount that
    cancelled part of an overcount on the counting side, leaving a small
    disagreement that hid both."""

    def counted(self, *lines):
        return sp.check_equations('', list(lines))[1]

    def test_a_lettered_marker_counts(self):
        self.assertEqual(self.counted('(2a)', '(2b)'), 2)

    def test_a_lettered_marker_with_a_section_prefix_counts(self):
        self.assertEqual(self.counted('(2.1a)', '(2.1b)'), 2)

    def test_the_plain_forms_still_count(self):
        self.assertEqual(self.counted('(3)', '(2.1)'), 2)

    def test_a_bare_letter_is_not_an_equation_number(self):
        """`(a)` labels a subfigure, and this probe must not read it as a
        formula the paper numbered."""
        self.assertEqual(self.counted('(a)', '(b)'), 0)


if __name__ == '__main__':
    unittest.main()
