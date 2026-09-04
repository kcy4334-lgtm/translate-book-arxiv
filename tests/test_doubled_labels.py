# -*- coding: utf-8 -*-
r"""Tests for the doubled reference label.

CafeQ shipped "4.1절 절과 4.2절 절에서는". The translator wrote its own '절'
after the placeholder, never having seen that the reference substituted in
front of it would already end in one -- the same blind spot the particle fix
exists for. A Korean reader stops at every one.

The trap is that '절' also starts real words. "4.1절 절차를" is correct
Korean and must survive untouched, so these tests run in both directions.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

WORDS = {'section': '절'}
SUFFIX = {'section': '{number}{label}'}
PREFIX = {'figure': '{label} {number}'}
KO = {'particle_agreement': True}


class DoubledLabels(unittest.TestCase):

    def collapse(self, text, words=None, formats=None, cfg=KO):
        return mb.drop_doubled_labels(text, words or WORDS,
                                      formats or SUFFIX, cfg)

    def test_the_shipped_sentence(self):
        got, n = self.collapse('4.1절 절과 4.2절 절에서는 단일 행렬을')
        self.assertEqual(got, '4.1절과 4.2절에서는 단일 행렬을')
        self.assertEqual(n, 2)

    def test_a_real_word_starting_with_the_label_survives(self):
        text = '4.1절 절차를 따른다'
        self.assertEqual(self.collapse(text)[0], text)

    def test_an_undoubled_reference_is_untouched(self):
        text = '3절에서 설명한다'
        self.assertEqual(self.collapse(text)[0], text)

    def test_doubling_without_a_particle(self):
        got, n = self.collapse('자세한 내용은 2절 절 참고')
        self.assertEqual(got, '자세한 내용은 2절 참고')
        self.assertEqual(n, 1)

    def test_the_longest_particle_wins(self):
        # '에' would match first and leave '서는' stranded behind it.
        self.assertEqual(self.collapse('5.2절 절에서는')[0], '5.2절에서는')

    def test_a_prefix_format_is_left_alone(self):
        # "그림 1 그림" cannot arise from a prefix format, and collapsing on
        # one would eat a caption word that belongs to the sentence.
        text = '그림 1 그림자 효과'
        got, n = mb.drop_doubled_labels(text, {'figure': '그림'}, PREFIX, KO)
        self.assertEqual(got, text)
        self.assertEqual(n, 0)

    def test_a_prefix_label_doubles_in_front_of_the_number(self):
        r"""The other prefix shape, which the note above said could not exist.

        The source writes `Figure (Figure_teaser)`. `resolve_references`
        replaces the parenthesised key alone, so the label word the translator
        put in front of it survives and meets the one the resolver supplies.
        VLA-Adapter shipped `그림 그림 1` and `표 표 2` twenty times.

        The number is what separates this from the case above: there the
        second `그림` opens an ordinary word, here it heads a reference.
        """
        got, n = mb.drop_doubled_labels('그림 그림 1 에서 보듯',
                                        {'figure': '그림'}, PREFIX, KO)
        self.assertEqual(got, '그림 1 에서 보듯')
        self.assertEqual(n, 1)

    def test_the_same_for_a_table(self):
        got, n = mb.drop_doubled_labels('표 표 2에 제시했다',
                                        {'table': '표'},
                                        {'table': '{label} {number}'}, KO)
        self.assertEqual(got, '표 2에 제시했다')
        self.assertEqual(n, 1)

    def test_a_word_starting_with_the_label_is_still_safe(self):
        """`표현` must survive: the guard is the digit, not the word."""
        text = '표 표현을 바꾼다'
        got, n = mb.drop_doubled_labels(text, {'table': '표'},
                                        {'table': '{label} {number}'}, KO)
        self.assertEqual(got, text)
        self.assertEqual(n, 0)

    def test_an_appendix_letter_counts_as_a_number(self):
        r"""Where the first attempt at the rule above stopped.

        Anchoring on `\d` alone caught every reference in the body and missed
        every one in the appendix, because those print `A1`, `C2`, `D1`. The
        check written in the same hour reported zero doubled labels while
        sixteen `그림 그림 A1` sat in the finished book -- the number the
        rule was reading was simply never there.
        """
        for text, want in (('그림 그림 A1은', '그림 A1은'),
                           ('그림 그림 D2에서', '그림 D2에서'),
                           ('그림 그림A3', '그림A3')):
            got, n = mb.drop_doubled_labels(text, {'figure': '그림'},
                                            PREFIX, KO)
            self.assertEqual(got, want)
            self.assertEqual(n, 1)

    def test_a_table_appendix_letter_too(self):
        got, n = mb.drop_doubled_labels('표 표 C1에 정리했다', {'table': '표'},
                                        {'table': '{label} {number}'}, KO)
        self.assertEqual(got, '표 C1에 정리했다')
        self.assertEqual(n, 1)

    def test_a_bare_letter_with_no_number_is_not_a_reference(self):
        """The letter alone is not enough -- `그림 그림 A` has no float to
        point at, and collapsing it would eat a word the sentence needs."""
        text = '그림 그림 A에서'
        got, n = mb.drop_doubled_labels(text, {'figure': '그림'}, PREFIX, KO)
        self.assertEqual(got, text)
        self.assertEqual(n, 0)

    def test_a_korean_word_after_the_label_still_survives(self):
        """The letter is optional, so the digit still has to be reachable.
        `그림자` must not be read as label + `자`."""
        text = '그림 그림자 효과 3개'
        got, n = mb.drop_doubled_labels(text, {'figure': '그림'}, PREFIX, KO)
        self.assertEqual(got, text)
        self.assertEqual(n, 0)

    def test_without_particle_agreement_only_word_boundaries_count(self):
        got, n = mb.drop_doubled_labels('第4.1节 节。', {'section': '节'},
                                        {'section': '第{number}{label}'},
                                        {'particle_agreement': False})
        self.assertEqual(got, '第4.1节。')
        self.assertEqual(n, 1)

    def test_a_chinese_word_starting_with_the_label_survives(self):
        text = '第4.1节 节点数'
        got, n = mb.drop_doubled_labels(text, {'section': '节'},
                                        {'section': '第{number}{label}'},
                                        {'particle_agreement': False})
        self.assertEqual(got, text)
        self.assertEqual(n, 0)

    def test_resolve_references_reports_the_count(self):
        self.assertIn('doubled', mb.resolve_references('text', '.', {})[1])


sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'tests'))

import consistency_probe as cp                       # noqa: E402


class TheCheckThatFindsThem(unittest.TestCase):
    """The probe side: it has to see a real doubling and only that."""

    def found(self, sentence):
        return len(cp.check_doubled_labels('<p>%s</p>' % sentence, 'ko'))

    def test_a_real_doubling_is_reported(self):
        self.assertEqual(self.found('4.1절 절을 따라'), 1)

    def test_two_bare_labels_are_reported(self):
        self.assertEqual(self.found('식 식 (5)를 보라'), 1)

    def test_a_label_that_ends_a_longer_word_is_not_one(self):
        # 식 also ends 방식, so an ordinary sentence read as 식 doubled by
        # 알고리즘 and SINQ carried the false alarm through every build.
        self.assertEqual(self.found('Sinkhorn–Knopp 방식 알고리즘을 더한'), 0)

    def test_a_label_that_starts_a_longer_word_is_not_one(self):
        self.assertEqual(self.found('표 표현을 바꾼다'), 0)


if __name__ == '__main__':
    unittest.main()
