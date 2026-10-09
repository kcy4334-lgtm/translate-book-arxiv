# -*- coding: utf-8 -*-
r"""A citation list in escaped brackets is prose, not display maths.

Shor cites `[Teich et al. 1988, Lloyd 1993, ..., Chuang and Yamomoto 1995]`.
pandoc escapes the brackets, the HTML reader reads `\[...\]` as display
maths, and since equation numbers are assigned to display formulas in
order, every number after it landed one formula late: (2.2) was put on the
citation list and the build refused the book.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import latex_cleanup  # noqa: E402

BS = '\\'


class EscapedCitationBrackets(unittest.TestCase):

    def test_a_long_citation_list_is_unbracketed(self):
        text = ('designs ' + BS + '[Teich et al. 1988, Lloyd 1993, 1994, '
                'Cirac and Zoller 1995, Barenco et al. 1995b' + BS + '], but')
        out, stats = latex_cleanup.normalize_latex_leftovers(text)
        self.assertIn('[Teich et al. 1988', out)
        self.assertNotIn(BS + '[', out)
        self.assertEqual(stats['brackets'], 1)

    def test_a_display_formula_stays(self):
        text = 'so ' + BS + '[ x + y = z ' + BS + '] holds'
        out, _stats = latex_cleanup.normalize_latex_leftovers(text)
        self.assertIn(BS + '[ x + y = z ' + BS + ']', out)

    def test_a_long_run_without_words_stays(self):
        text = BS + '[' + ', '.join('a_%d' % i for i in range(20)) + BS + ']'
        out, _stats = latex_cleanup.normalize_latex_leftovers(text)
        self.assertIn(BS + '[', out)

    def test_a_formula_inside_text_brackets_stays_a_formula(self):
        # PaLM's language list: `[en/es/ru/tr/vi $\to$ en]`, written with \rightarrow.
        text = ('sentences. ' + BS + '[en/es/ru/tr/vi $' + BS + 'rightarrow$ en'
                + BS + ']')
        out, stats = latex_cleanup.normalize_latex_leftovers(text)
        self.assertEqual(out, 'sentences. [en/es/ru/tr/vi $' + BS
                         + 'rightarrow$ en]')
        self.assertEqual(stats['brackets'], 1)


if __name__ == '__main__':
    unittest.main()
