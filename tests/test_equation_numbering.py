# -*- coding: utf-8 -*-
r"""How many numbers LaTeX prints for each display environment.

`source_probe` compares the numbers this pipeline assigns against the `(N)`
markers printed in the paper's own PDF, so a miscount does not stay local:
every equation after it is off by the difference, and every `\ref` into them
points at the wrong one.

Two were wrong. `gather` numbers row by row, like `align`, and fell to the
one-per-block branch: a three-line gather counted 1 where the paper prints 3.
`alignat` was not in the pattern at all and counted 0.

They were found by feeding each environment to the counter directly, after
`corpus_census digest` listed `alignat` and `flalign` under NEVER SEEN.
Never seen means never tested, and one paper in the corpus already uses
`gather`, so this was live rather than hypothetical.

`multline` was right and stays here as a guard: it is a single equation broken
across lines for width, and it takes one number however many `\\` it holds.
Making it row-numbered would be the obvious wrong fix.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

ROW = '\\\\'


def block(env, rows, arg='', star=''):
    body = (' %s\n' % ROW).join('a_%d = b' % n for n in range(rows))
    return '\\begin{%s%s}%s\n%s\n\\end{%s%s}' % (env, star, arg, body,
                                                 env, star)


class OneNumberForTheWholeBlock(unittest.TestCase):

    def test_equation(self):
        self.assertEqual(mb._numbers_for_block(block('equation', 1)), 1)

    def test_multline_however_many_lines_it_breaks_across(self):
        r"""One equation, broken for width. Three `\\` do not make it three."""
        for rows in (1, 3, 6):
            self.assertEqual(mb._numbers_for_block(block('multline', rows)), 1,
                             '%d rows' % rows)


class OneNumberPerRow(unittest.TestCase):

    def test_align(self):
        self.assertEqual(mb._numbers_for_block(block('align', 3)), 3)

    def test_gather(self):
        """Was counted as one block. It numbers every line."""
        self.assertEqual(mb._numbers_for_block(block('gather', 3)), 3)

    def test_eqnarray(self):
        self.assertEqual(mb._numbers_for_block(block('eqnarray', 2)), 2)

    def test_flalign(self):
        self.assertEqual(mb._numbers_for_block(block('flalign', 2)), 2)

    def test_alignat_with_its_column_argument(self):
        """`\\begin{alignat}{2}` was not matched at all, so it counted zero."""
        self.assertEqual(mb._numbers_for_block(block('alignat', 2, '{2}')), 2)

    def test_ieee_eqnarray(self):
        self.assertEqual(mb._numbers_for_block(block('IEEEeqnarray', 2)), 2)

    def test_align_is_not_matched_inside_alignat(self):
        """The alternation lists the longer name first; `align` matching the
        opening of `alignat` would count its rows under the wrong rule."""
        got = mb._numbers_for_block(block('alignat', 4, '{3}'))
        self.assertEqual(got, 4)


class StarredFormsTakeNoNumber(unittest.TestCase):

    def test_every_environment_starred(self):
        for env in ('equation', 'align', 'gather', 'multline', 'eqnarray',
                    'flalign'):
            self.assertEqual(mb._numbers_for_block(block(env, 2, star='*')), 0,
                             env)


class SubequationsPrintsTheRowsItHolds(unittest.TestCase):
    r"""`subequations` prints (1a) and (1b) for a two-row align: two markers
    on the page, though the OUTER counter advances only once. Two different
    questions with two different answers, and this counter is asked the first
    one -- `source_probe` compares against the `(N)` markers the paper's PDF
    actually shows.

    The wrapper is not in the pattern and does not need to be: the inner
    environment is matched and counted by its rows, which is the marker count.
    Adding `subequations` as a one-per-block environment would break this.
    """

    def test_a_wrapped_align_counts_its_rows(self):
        body = ('\\begin{subequations}\n\\begin{align}\na &= b %s\nc &= d\n'
                '\\end{align}\n\\end{subequations}' % ROW)
        self.assertEqual(mb._numbers_for_block(body), 2)

    def test_a_wrapped_equation_still_counts_one(self):
        body = ('\\begin{subequations}\n\\begin{equation}\na = b\n'
                '\\end{equation}\n\\end{subequations}')
        self.assertEqual(mb._numbers_for_block(body), 1)


class SuppressedRows(unittest.TestCase):

    def test_nonumber_removes_one(self):
        body = ('\\begin{align}\na &= b %s\nc &= d \\nonumber %s\ne &= f\n'
                '\\end{align}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)

    def test_notag_removes_one(self):
        body = ('\\begin{gather}\na = b %s\nc = d \\notag %s\ne = f\n'
                '\\end{gather}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)


class BreqnBreaksTheLineItself(unittest.TestCase):
    r"""`dmath` was listed under NEVER SEEN and was not in the pattern, so
    it counted 0 where the paper prints one number. It is `equation` with
    automatic line breaking: however many lines it takes, it takes one
    number."""

    def test_dmath(self):
        self.assertEqual(mb._numbers_for_block(
            '\\begin{dmath}\na = b + c\n\\end{dmath}'), 1)

    def test_dmath_starred(self):
        self.assertEqual(mb._numbers_for_block(
            '\\begin{dmath*}\na = b\n\\end{dmath*}'), 0)


class EmpheqNamesItsEnvironmentAsAnArgument(unittest.TestCase):
    r"""`\begin{empheq}[box=\fbox]{align}` is an align, and a pattern
    hunting `\begin{align}` cannot see it: the name is in an ARGUMENT. It
    counted 0 for every boxed display."""

    def body(self, arg, rows):
        joined = (' %s\n' % ROW).join('a_%d &= b' % n for n in range(rows))
        return ('\\begin{empheq}%s\n%s\n\\end{empheq}' % (arg, joined))

    def test_a_boxed_align_numbers_its_rows(self):
        self.assertEqual(mb._numbers_for_block(
            self.body('[box=\\fbox]{align}', 2)), 2)

    def test_the_optional_argument_may_be_absent(self):
        self.assertEqual(mb._numbers_for_block(self.body('{align}', 3)), 3)

    def test_a_boxed_equation_takes_one(self):
        self.assertEqual(mb._numbers_for_block(
            self.body('[left=\\empheqlbrace]{equation}', 1)), 1)

    def test_a_starred_inner_environment_prints_none(self):
        self.assertEqual(mb._numbers_for_block(
            self.body('[box=\\fbox]{align*}', 2)), 0)

    def test_an_unreadable_argument_is_read_as_one(self):
        """A box round something is still a display. Guessing zero would
        delete a number; guessing many would invent them."""
        self.assertEqual(mb._numbers_for_block(
            '\\begin{empheq}\na = b\n\\end{empheq}'), 1)


class ABreakInsideANestedEnvironmentIsNotARow(unittest.TestCase):
    r"""Measured, and both shapes are ordinary in a machine learning paper.
    The counter read every `\\` in the block, so the `cases` on one line of
    an `align` added a number LaTeX does not print, and everything after it
    was off by one."""

    def test_cases_inside_align(self):
        body = ('\\begin{align}\n'
                'f(x) &= \\begin{cases} a %s b \\end{cases} %s\n'
                'g(x) &= c\n\\end{align}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)

    def test_substack_inside_align(self):
        body = ('\\begin{align}\n'
                '\\sum_{\\substack{i=1 %s j=2}} x_i &= y %s\n'
                'z &= w\n\\end{align}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)

    def test_a_matrix_inside_an_equation_was_already_right(self):
        """`equation` takes one number however many rows its matrix has,
        so this never depended on the row count. Kept because a counter
        rewritten to count rows everywhere would fail it."""
        body = ('\\begin{equation}\n'
                'M = \\begin{pmatrix} a & b %s c & d \\end{pmatrix}\n'
                '\\end{equation}' % ROW)
        self.assertEqual(mb._numbers_for_block(body), 1)

    def test_a_multi_line_cell_does_not_add_a_number(self):
        body = ('\\begin{align}\n'
                'a &= \\text{one %s two} %s\n'
                'b &= c\n\\end{align}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)


if __name__ == '__main__':
    unittest.main()
