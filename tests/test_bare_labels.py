# -*- coding: utf-8 -*-
r"""Tests for a cross-reference whose label carries no prefix.

References are matched by their prefix — `(tab:x)`, `(fig:y)`. AlphaQ labels
one of its tables `\label{table-mixtral}` with no prefix at all, so nothing
matched it: page 27 printed `표 7, 표 8, 그리고 (table-mixtral)에서 보듯이`,
showing the reader a raw internal label and losing the pointer to table 9.

The trap is that these pages are full of parenthesised English. The same
paper has a section labelled `HT-SR`, and `(HT-SR)` is also how the text
introduces the acronym — so a looser rule would rewrite an acronym gloss
into a section number. Hence two guards: floats only, and only where a
space precedes the bracket.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

FLAT = (r'\begin{table}' '\n'
        r'\caption{First}\label{tab:first}' '\n'
        r'\end{table}' '\n'
        r'\begin{table}' '\n'
        r'\caption{Second}\label{table-mixtral}' '\n'
        r'\end{table}' '\n'
        r'\section{Theory}\label{HT-SR}' '\n')

WORDS = {'figure': '그림', 'table': '표', 'section': '절'}
FORMATS = {}


class BareFloatLabels(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix='tb-bare-')
        with open(os.path.join(self.temp, 'flat.tex'), 'w',
                  encoding='utf-8') as fh:
            fh.write(FLAT)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def resolve(self, text):
        return mb.resolve_bare_float_labels(text, self.temp, WORDS, FORMATS)

    def test_a_prefixless_table_label_becomes_its_number(self):
        got, n = self.resolve('표 7, 표 8, 그리고 (table-mixtral)에서 보듯이')
        self.assertEqual(got, '표 7, 표 8, 그리고 표 2에서 보듯이')
        self.assertEqual(n, 1)

    def test_an_acronym_gloss_is_not_a_reference(self):
        # No space before the bracket: this is a term introducing itself.
        text = 'Heavy-Tailed Self-Regularization(HT-SR) 이론은'
        self.assertEqual(self.resolve(text), (text, 0))

    def test_a_section_label_is_not_eligible_even_with_a_space(self):
        # Only floats. A section label is exactly the kind that collides
        # with an acronym.
        text = '앞의 (HT-SR) 참고'
        self.assertEqual(self.resolve(text), (text, 0))

    def test_an_english_gloss_that_is_not_a_label_is_untouched(self):
        text = '비트 폭 (bit-width) 과 제로샷 (zero-shot) 은'
        self.assertEqual(self.resolve(text), (text, 0))

    def test_a_prefixed_label_still_resolves_here_too(self):
        got, n = self.resolve('앞서 (tab:first) 에서')
        self.assertEqual(got, '앞서 표 1 에서')
        self.assertEqual(n, 1)

    def test_no_flat_tex_is_not_an_error(self):
        empty = tempfile.mkdtemp(prefix='tb-bare-none-')
        try:
            text = '그리고 (table-mixtral)에서'
            self.assertEqual(
                mb.resolve_bare_float_labels(text, empty, WORDS, FORMATS),
                (text, 0))
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
