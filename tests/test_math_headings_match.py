# -*- coding: utf-8 -*-
r"""A section title with maths in it matched nothing in the original PDF.

`_normalize_heading` deletes `$...$`, because two renderings of a formula never
agree character for character. The PDF side has nothing to delete:
`\section{Smooth choice of $y$}` prints as "Smooth choice of y". So the LaTeX
key stops one letter short of the PDF key, the exact test misses, and
`_longest_prefix_match` cannot help — it looks for the opposite relation, a PDF
key that the LaTeX key starts with.

Three of Maynard's ten sections are written that way and all three came back
"not found", so the pipeline never learned their printed numbers. The same gap
on the rendering side left their contents rows blank (K126).

The fallback is deliberately narrow. A heading that is a genuine prefix of
another must stay unmatched rather than take its neighbour's number, so it
fires only when the title really contains maths AND exactly one candidate
extends it.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class TheKeysNoLongerAgree(unittest.TestCase):
    def test_the_latex_side_drops_the_maths(self):
        self.assertEqual(mb._normalize_heading('Smooth choice of $y$'),
                         'smooth choice of')

    def test_the_pdf_side_keeps_the_letter(self):
        self.assertEqual(mb._normalize_heading('Smooth choice of y'),
                         'smooth choice of y')


class TheFallbackBridgesIt(unittest.TestCase):
    def setUp(self):
        self.numbered = {
            'smooth choice of y': '6',
            'choice of smooth weight for large k': '7',
            'choice of weight for small k': '8',
            'selberg sieve manipulations': '5',
        }

    def match(self, title):
        key = mb._normalize_heading(title)
        return mb._math_extended_match(title, key, self.numbered)

    def test_all_three_maynard_titles_resolve(self):
        for title, want in (('Smooth choice of $y$', 'smooth choice of y'),
                            ('Choice of smooth weight for large $k$',
                             'choice of smooth weight for large k'),
                            ('Choice of weight for small $k$',
                             'choice of weight for small k')):
            self.assertEqual(self.match(title), want)

    def test_a_title_without_maths_is_not_extended(self):
        self.assertIsNone(self.match('Selberg sieve'))

    def test_an_ambiguous_extension_is_refused(self):
        numbered = {'notation and conventions': '3', 'notation and proofs': '4'}
        key = mb._normalize_heading('Notation $x$')
        self.assertIsNone(mb._math_extended_match('Notation $x$', key, numbered))

    def test_a_very_short_key_is_refused(self):
        # Too little evidence to be sure which heading it is.
        numbered = {'the set a': '2'}
        self.assertIsNone(mb._math_extended_match('The $A$', 'the', numbered))

    def test_an_exact_key_is_not_matched_to_itself(self):
        self.assertIsNone(mb._math_extended_match(
            'Selberg sieve manipulations $x$', 'selberg sieve manipulations',
            {'selberg sieve manipulations': '5'}))


if __name__ == '__main__':
    unittest.main()
