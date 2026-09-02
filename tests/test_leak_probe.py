# -*- coding: utf-8 -*-
r"""Tests for the markup-residue probe.

The scan this replaces was a list of things that had already gone wrong, so
it could only ever be one build behind: `<!-- -->` printed twenty-one times
in AlphaQ while a scan looking for seven other shapes called the book clean,
and a reader found it.

The cases below are the real shapes that reached a page in this project.
The probe was told about NONE of them by name — it is told what a sentence
is made of, and these are not that. The negative cases are just as
important: every one of them was flagged by the first cut of this probe and
is legitimate rendered content.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import leak_probe as lp


def page(text):
    """Minimal HTML carrying `text` as body content."""
    return '<html><body><p>%s</p></body></html>' % text


class LeaksThatReachedAPage(unittest.TestCase):
    """Each of these printed to a reader in a real build."""

    def flagged(self, text):
        return dict(lp.candidates(lp.visible(page(text))))

    def test_an_html_comment_between_math_and_a_digit(self):
        # Found by a reader, not by the scan of the day.
        self.assertTrue(self.flagged('양자화한 Mixtral-8×&lt;!-- --&gt;7B에서'))

    def test_a_pandoc_raw_attribute(self):
        self.assertIn('{=latex}여기서', self.flagged('정의한다. {=latex}여기서 σ'))

    def test_a_spacing_directive(self):
        self.assertIn('{-2em}', self.flagged('그림 {-2em} 캡션'))

    def test_an_unresolved_label(self):
        self.assertTrue(self.flagged('그리고 (table-mixtral)에서 보듯이'))

    def test_a_citation_key(self):
        self.assertTrue(self.flagged('앞서 [@knuth1984] 참조'))

    def test_a_fenced_div(self):
        self.assertIn(':::', self.flagged('본문\n:::\n다음'))

    def test_math_delimiters_around_a_character(self):
        self.assertTrue(self.flagged('제목 QuIP$\\#$: Even better'))

    def test_a_numeric_entity(self):
        self.assertTrue(self.flagged('셀 &amp;#92;downarrow 값'))

    def test_a_double_question_mark(self):
        self.assertTrue(self.flagged('표 ??에서 보듯이'))


class WrittenAsALiteralInTheSource(unittest.TestCase):
    r"""The exception the paper declares for itself.

    DeeR-VLA's acknowledgement thanks the "National Key R&D Program", and the
    probe called that a leak on a book with nothing wrong with it. In LaTeX
    the author wrote `R\&D`: the backslash says this character is a word here.
    A column separator that escaped from a table is written BARE, so the
    source tells the two apart even though the page cannot.
    """

    SOURCE = r'thanks the National Key R\&D Program, and pick\&place tasks.'

    def flagged(self, text, source=SOURCE):
        return dict(lp.candidates(lp.visible(page(text)), source))

    def test_an_escaped_ampersand_is_content(self):
        self.assertEqual(self.flagged('국가 R&D 프로그램의 지원을 받았다'), {})

    def test_another_one_in_the_same_source(self):
        self.assertEqual(self.flagged('pick&place 과제에서'), {})

    def test_a_bare_separator_is_still_a_leak(self):
        """The source writes a column separator without the backslash."""
        self.assertIn('Method&Acc', self.flagged('셀 Method&Acc 값'))

    def test_a_token_the_source_never_escapes_is_still_a_leak(self):
        self.assertIn('R&D', self.flagged('국가 R&D 프로그램', source='no ampersands here'))

    def test_with_no_source_nothing_is_excused(self):
        self.assertIn('R&D', self.flagged('국가 R&D 프로그램', source=''))

    def test_other_syntax_in_the_token_defeats_the_exception(self):
        """`\\&` in the source must not license a brace or a backslash."""
        self.assertIn('{=latex}&x', self.flagged('본문 {=latex}&x 뒤'))

    def test_an_escaped_percent_is_content(self):
        self.assertEqual(
            dict(lp.candidates(lp.visible(page('정확도 50%p 향상')),
                               r'accuracy 50\%p higher')), {})


class ContentThatOnlyLooksLikeMarkup(unittest.TestCase):
    """Every one of these was flagged by the first cut and is legitimate."""

    def clean(self, text):
        return dict(lp.candidates(lp.visible(page(text))))

    def test_a_norm(self):
        self.assertEqual(self.clean('오차는 | w i − w ̂ i | ≤ 상한'), {})

    def test_set_notation(self):
        self.assertEqual(self.clean('학습률: { 0.1 , 0.5 , 1.0 }'), {})

    def test_an_inequality_in_prose(self):
        self.assertEqual(self.clean('전체적으로 &lt; 3 % 의 FLOPs를'), {})

    def test_two_authors_joined_by_an_ampersand(self):
        self.assertEqual(self.clean('(Williams &amp; Aletras 2024)'), {})

    def test_a_diagonal_table_header(self):
        self.assertEqual(self.clean('방법 \\ 가중치 FF QK VO'), {})

    def test_a_url(self):
        self.assertEqual(self.clean('코드는 https://github.com/a/b에서'), {})

    def test_a_code_span_is_not_page_prose(self):
        html = '<p>see <code>{=latex}</code> here</p>'
        self.assertEqual(dict(lp.candidates(lp.visible(html))), {})

    def test_the_tex_annotation_inside_mathml_is_not_page_prose(self):
        html = ('<p><math><mo>↓</mo><annotation encoding="application/x-tex">'
                '\\downarrow</annotation></math></p>')
        self.assertEqual(dict(lp.candidates(lp.visible(html))), {})


if __name__ == '__main__':
    unittest.main()
