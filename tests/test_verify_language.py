# -*- coding: utf-8 -*-
r"""The verifier assumed the target language was Korean.

`--lang` defaulted to `ko` and nothing read `output_lang`, which had been
sitting in the temp directory the command is already pointed at since
conversion. So every chunk of every non-Korean book was checked against
Hangul. Measured on a Japanese run: five of nine correct chunks reported
"only 0% of the letters are ko" and would have been sent back for
re-translation, forever, on output that was entirely right.

The second half was narrower and worse. The Japanese range was
`0x3040-0x30FF`, which is kana only. Japanese academic prose is kanji-dense,
so even with `--lang ja` passed by hand the ratio counted almost none of the
text as Japanese. The check that exists to notice an untranslated chunk was
nearly blind on the language it was checking.

Both are the same shape: a tool written for the first language it saw, in a
project that claims seven.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import verify_chunk as vc


class TheLanguageComesFromTheRun(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write_config(self, body):
        with io.open(os.path.join(self.dir, 'config.txt'), 'w',
                     encoding='utf-8') as fh:
            fh.write(body)

    def test_output_lang_is_read(self):
        self.write_config('input_lang=auto\noutput_lang=ja\nmath_guard=on\n')
        self.assertEqual(vc.config_lang(self.dir), 'ja')

    def test_a_config_without_it_says_nothing(self):
        self.write_config('input_lang=auto\nmath_guard=on\n')
        self.assertIsNone(vc.config_lang(self.dir))

    def test_no_config_at_all_says_nothing(self):
        self.assertIsNone(vc.config_lang(self.dir))

    def test_a_missing_directory_says_nothing(self):
        self.assertIsNone(vc.config_lang(os.path.join(self.dir, 'nope')))
        self.assertIsNone(vc.config_lang(None))

    def test_an_empty_value_says_nothing(self):
        """`output_lang=` with nothing after it must not become the empty
        language, which matches no script and silently disables the check."""
        self.write_config('output_lang=\n')
        self.assertIsNone(vc.config_lang(self.dir))


class TheJapaneseRangeCoversKanji(unittest.TestCase):
    r"""Kana alone was the range, and it is the smaller half of the writing
    system. A sentence of ordinary academic Japanese counted as almost no
    Japanese at all."""

    KANJI_HEAVY = '本論文では知識蒸留の手法を提案する'
    KANA = 'これは、ソフトターゲットを用いる。'

    def test_kanji_counts_as_japanese(self):
        self.assertEqual(vc._script_ratio(self.KANJI_HEAVY, 'ja'), 1.0)

    def test_kana_still_counts(self):
        self.assertEqual(vc._script_ratio(self.KANA, 'ja'), 1.0)

    def test_a_kanji_sentence_used_to_read_as_untranslated(self):
        """With the old kana-only range this text scored zero against a
        Latin word, which is what failed five correct chunks."""
        mixed = self.KANJI_HEAVY + ' distillation'
        ratio = vc._script_ratio(mixed, 'ja')
        self.assertGreater(ratio, 0.5, ratio)

    def test_korean_is_unaffected(self):
        self.assertEqual(vc._script_ratio('한국어 문장', 'ko'), 1.0)

    def test_latin_text_under_a_cjk_target_scores_zero_not_nothing(self):
        """0.0 is the answer that makes the untranslated check fire. `None`
        means "cannot be measured", which is a different claim and would
        silently pass an untranslated chunk."""
        self.assertEqual(vc._script_ratio('plain latin', 'ko'), 0.0)
        self.assertEqual(vc._script_ratio('plain latin', 'ja'), 0.0)

    def test_chinese_is_unaffected(self):
        self.assertEqual(vc._script_ratio('本文提出知识蒸馏', 'zh'), 1.0)

    def test_a_latin_target_still_refuses_to_answer(self):
        """K68: a Latin target cannot be checked this way, and the ratio
        says so rather than inventing a number."""
        self.assertIsNone(vc._script_ratio('anything at all', 'fr'))
        self.assertIsNone(vc._script_ratio('anything at all', 'en'))


class EveryRangeIsATupleOfRanges(unittest.TestCase):
    """The shape changed so Japanese could have two. A language left as a
    bare pair would be read as one range of two languages."""

    def test_each_entry_is_a_sequence_of_pairs(self):
        for lang, ranges in vc._SCRIPT_RANGES.items():
            self.assertIsInstance(ranges, tuple, lang)
            for pair in ranges:
                self.assertIsInstance(pair, tuple, lang)
                self.assertEqual(len(pair), 2, lang)
                lo, hi = pair
                self.assertLess(lo, hi, lang)

    def test_japanese_has_both_kana_and_han(self):
        self.assertEqual(len(vc._SCRIPT_RANGES['ja']), 2)

    def test_the_membership_helper_agrees_with_the_ranges(self):
        self.assertTrue(vc._in_target_script(
            '本', vc._SCRIPT_RANGES['ja']))
        self.assertTrue(vc._in_target_script(
            'あ', vc._SCRIPT_RANGES['ja']))
        self.assertFalse(vc._in_target_script(
            'a', vc._SCRIPT_RANGES['ja']))
        self.assertFalse(vc._in_target_script(
            '가', vc._SCRIPT_RANGES['ja']))


if __name__ == '__main__':
    unittest.main()
