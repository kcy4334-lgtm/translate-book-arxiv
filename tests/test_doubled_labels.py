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


EQ = {'equation': '{label} ({number})'}


class ANumberInBracketsIsStillANumber(unittest.TestCase):
    r"""`式 式 (3)`.

    An equation reference is written `式 (3)`, not `式 3`, and this rule was
    anchored on a bare digit -- so it could never see a doubling in one. The
    Chinese edition printed `那么式 式 (3)` and `针对式 式 (5)` while every
    count reported zero.

    They reach this stage at all because Chinese leaves no space between
    words: the translator's own 式 sits inside 那么式, and the absorbing pass
    deliberately refuses to lift a label out of the middle of a word.
    """

    EQ = {'equation': '{label} ({number})'}

    def collapse(self, text, label='式'):
        return mb.drop_doubled_labels(text, {'equation': label}, self.EQ, {})

    def test_the_two_that_shipped(self):
        for text, want in (
                ('使得 ∑ = 0，那么式 式 (3) 可简化为：',
                 '使得 ∑ = 0，那么式 (3) 可简化为：'),
                ('并使用梯度下降针对式 式 (5) 优化 logits。',
                 '并使用梯度下降针对式 (5) 优化 logits。')):
            got, n = self.collapse(text)
            self.assertEqual(got, want)
            self.assertEqual(n, 1)

    def test_a_full_width_bracket_too(self):
        got, n = self.collapse('见式 式（7）的推导')
        self.assertEqual(got, '见式（7）的推导')
        self.assertEqual(n, 1)

    def test_a_single_reference_is_untouched(self):
        for text in ('那么式 (3) 可简化为', '见式（7）的推导', '式 (5) 没有解'):
            got, n = self.collapse(text)
            self.assertEqual((got, n), (text, 0))

    def test_the_bare_digit_form_still_collapses(self):
        """`그림 그림 1` is what this rule was written for; it must survive."""
        got, n = mb.drop_doubled_labels('그림 그림 1 에서 보듯',
                                        {'figure': '그림'}, PREFIX, KO)
        self.assertEqual(got, '그림 1 에서 보듯')
        self.assertEqual(n, 1)

    def test_an_appendix_letter_still_collapses(self):
        got, n = mb.drop_doubled_labels('표 표 C1에 정리했다', {'table': '표'},
                                        {'table': '{label} {number}'}, KO)
        self.assertEqual(got, '표 C1에 정리했다')
        self.assertEqual(n, 1)


class AnAbbreviationIsTheSameDoubling(unittest.TestCase):
    r"""`l'éq. Équation (3)`.

    The doubling this file was written for is the same word twice, which is
    what a translator produces when it writes the label the resolver is about
    to write. A translator that ABBREVIATES leaves two forms that do not
    match each other, and nothing fired: French, German and Spanish shipped
    nine of these between them while the Korean and Japanese books, whose
    translators wrote `식 (3)` and `式 (3)`, had none.

    An abbreviation is a prefix of its word, so the rule is derived rather
    than listed and a language nobody has run yet is covered.
    """

    def collapse(self, text, label):
        return mb.drop_doubled_labels(text, {'equation': label}, EQ, {})

    def test_the_three_that_shipped(self):
        for text, label, want in (
                ("de sorte que 0 l'éq. Équation (3) se simplifie",
                 'Équation', "de sorte que 0 l'Équation (3) se simplifie"),
                ('vereinfacht sich Gl. Gleichung (3) zu',
                 'Gleichung', 'vereinfacht sich Gleichung (3) zu'),
                ('La Ec. Ecuación (5) no tiene',
                 'Ecuación', 'La Ecuación (5) no tiene')):
            got, n = self.collapse(text, label)
            self.assertEqual(got, want)
            self.assertEqual(n, 1)

    def test_a_lowercase_abbreviation_too(self):
        got, n = self.collapse('con respecto a la ec. Ecuación (5).',
                               'Ecuación')
        self.assertEqual(got, 'con respecto a la Ecuación (5).')
        self.assertEqual(n, 1)

    def test_an_unrelated_abbreviation_is_left_alone(self):
        r"""This is the whole reason the rule tests for a prefix. `cf.` and
        `vs.` in front of a reference are correct writing, and a check that
        ate them would be worse than the defect."""
        for text in ('véase cf. Ecuación (3) para el detalle',
                     'compare vs. Ecuación (3) here',
                     'p. ej. Ecuación (3) muestra'):
            got, n = self.collapse(text, 'Ecuación')
            self.assertEqual(got, text)
            self.assertEqual(n, 0)

    def test_the_word_alone_is_untouched(self):
        for text in ('Ecuación (3) muestra que',
                     'la Ecuación (5) no tiene solución'):
            got, n = self.collapse(text, 'Ecuación')
            self.assertEqual(got, text)
            self.assertEqual(n, 0)

    def test_it_needs_a_number_after_the_label(self):
        """A sentence that merely uses the word is not a reference."""
        got, n = self.collapse('la ec. Ecuación de estado', 'Ecuación')
        self.assertEqual(n, 0)

    def test_it_works_for_tables_and_figures_as_well(self):
        got, n = mb.drop_doubled_labels('voir Tab. Tableau 1 ci-dessus',
                                        {'table': 'Tableau'},
                                        {'table': '{label} {number}'}, {})
        self.assertEqual(got, 'voir Tableau 1 ci-dessus')
        self.assertEqual(n, 1)


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
