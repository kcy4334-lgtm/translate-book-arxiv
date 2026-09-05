# -*- coding: utf-8 -*-
r"""CJK emphasis prints bold; Latin emphasis keeps its italics.

No CJK face this pipeline can rely on has a real italic, so the print sheet
substitutes bold rather than let Chromium synthesise an oblique. For Chinese
that synthesis is not merely ugly: Chromium emits it as a Type3 object, one
per glyph, which is the failure the rule "static, 0 Type3" exists to refuse.

The rule was first written `:lang(ko) em`, and the root element is
`lang="ko"`, so it matched EVERY <em> in the book. `\textit{16.67}` and
`\textit{Wiki2}` printed bold inside tables whose caption says the best
result is the bold one, and ten of SINQ's tables showed their FP16 baseline
row as the winner. So the decision is made from what the element CONTAINS and
never from the document language.

It was then Hangul-only, and Chinese emphasis went on producing Type3 long
after the Korean case was closed.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb


class EveryBoldChineseElementReachesAFaceWithABold(unittest.TestCase):
    r"""A table header is bold without any `<strong>` in it.

    The print sheet routes bold Chinese to the sans stack because 宋体 has no
    bold companion and Chromium synthesises one as a Type3 object per glyph.
    The selector listed `strong`, `b` and the two emphasis classes, all of
    which are markup somebody wrote. A `<th>` is bold by the browser's own
    stylesheet instead, so nothing matched it, and the Chinese edition
    carried 97 synthesised glyphs across its three table pages while Korean
    and Japanese carried none.

    Asserted against the template rather than a render: the suite runs on the
    standard library and there is no browser on CI.
    """

    def sheet(self):
        import io
        path = os.path.join(ROOT, 'scripts', 'template_ebook.html')
        with io.open(path, encoding='utf-8') as handle:
            return handle.read()

    def sans_rule(self):
        """The declaration block that sends bold Chinese to the sans stack."""
        text = self.sheet()
        at = text.index('html:lang(zh) strong')
        return text[at:text.index('}', at)]

    def test_a_chinese_table_header_is_in_the_sans_stack(self):
        self.assertIn('html:lang(zh) th', self.sans_rule())

    def test_the_rule_still_covers_what_it_always_did(self):
        rule = self.sans_rule()
        for selector in ('html:lang(zh) strong', 'html:lang(zh) b',
                         'html:lang(zh) em.cjk', 'html:lang(zh) i.cjk'):
            self.assertIn(selector, rule)
        self.assertIn('var(--p-sans)', rule)

    def test_korean_and_japanese_are_left_alone(self):
        r"""They reach HCR Batang and BIZ UDMincho, which ship a bold, so
        sending their headers to a gothic would change the page for nothing.

        Asked of the sans rule and not of the whole sheet: `html:lang(ja) th`
        appears elsewhere in perfectly good standing, in the rule that turns
        `word-break: keep-all` off for languages that do not put spaces
        between words. A first version of this test searched the file and
        failed on that."""
        rule = self.sans_rule()
        self.assertNotIn('lang(ko)', rule)
        self.assertNotIn('lang(ja)', rule)


class PunctuationStaysWithItsFormula(unittest.TestCase):
    r"""A line may not open with `。`.

    The Chinese edition printed one that did. The line before it ended on an
    inline formula and there is no space between them -- the HTML reads
    `</math>。` -- so Chromium took the break opportunity it puts beside a
    replaced element, where the rule against breaking before closing
    punctuation should already have refused.

    U+2060 WORD JOINER is what the standard provides: a break is forbidden on
    either side of it, and that outranks the replaced-element rule. It prints
    nothing.
    """

    WJ = '⁠'

    def test_a_full_stop_is_held_against_the_formula(self):
        html, n = mb.join_maths_to_following_punctuation(
            '<p>记为 <math display="inline"><mi>k</mi></math>。在我们的实验中</p>')
        self.assertEqual(n, 1)
        self.assertIn('</math>' + self.WJ + '。', html)

    def test_every_closing_mark_that_may_not_open_a_line(self):
        for mark in '。、，；：？！）》」』':
            html, n = mb.join_maths_to_following_punctuation(
                '<math><mi>x</mi></math>%s' % mark)
            self.assertEqual(n, 1, mark)
            self.assertIn('</math>' + self.WJ + mark, html)

    def test_korean_and_japanese_get_it_too(self):
        r"""The prohibition belongs to the punctuation, not to the language.
        Neither book broke in this paper, which is where its lines happened
        to fall rather than a difference in kind."""
        for text in ('<math><mi>k</mi></math>。본문', '<math><mi>k</mi></math>」と'):
            _html, n = mb.join_maths_to_following_punctuation(text)
            self.assertEqual(n, 1, text)

    def test_a_latin_full_stop_is_left_alone(self):
        r"""English and French break perfectly well after a formula, and a
        joiner there would be an invisible character for nothing."""
        for tail in ('. The next', ', and then', ') so'):
            _html, n = mb.join_maths_to_following_punctuation(
                '<math><mi>x</mi></math>%s' % tail)
            self.assertEqual(n, 0, tail)

    def test_an_opening_mark_is_left_alone(self):
        """`（` may not END a line; that is a different rule and no formula
        precedes it here."""
        _html, n = mb.join_maths_to_following_punctuation(
            '<math><mi>x</mi></math>（注）')
        self.assertEqual(n, 0)

    def test_a_document_with_no_maths_is_untouched(self):
        text = '<p>本文には数式がない。</p>'
        self.assertEqual(mb.join_maths_to_following_punctuation(text),
                         (text, 0))


class MarkTests(unittest.TestCase):

    def test_korean_emphasis_is_marked(self):
        html, n = mb.mark_cjk_emphasis('<p><em>강조된 말</em></p>')
        self.assertEqual(n, 1)
        self.assertIn('<em class="cjk">강조된 말</em>', html)

    def test_chinese_emphasis_is_marked(self):
        """`即` and `只` were the last two Type3 glyphs in the Chinese
        edition, both of them a one-word italic run."""
        html, n = mb.mark_cjk_emphasis('<p>他<em>即</em>是</p>')
        self.assertEqual(n, 1)
        self.assertIn('<em class="cjk">即</em>', html)

    def test_japanese_kana_emphasis_is_marked(self):
        html, n = mb.mark_cjk_emphasis('<em>すなわち</em>')
        self.assertEqual(n, 1)
        self.assertIn('class="cjk"', html)

    def test_japanese_kanji_emphasis_is_marked(self):
        html, n = mb.mark_cjk_emphasis('<em>蒸留</em>')
        self.assertEqual(n, 1)

    def test_latin_emphasis_is_left_alone(self):
        html, n = mb.mark_cjk_emphasis('<td><em>16.67</em></td>')
        self.assertEqual(n, 0)
        self.assertEqual(html, '<td><em>16.67</em></td>')

    def test_a_latin_word_in_a_table_header_keeps_its_italics(self):
        html, _n = mb.mark_cjk_emphasis('<th><em>Wiki2</em></th>')
        self.assertNotIn('cjk', html)

    def test_mixed_content_counts_as_cjk(self):
        html, n = mb.mark_cjk_emphasis('<em>Qwen3 모델</em>')
        self.assertEqual(n, 1)
        self.assertIn('class="cjk"', html)

    def test_the_i_tag_is_handled_too(self):
        html, n = mb.mark_cjk_emphasis('<i>기울임</i>')
        self.assertEqual(n, 1)
        self.assertIn('<i class="cjk">기울임</i>', html)

    def test_an_existing_class_is_kept(self):
        html, _n = mb.mark_cjk_emphasis('<em class="lead">머리말</em>')
        self.assertIn('class="lead cjk"', html)

    def test_nested_markup_does_not_hide_the_cjk(self):
        html, n = mb.mark_cjk_emphasis('<em><strong>굵고 기울임</strong></em>')
        self.assertEqual(n, 1)

    def test_tags_alone_are_not_mistaken_for_content(self):
        # The tag names are Latin; only the TEXT decides.
        html, n = mb.mark_cjk_emphasis('<em><span class="x">42</span></em>')
        self.assertEqual(n, 0)

    def test_every_emphasis_in_a_document_is_visited(self):
        src = '<p><em>가</em> and <em>b</em> and <i>中</i></p>'
        html, n = mb.mark_cjk_emphasis(src)
        self.assertEqual(n, 2)
        self.assertEqual(len(re.findall(r'class="cjk"', html)), 2)

    def test_the_stylesheet_targets_the_class_and_not_the_language(self):
        css = open(os.path.join(ROOT, 'scripts', 'template_ebook.html'),
                   encoding='utf-8').read()
        self.assertIn('em.cjk', css)
        self.assertNotIn(':lang(ko) em', css,
                         'the language selector matched every <em> in the book')


if __name__ == '__main__':
    unittest.main()
