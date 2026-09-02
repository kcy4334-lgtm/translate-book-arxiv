# -*- coding: utf-8 -*-
r"""Tests for first-use English glosses: the prompt's floor, the merge's ceiling.

Three books lost about half their `한글(English)` annotations between one
version and the next. Nobody removed them. The term tables grew from ~74 to
~128 entries, the sub-agents stopped annotating terms the table had already
decided for them, and every check stayed green — `check_glosses` only ever
complained about glossing something too OFTEN. A reader noticed; no counter
did.

The fix has two halves that must be tested together, because each is wrong
without the other: the prompt tells every sub-agent to gloss the first use it
can see (it sees one chunk), and the merge drops the repeats that produces.
"""
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import glossary
import consistency_probe as cp


class DedupeTests(unittest.TestCase):
    def test_the_first_gloss_stays_and_the_second_goes(self):
        text = ('가중치에 존재하는 이상치(outlier)로 인해 오차가 커진다. '
                '이 이상치(outlier)를 따로 다룬다.')
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 1)
        self.assertEqual(out.count('(outlier)'), 1)
        self.assertLess(out.index('(outlier)'), out.index('이 이상치'))

    def test_a_third_copy_goes_too(self):
        text = '재구성 오차(reconstruction error) ' * 3
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 2)
        self.assertEqual(out.count('(reconstruction error)'), 1)

    def test_dedupe_is_case_insensitive(self):
        text = '이상치(outlier)와 이상치(Outlier)'
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 1)
        self.assertIn('(outlier)', out)

    def test_a_unit_is_never_removed(self):
        text = '메모리 사용량(GB)과 메모리 사용량(GB)을 보고한다'
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 0)
        self.assertEqual(out.count('(GB)'), 2)

    def test_an_abbreviation_the_text_keeps_using_is_never_removed(self):
        text = '사후 학습 양자화(PTQ)는 ... 균일 양자화(PTQ)도 마찬가지다'
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 0)

    def test_a_citation_is_never_removed(self):
        text = ('행렬 이론(Couillet and Liao 2022)과 '
                '행렬 이론(Couillet and Liao 2022)')
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 0)

    def test_a_parenthesis_not_after_hangul_is_left_alone(self):
        text = 'SINQ (uniform quantization) and RTN (uniform quantization)'
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual((out, removed), (text, 0))

    def test_text_with_no_glosses_is_returned_unchanged(self):
        text = '양자화 오차를 최소화한다.\n\n두 번째 문단.'
        self.assertEqual(glossary.dedupe_glosses(text), (text, 0))

    def test_placeholders_are_untouched(self):
        text = ('이상치(outlier) ⟦M0042⟧ 그리고 이상치(outlier) ⟦M0043⟧')
        out, _removed = glossary.dedupe_glosses(text)
        self.assertIn('⟦M0042⟧', out)
        self.assertIn('⟦M0043⟧', out)

    def test_a_space_before_the_parenthesis_is_still_a_gloss(self):
        """Translators write both forms; a detector that saw one counted 18
        of a book's 40 glosses, and deduplicated only those 18."""
        text = '이상치 (outlier)를 다루고, 다시 이상치 (outlier)를 본다'
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 1)
        self.assertEqual(out.count('(outlier)'), 1)
        self.assertIn('다시 이상치를 본다', out)

    def test_the_two_spacings_deduplicate_against_each_other(self):
        text = '이상치(outlier)를 쓰고 이상치 (outlier)도 쓴다'
        out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 1)
        self.assertEqual(out.count('(outlier)'), 1)

    def test_a_long_parenthetical_is_not_treated_as_a_gloss(self):
        # Six words: a sentence in brackets, not a term's English.
        inside = 'this is clearly a running sentence'
        text = '설명(%s)과 설명(%s)' % (inside, inside)
        _out, removed = glossary.dedupe_glosses(text)
        self.assertEqual(removed, 0)


class CoverageTests(unittest.TestCase):
    """The floor `check_glosses` never had."""

    def glossary_at(self, tmp, terms):
        path = os.path.join(tmp, 'glossary.json')
        with io.open(path, 'w', encoding='utf-8', newline='') as fh:
            json.dump({'version': 2, 'terms': terms,
                       'high_frequency_top_n': 20,
                       'applied_meta_hashes': {}}, fh, ensure_ascii=False)
        return path

    def term(self, source, target):
        return {'id': source, 'source': source, 'target': target,
                'category': 'concept', 'aliases': [], 'gender': 'unknown',
                'confidence': 'high', 'frequency': 0, 'evidence_refs': [],
                'notes': ''}

    def test_counts_glossed_against_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.glossary_at(tmp, [self.term('outlier', '이상치'),
                                   self.term('scale factor', '스케일 인자')])
            text = '이상치(outlier)를 다루고 스케일 인자를 조정한다'
            count, glossed, eligible = cp.check_gloss_coverage(text, tmp)
            self.assertEqual(sorted(eligible), ['outlier', 'scale factor'])
            self.assertEqual(glossed, ['outlier'])
            self.assertEqual(count, 1)

    def test_the_count_sees_glosses_the_glossary_does_not_list(self):
        """The headline number is about the book, not about the glossary."""
        with tempfile.TemporaryDirectory() as tmp:
            self.glossary_at(tmp, [self.term('outlier', '이상치')])
            text = '이상치(outlier)와 유사역행렬(pseudoinverse)을 쓴다'
            count, glossed, _eligible = cp.check_gloss_coverage(text, tmp)
            self.assertEqual(count, 2, 'a gloss off the glossary still counts')
            self.assertEqual(glossed, ['outlier'])

    def test_a_term_kept_in_english_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.glossary_at(tmp, [self.term('Hadamard', 'Hadamard')])
            _c, glossed, eligible = cp.check_gloss_coverage('Hadamard 회전', tmp)
            self.assertEqual((glossed, eligible), ([], []))

    def test_a_term_the_book_never_uses_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.glossary_at(tmp, [self.term('kurtosis', '첨도')])
            _c, glossed, eligible = cp.check_gloss_coverage('양자화 오차', tmp)
            self.assertEqual((glossed, eligible), ([], []))

    def test_no_glossary_means_the_check_refuses_rather_than_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(cp.check_gloss_coverage('아무 글', tmp))

    def test_whitespace_between_term_and_parenthesis_still_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.glossary_at(tmp, [self.term('outlier', '이상치')])
            _c, glossed, _e = cp.check_gloss_coverage('이상치 (outlier)', tmp)
            self.assertEqual(glossed, ['outlier'])

    def test_the_two_halves_agree(self):
        """Dedupe must not delete the one gloss coverage is counting."""
        with tempfile.TemporaryDirectory() as tmp:
            self.glossary_at(tmp, [self.term('outlier', '이상치')])
            text = '이상치(outlier)다. 다시 이상치(outlier)다.'
            deduped, removed = glossary.dedupe_glosses(text)
            self.assertEqual(removed, 1)
            count, glossed, eligible = cp.check_gloss_coverage(deduped, tmp)
            self.assertEqual((count, glossed, eligible),
                             (1, ['outlier'], ['outlier']))

    def test_the_probe_and_the_merge_share_one_detector(self):
        """Two copies of "gloss or unit?" would drift apart."""
        self.assertIs(cp._looks_like_gloss, glossary._is_first_use_gloss)
        self.assertIs(cp._GLOSS_PAREN_RE, glossary._GLOSS_RE)


if __name__ == '__main__':
    unittest.main()
