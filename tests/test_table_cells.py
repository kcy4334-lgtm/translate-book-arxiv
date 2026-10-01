# -*- coding: utf-8 -*-
r"""`\makecell` and `\thead` empty the cell they are supposed to format.

Both exist to put a line break inside one table cell. pandoc has no reader for
either, so it drops the command TOGETHER WITH its argument: the cell arrives as
`<td></td>` and nothing anywhere reports it. PaLM writes 92 of them.

That is K110's swallow at cell scale, and it is invisible in every check that
counts tables rather than reading them — which is why these tests exist.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class CellWrappersKeepTheirText(unittest.TestCase):
    def test_makecell_rows_join_with_a_space(self):
        got, n = mb.unwrap_table_cell_wrappers(r'| \makecell{one\\two} | x |')
        self.assertEqual(got, '| one two | x |')
        self.assertEqual(n, 1)

    def test_thead_behaves_the_same(self):
        got, n = mb.unwrap_table_cell_wrappers(r'| \thead{a\\b} | y |')
        self.assertEqual(got, '| a b | y |')
        self.assertEqual(n, 1)

    def test_the_optional_argument_is_consumed(self):
        # `\makecell[l]{...}` dropped its cell exactly as the bare form did,
        # so the alignment option must not be left behind either.
        got, n = mb.unwrap_table_cell_wrappers(r'| \makecell[l]{a\\b} | y |')
        self.assertEqual(got, '| a b | y |')
        self.assertEqual(n, 1)

    def test_a_single_line_cell_still_unwraps(self):
        got, n = mb.unwrap_table_cell_wrappers(r'| \makecell{single} | z |')
        self.assertEqual(got, '| single | z |')
        self.assertEqual(n, 1)

    def test_two_wrappers_in_one_row(self):
        got, n = mb.unwrap_table_cell_wrappers(
            r'| \makecell{a\\b} | \thead{c\\d} |')
        self.assertEqual(got, '| a b | c d |')
        self.assertEqual(n, 2)

    def test_nested_braces_survive(self):
        got, _ = mb.unwrap_table_cell_wrappers(
            r'| \makecell{\textbf{a}\\b} | x |')
        self.assertEqual(got, r'| \textbf{a} b | x |')

    def test_a_row_without_either_is_untouched(self):
        row = '| plain | w |'
        self.assertEqual(mb.unwrap_table_cell_wrappers(row), (row, 0))

    def test_an_unbalanced_brace_does_not_hang_or_corrupt(self):
        row = r'| \makecell{a\\b | x |'
        got, n = mb.unwrap_table_cell_wrappers(row)
        self.assertEqual((got, n), (row, 0))


if __name__ == '__main__':
    unittest.main()
