# -*- coding: utf-8 -*-
r"""The column pairs of an align row keep LaTeX's gap between them.

pandoc's MathML gives every cell of an `align` no padding, so ViT's equation
8, `[...]\,U_{msa} & U_{msa} \in \mathbb{R}^{...}`, printed "U_msa U_msa ∈":
the second pair started where the first ended.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb  # noqa: E402


def cell(align, text):
    return '<mtd columnalign="%s" style="text-align: %s">%s</mtd>' % (align, align, text)


class AlignmentPairs(unittest.TestCase):

    def test_the_second_pair_starts_after_a_gap(self):
        html = '<mtr>%s%s%s</mtr>' % (cell('right', 'a'), cell('left', '=b'),
                                       cell('right', 'c'))
        out = mb.space_alignment_pairs(html)
        self.assertEqual(out.count('padding-left: 2em'), 1)
        self.assertIn('padding-left: 2em; text-align: right">c', out)

    def test_a_single_pair_is_untouched(self):
        html = '<mtr>%s%s</mtr>' % (cell('right', 'a'), cell('left', '=b'))
        self.assertEqual(mb.space_alignment_pairs(html), html)

    def test_a_matrix_is_untouched(self):
        html = '<mtr>%s%s%s</mtr>' % (cell('center', '1'), cell('center', '0'),
                                       cell('center', '0'))
        self.assertEqual(mb.space_alignment_pairs(html), html)


if __name__ == '__main__':
    unittest.main()
