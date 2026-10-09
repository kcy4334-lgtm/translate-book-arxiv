# -*- coding: utf-8 -*-
r"""A block LaTeX numbers row by row prints a number on each row.

`equation_numbers` leaves such a block unlabelled, since one flush-right label
cannot stand for four rows, and pandoc drops `\tag`. So the block printed no
number at all: ViT's eight equations showed one between them, while the text
referred to (2) to (7). The numbers now go into the TeX, in a column of their
own after the widest row, so they line up and the rows keep their alignment.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import numbering  # noqa: E402

BS = '\\'
NL = '\n'


def _block(env, rows):
    return ('$$' + BS + 'begin{%s}' % env + NL
            + (' ' + BS + BS + NL).join(rows) + NL
            + BS + 'end{%s}$$' % env)


class EquationRows(unittest.TestCase):

    def test_each_row_carries_its_number_in_one_column(self):
        md = (_block('equation', ['x = 1']) + '\n\n'
              + _block('align', ['a &= b', 'c &= d && e']))
        out, n = numbering.tag_equation_rows(md)
        self.assertEqual(n, 2)
        self.assertIn('a &= b &&& ' + BS + 'qquad(2)', out)
        self.assertIn('c &= d && e & ' + BS + 'qquad(3)', out)
        # the one-number block is left to the per-path labelling
        self.assertIn(BS + 'begin{equation}' + NL + 'x = 1' + NL, out)

    def test_a_nonumber_row_gets_none(self):
        md = _block('align', ['a &= b ' + BS + 'nonumber', 'c &= d', 'e &= f'])
        out, n = numbering.tag_equation_rows(md)
        self.assertEqual(n, 2)
        self.assertNotIn('b ' + BS + 'nonumber &', out)
        self.assertIn(BS + 'qquad(1)', out)
        self.assertIn(BS + 'qquad(2)', out)

    def test_a_starred_block_is_untouched(self):
        md = _block('align*', ['a &= b', 'c &= d'])
        self.assertEqual(numbering.tag_equation_rows(md), (md, 0))

    def test_an_ampersand_inside_cases_is_not_a_column(self):
        cases = 'f &= ' + BS + 'begin{cases} 1 & x ' + BS + BS + ' 0 & y ' + BS + 'end{cases}'
        md = _block('align', [cases, 'g &= h'])
        out, _n = numbering.tag_equation_rows(md)
        self.assertIn(BS + 'end{cases} & ' + BS + 'qquad(1)', out)
        self.assertIn('g &= h & ' + BS + 'qquad(2)', out)

    def test_gather_has_no_columns_to_add(self):
        md = _block('gather', ['a = b', 'c = d'])
        out, n = numbering.tag_equation_rows(md)
        self.assertEqual(n, 2)
        self.assertIn('a = b ' + BS + 'qquad(1)', out)
        self.assertNotIn('&', out)

    def test_the_count_of_numbers_does_not_change(self):
        md = _block('align', ['a &= b', 'c &= d', 'e &= f'])
        out, _n = numbering.tag_equation_rows(md)
        before = [w for _s, _e, w in numbering.equation_numbers(md)]
        after = [w for _s, _e, w in numbering.equation_numbers(out)]
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
