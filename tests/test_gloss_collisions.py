# -*- coding: utf-8 -*-
r"""Tests for the gloss-collision check's calibration.

The check reports a term glossed two ways. It was reporting 22 for CafeQ,
and most of them were its own doing: the gloss pattern takes up to two words
in front of the term so that `블록 대각 행렬` survives whole, and those words
made one `어블레이션` look like three renderings. A citation with a
disambiguating letter -- `Tseng et al. 2024c` -- also read as English, so
`양자화` was reported as clashing with a surname.

A check nobody believes is worse than no check: the real defect this session
was found by hand while two dozen false alarms stood. So the fixtures below
hold it to both duties -- silent on what is fine, loud on what is not.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import consistency_probe as cp


class Citations(unittest.TestCase):

    def test_year_with_a_disambiguating_letter(self):
        self.assertTrue(cp.is_citation('Tseng et al. 2024c'))

    def test_plain_year(self):
        self.assertTrue(cp.is_citation('Frantar et al. 2022'))

    def test_an_english_term_is_not_a_citation(self):
        self.assertFalse(cp.is_citation('uniform quantization'))

    def test_a_term_carrying_a_digit_is_not_a_citation(self):
        self.assertFalse(cp.is_citation('INT4 quantization'))


class LeadingContext(unittest.TestCase):

    def test_particle_word_is_dropped(self):
        self.assertEqual(cp._trim_leading_context('절에서는 어블레이션'),
                         '어블레이션')

    def test_verb_ending_is_dropped(self):
        self.assertEqual(cp._trim_leading_context('모델에서 수행한 어블레이션'),
                         '어블레이션')

    def test_a_compound_term_is_kept_whole(self):
        self.assertEqual(cp._trim_leading_context('블록 대각 행렬'),
                         '블록 대각 행렬')

    def test_a_single_word_is_never_emptied(self):
        self.assertEqual(cp._trim_leading_context('행렬의'), '행렬의')


class SameTerm(unittest.TestCase):

    def test_one_term_with_different_modifiers(self):
        self.assertTrue(cp._same_term(['계산 오버헤드', '추론 오버헤드']))

    def test_one_term_with_junk_the_tail_list_cannot_reach(self):
        self.assertTrue(cp._same_term(['가장 높은 양자화된', '그런 다음 양자화된']))

    def test_genuinely_different_terms(self):
        self.assertFalse(cp._same_term(['정확도', '속도']))


class Collisions(unittest.TestCase):

    def test_a_citation_is_not_a_gloss(self):
        self.assertEqual(cp.check_glosses('이 양자화(Tseng et al. 2024c)는'), [])

    def test_context_words_do_not_make_three_renderings(self):
        text = ('4.1절에서는 어블레이션(ablation)을 했고, '
                '모델에서 수행한 어블레이션(ablation)도 있다.')
        self.assertEqual(cp.check_glosses(text), [])

    def test_a_real_clash_is_still_reported(self):
        # Each gloss starts its line, so the capture window has no preceding
        # word to take and both terms are exactly `양자화`.
        text = '양자화(quantization)\n양자화(uniform quantization)\n'
        problems = cp.check_glosses(text)
        self.assertTrue(any('양자화' in p for p in problems), problems)

    def test_an_acronym_beside_its_expansion_is_not_a_clash(self):
        text = ('학습 후 양자화(post-training quantization)와 '
                '학습 후 양자화(PTQ)를 쓴다.')
        self.assertEqual(cp.check_glosses(text), [])


if __name__ == '__main__':
    unittest.main()
