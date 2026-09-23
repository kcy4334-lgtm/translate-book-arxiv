# -*- coding: utf-8 -*-
r"""Sibling headings are siblings in the PDF outline too.

PyMuPDF refuses a bookmark depth that jumps by more than one, and every paper
jumps: `\paragraph` headings are h4 directly under an h1 section. The old
answer clamped each entry to one below the previous entry, which chained the
siblings. Looped flows' outline nested "Flow and diffusion models" inside
"Looped models" and went four deep under one section.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import chromium_pdf  # noqa: E402


class OutlineDepths(unittest.TestCase):
    def test_paragraph_siblings_share_a_depth(self):
        # 2 Background / Looped models. / Flow and diffusion models.
        self.assertEqual(chromium_pdf.outline_depths([1, 4, 4]), [1, 2, 2])

    def test_the_looped_flows_shape(self):
        # 4 Related work, five \paragraph headings, 5 Experiments,
        # 5.1, three \paragraph headings, 5.2.
        levels = [1, 4, 4, 4, 4, 4, 1, 2, 4, 4, 4, 2]
        self.assertEqual(chromium_pdf.outline_depths(levels),
                         [1, 2, 2, 2, 2, 2, 1, 2, 3, 3, 3, 2])

    def test_a_regular_ladder_is_unchanged(self):
        levels = [1, 2, 3, 3, 2, 1, 2]
        self.assertEqual(chromium_pdf.outline_depths(levels), levels)

    def test_no_depth_ever_jumps_by_more_than_one(self):
        # What PyMuPDF requires, on a deliberately ragged sequence.
        levels = [2, 6, 3, 1, 5, 5, 2, 4, 1]
        depths = chromium_pdf.outline_depths(levels)
        self.assertEqual(depths[0], 1)
        for before, after in zip(depths, depths[1:]):
            self.assertLessEqual(after, before + 1)

    def test_empty(self):
        self.assertEqual(chromium_pdf.outline_depths([]), [])


if __name__ == '__main__':
    unittest.main()
