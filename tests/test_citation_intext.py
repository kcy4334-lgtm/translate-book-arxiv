# -*- coding: utf-8 -*-
r"""An author-in-text citation must resolve too, not just a bracketed one.

`\citep{key}` becomes `[@key]` and `\citet{key}` becomes a BARE `@key`,
because there the author's name carries the sentence. The resolver only
matched the bracketed form, so every `\citet` printed a raw bibtex key on the
page — CafeQ shipped five, one of them sitting immediately beside a citation
that had rendered perfectly, in a build where all 61 labels had been
harvested from the paper's own .bbl and were sitting in the map the resolver
was holding. Nothing failed; one pattern was narrower than the input.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab

MAP = {
    'adepu2024framequant': 'Adepu et al. 2024',
    'ashkboos2024quarot': 'Ashkboos et al. 2024b',
    'kim2025zero': 'Kim et al. 2025b',
    'dettmers2023case': r'Dettmers \& Zettlemoyer 2023',
    'nodate2024': 'Someone Without A Year',
}


def resolve(text):
    return ab.resolve_citation_keys(text, MAP)


class BareCitationTests(unittest.TestCase):
    def test_a_bare_key_becomes_an_author_in_text_citation(self):
        # The name carries the sentence, so the year is what goes in brackets.
        self.assertEqual(resolve('following @adepu2024framequant, we propose'),
                         'following Adepu et al. (2024), we propose')

    def test_a_year_suffix_survives(self):
        self.assertEqual(resolve('see @ashkboos2024quarot'),
                         'see Ashkboos et al. (2024b)')

    def test_a_label_with_no_year_is_used_as_is(self):
        self.assertEqual(resolve('per @nodate2024x'), 'per @nodate2024x')
        self.assertEqual(resolve('per @nodate2024'), 'per Someone Without A Year')

    # The `@A [@B]` shape CafeQ shipped is covered by ShapeTests below, which
    # asserts the merged group rather than the two-parenthesis intermediate.

    def test_the_bracketed_form_still_works(self):
        self.assertEqual(resolve('[@adepu2024framequant; @ashkboos2024quarot]'),
                         '(Adepu et al. 2024; Ashkboos et al. 2024b)')

    def test_korean_text_around_the_citation_is_untouched(self):
        out = resolve('레이어에 대해서는 @kim2025zero의 서베이를 참고하라.')
        self.assertEqual(out, '레이어에 대해서는 Kim et al. (2025b)의 서베이를 참고하라.')


class ShapeTests(unittest.TestCase):
    r"""`\citep{A, B}` can arrive split; it is still one citation."""

    def test_adjacent_citations_merge_into_one_group(self):
        out = resolve('works of @adepu2024framequant [@ashkboos2024quarot], we')
        self.assertEqual(
            out, 'works of (Adepu et al. 2024; Ashkboos et al. 2024b), we')

    def test_a_citation_inside_parentheses_drops_the_inner_brackets(self):
        # `(예: Dettmers & Zettlemoyer (2023))` nests brackets for no reason.
        out = resolve('방법(예: @dettmers2023case)은 반올림을 쓴다')
        self.assertEqual(out, r'방법(예: Dettmers \& Zettlemoyer 2023)은 반올림을 쓴다')

    def test_an_ordinary_aside_after_a_date_is_not_swallowed(self):
        text = 'Smith (2020) (see appendix) shows'
        self.assertEqual(resolve(text), text)

    def test_a_closed_parenthesis_does_not_count_as_enclosing(self):
        out = resolve('(앞 절) 이후 @kim2025zero의 서베이')
        self.assertEqual(out, '(앞 절) 이후 Kim et al. (2025b)의 서베이')


class SafetyTests(unittest.TestCase):
    """What must never be mistaken for a citation."""

    def test_an_email_address_is_left_alone(self):
        text = 'write to sam@example.com today'
        self.assertEqual(resolve(text), text)

    def test_an_unknown_key_is_left_alone_not_deleted(self):
        text = 'see @nosuchkey2099 for details'
        self.assertEqual(resolve(text), text)

    def test_an_escaped_at_is_left_alone(self):
        text = r'a literal \@adepu2024framequant here'
        self.assertEqual(resolve(text), text)

    def test_a_key_inside_a_word_is_left_alone(self):
        text = 'handle@adepu2024framequant'
        self.assertEqual(resolve(text), text)

    def test_sentence_punctuation_is_not_eaten(self):
        self.assertEqual(resolve('per @kim2025zero.'),
                         'per Kim et al. (2025b).')

    def test_an_empty_map_changes_nothing(self):
        text = 'following @adepu2024framequant, we propose'
        self.assertEqual(ab.resolve_citation_keys(text, {}), text)


if __name__ == '__main__':
    unittest.main()
