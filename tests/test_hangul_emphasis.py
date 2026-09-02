# -*- coding: utf-8 -*-
r"""Korean emphasis prints bold; Latin emphasis keeps its italics.

Hangul has no italic, so the print sheet substitutes bold. That rule was
written `:lang(ko) em` — and the root element is `lang="ko"`, so it matched
EVERY <em> in the book. `\textit{16.67}` and `\textit{Wiki2}` printed bold
inside tables whose caption says the best result is the bold one, and ten of
SINQ's tables showed their FP16 baseline row as the winner.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb


class MarkTests(unittest.TestCase):
    def test_korean_emphasis_is_marked(self):
        html, n = mb.mark_hangul_emphasis('<p><em>강조된 말</em></p>')
        self.assertEqual(n, 1)
        self.assertIn('<em class="hangul">강조된 말</em>', html)

    def test_latin_emphasis_is_left_alone(self):
        html, n = mb.mark_hangul_emphasis('<td><em>16.67</em></td>')
        self.assertEqual(n, 0)
        self.assertEqual(html, '<td><em>16.67</em></td>')

    def test_a_latin_word_in_a_table_header_keeps_its_italics(self):
        html, _n = mb.mark_hangul_emphasis('<th><em>Wiki2</em></th>')
        self.assertNotIn('hangul', html)

    def test_mixed_content_counts_as_korean(self):
        html, n = mb.mark_hangul_emphasis('<em>Qwen3 모델</em>')
        self.assertEqual(n, 1)
        self.assertIn('class="hangul"', html)

    def test_the_i_tag_is_handled_too(self):
        html, n = mb.mark_hangul_emphasis('<i>기울임</i>')
        self.assertEqual(n, 1)
        self.assertIn('<i class="hangul">기울임</i>', html)

    def test_an_existing_class_is_kept(self):
        html, _n = mb.mark_hangul_emphasis('<em class="lead">머리말</em>')
        self.assertIn('class="lead hangul"', html)

    def test_nested_markup_does_not_hide_the_hangul(self):
        html, n = mb.mark_hangul_emphasis('<em><strong>굵고 기울임</strong></em>')
        self.assertEqual(n, 1)

    def test_tags_alone_are_not_mistaken_for_content(self):
        # The tag names are Latin; only the TEXT decides.
        html, n = mb.mark_hangul_emphasis('<em><span class="x">42</span></em>')
        self.assertEqual(n, 0)

    def test_every_emphasis_in_a_document_is_visited(self):
        src = '<p><em>가</em> and <em>b</em> and <i>다</i></p>'
        html, n = mb.mark_hangul_emphasis(src)
        self.assertEqual(n, 2)
        self.assertEqual(len(re.findall(r'class="hangul"', html)), 2)

    def test_the_stylesheet_targets_the_class_and_not_the_language(self):
        css = open(os.path.join(ROOT, 'scripts', 'template_ebook.html'),
                   encoding='utf-8').read()
        self.assertIn('em.hangul', css)
        self.assertNotIn(':lang(ko) em', css,
                         'the language selector matched every <em> in the book')


if __name__ == '__main__':
    unittest.main()
