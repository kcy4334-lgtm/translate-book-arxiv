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


class SuppressedRows(unittest.TestCase):

    def test_nonumber_removes_one(self):
        body = ('\\begin{align}\na &= b %s\nc &= d \\nonumber %s\ne &= f\n'
                '\\end{align}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)

    def test_notag_removes_one(self):
        body = ('\\begin{gather}\na = b %s\nc = d \\notag %s\ne = f\n'
                '\\end{gather}' % (ROW, ROW))
        self.assertEqual(mb._numbers_for_block(body), 2)


if __name__ == '__main__':
    unittest.main()
