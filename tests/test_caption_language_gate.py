# -*- coding: utf-8 -*-
r"""The build refuses a book whose tables are still in the source language.

Step 4.6 of SKILL.md translates the words inside table floats. A float is
protected behind a `⟦T####⟧` placeholder so the math guard can guarantee its
backslashes survive, which also means no translator ever sees its
`\caption{}`.

That step is prose. It was skipped for three editions of one paper in a
single session -- twice after being raised -- and nothing noticed, because
the step's own text is exactly right about what happens: the book comes out
with its tables in the source language and EVERY existing check passes. The
tables are present, the values are correct, the counts agree. A green run
confirms the wrong conclusion.

Steps enforced by code are not skipped: the build stops. Steps written as
prose are skipped eventually. So this asks the artefact rather than trusting
that the step ran.
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

ENGLISH = r'''Some prose.

\begin{table}
\caption{Frame classification accuracy and WER showing that the distilled
single model performs about as well as the averaged predictions.}
\begin{tabular}{|c|c|}
System & WER \\
Baseline & 10.9\% \\
\end{tabular}
\end{table}

More prose.
'''

KOREAN = ENGLISH.replace(
    'Frame classification accuracy and WER showing that the distilled\n'
    'single model performs about as well as the averaged predictions.',
    '프레임 분류 정확도와 WER로, 증류된 단일 모델이 평균 예측과 '
    '거의 동등한 성능을 낸다는 것을 보여준다.')


class TheGateFires(unittest.TestCase):

    def test_an_english_caption_is_reported_for_a_korean_book(self):
        found = mb.untranslated_captions(ENGLISH, 'ko')
        self.assertEqual(len(found), 1)
        self.assertIn('Frame classification', found[0])

    def test_a_translated_caption_is_not_reported(self):
        self.assertEqual(mb.untranslated_captions(KOREAN, 'ko'), [])

    def test_it_works_for_japanese_and_chinese_too(self):
        for lang, caption in (
                ('ja', 'フレーム分類精度とWERであり、蒸留された単一モデルの性能を示す。'),
                ('zh', '帧分类准确率与WER，表明蒸馏后的单一模型性能相当。')):
            text = ENGLISH.replace(
                'Frame classification accuracy and WER showing that the '
                'distilled\nsingle model performs about as well as the '
                'averaged predictions.', caption)
            self.assertEqual(mb.untranslated_captions(text, lang), [], lang)
            self.assertEqual(len(mb.untranslated_captions(ENGLISH, lang)), 1,
                             lang)

    def test_the_lang_attr_form_is_accepted(self):
        """`lang_cfg` carries `zh-CN`, not `zh`."""
        self.assertEqual(len(mb.untranslated_captions(ENGLISH, 'zh-CN')), 1)


FRENCH = ENGLISH.replace(
    'Frame classification accuracy and WER showing that the distilled\n'
    'single model performs about as well as the averaged predictions.',
    'Précision de classification des trames et WER montrant que le '
    'modèle unique distillé égale les prédictions '
    'moyennées.')


class TheSourceIsWhatCoversTheLatinLanguages(unittest.TestCase):
    r"""Script alone leaves fr, de and es unguarded, which is where the whole
    defect would have gone unseen. `flat.tex` is the flattened LaTeX the book
    was built from and the one file the table agents never edit, so a caption
    still word for word identical to it was never translated, whatever
    alphabet the target happens to use."""

    def setUp(self):
        import shutil
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write_source(self, text):
        self.write_chunk('flat.tex', text)

    def write_chunk(self, name, text):
        with io.open(os.path.join(self.dir, name), 'w',
                     encoding='utf-8') as handle:
            handle.write(text)

    def test_an_untouched_caption_is_caught_in_french(self):
        self.write_source(ENGLISH)
        found = mb.untranslated_captions(ENGLISH, 'fr', self.dir)
        self.assertEqual(len(found), 1)
        self.assertIn('Frame classification', found[0])

    def test_a_translated_caption_is_not(self):
        self.write_source(ENGLISH)
        for lang in ('fr', 'de', 'es'):
            self.assertEqual(
                mb.untranslated_captions(FRENCH, lang, self.dir), [], lang)

    def test_line_breaks_moved_by_the_translator_do_not_hide_it(self):
        """The sidecar's caption is reflowed; the words are what matter."""
        self.write_source(ENGLISH.replace('the distilled\nsingle model',
                                          'the distilled single model'))
        self.assertEqual(len(mb.untranslated_captions(ENGLISH, 'fr',
                                                      self.dir)), 1)

    def test_it_also_catches_a_cjk_book_whose_caption_was_reverted(self):
        """Two independent tests, so a revert is caught twice over."""
        self.write_source(ENGLISH)
        self.assertEqual(len(mb.untranslated_captions(ENGLISH, 'ko',
                                                      self.dir)), 1)

    def test_a_passthrough_run_is_not_judged(self):
        r"""An English paper rendered into English copies its chunks through.
        Its captions are identical to `flat.tex` because that is correct, not
        because a step was skipped, and nothing can tell those apart."""
        self.write_source(ENGLISH)
        self.write_chunk('chunk0001.md', 'Some prose.\n')
        self.write_chunk('output_chunk0001.md', 'Some prose.\n')
        self.assertTrue(mb.translation_is_passthrough(self.dir))
        self.assertEqual(mb.untranslated_captions(ENGLISH, 'en', self.dir), [])

    def test_english_is_judged_when_something_was_actually_translated(self):
        r"""Asking `lang == 'en'` would assume every source paper is English,
        and silently drop the check for a French paper rendered into
        English. The question is whether translation happened, not what the
        target is called."""
        self.write_source(ENGLISH)
        self.write_chunk('chunk0001.md', 'Une phrase en français.\n')
        self.write_chunk('output_chunk0001.md', 'A sentence in English.\n')
        self.assertFalse(mb.translation_is_passthrough(self.dir))
        self.assertEqual(
            len(mb.untranslated_captions(ENGLISH, 'en', self.dir)), 1)

    def test_a_temp_dir_with_no_chunks_is_not_called_a_passthrough(self):
        """Absence of evidence is not evidence: judge the captions."""
        self.write_source(ENGLISH)
        self.assertFalse(mb.translation_is_passthrough(self.dir))
        self.assertFalse(mb.translation_is_passthrough(None))

    def test_a_short_source_caption_is_not_used_as_evidence(self):
        r"""`\caption{Results}` matching `\caption{Results}` says nothing."""
        short = ENGLISH.replace(
            'Frame classification accuracy and WER showing that the '
            'distilled\nsingle model performs about as well as the averaged '
            'predictions.', 'Results')
        self.write_source(short)
        self.assertEqual(mb.untranslated_captions(short, 'fr', self.dir), [])


HALF_FRENCH = ENGLISH.replace(
    'Frame classification accuracy and WER showing that the distilled\n'
    'single model performs about as well as the averaged predictions.',
    'Précision de classification par trame et WER montrant que the '
    'distilled single model performs about as well as the averaged '
    'predictions.')

HALF_KOREAN = ENGLISH.replace(
    'Frame classification accuracy and WER showing that the distilled\n'
    'single model performs about as well as the averaged predictions.',
    '프레임 분류 정확도와 WER, showing that the distilled single '
    'model performs about as well as the averaged predictions.')


class AHalfTranslatedCaptionIsCaught(unittest.TestCase):
    r"""The case both other tests wave through.

    One character of the target script satisfies the script test, so a caption
    that is Korean for six words and English for the next twenty passes it.
    And a half-translated caption is not identical to `flat.tex`, so it passes
    the identity test too. Measured over the seven editions of one paper, a
    correctly translated caption shares at most ONE word with its source and a
    half-translated one shares at least FOUR in a row, because a translator
    borrows scattered words (acronyms, dataset names, cognates) while
    untranslated text arrives as a contiguous run.
    """

    def setUp(self):
        import shutil
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        with io.open(os.path.join(self.dir, 'flat.tex'), 'w',
                     encoding='utf-8') as handle:
            handle.write(ENGLISH)

    def test_half_french(self):
        self.assertEqual(
            len(mb.untranslated_captions(HALF_FRENCH, 'fr', self.dir)), 1)

    def test_half_korean_which_the_script_test_accepts(self):
        self.assertEqual(mb.untranslated_captions(HALF_KOREAN, 'ko'), [],
                         'precondition: the script test alone accepts it')
        self.assertEqual(
            len(mb.untranslated_captions(HALF_KOREAN, 'ko', self.dir)), 1)

    def test_a_fully_translated_caption_is_still_quiet(self):
        for lang, text in (('fr', FRENCH), ('ko', KOREAN)):
            self.assertEqual(
                mb.untranslated_captions(text, lang, self.dir), [], lang)


class TheRunItselfBehaves(unittest.TestCase):

    def run_of(self, caption, source=None):
        return mb.longest_source_run(caption, {source or
                                               'Frame classification accuracy '
                                               'and WER showing that the '
                                               'distilled single model'})

    def test_scattered_shared_words_do_not_accumulate(self):
        r"""`classification` and `WER` in a French caption are one word each,
        not a run. This is why cognates do not trip the check."""
        self.assertEqual(
            self.run_of('Précision de classification par trame et WER'), 1)

    def test_a_contiguous_borrowing_counts(self):
        """showing / that / the / distilled / single / model."""
        self.assertEqual(
            self.run_of('Précision showing that the distilled single model'),
            6)

    def test_a_three_word_glossary_term_stays_under_the_threshold(self):
        r"""A term deliberately left in the source language runs one to three
        words. Four is the shortest run this reports."""
        self.assertLess(
            mb.longest_source_run('un mixture of experts adapté',
                                  {'we used a mixture of experts here'}),
            mb._UNTRANSLATED_RUN)

    def test_digits_do_not_pad_a_run(self):
        """`top 1` shares one word, not two: the digit is dropped."""
        self.assertEqual(mb.longest_source_run('précision top 1 sur JFT',
                                               {'top 1 accuracy on JFT'}), 1)

    def test_no_source_and_no_words_are_answered_with_zero(self):
        self.assertEqual(mb.longest_source_run('anything', set()), 0)
        self.assertEqual(mb.longest_source_run('', {'some words'}), 0)
        self.assertEqual(mb.longest_source_run('123 456', {'some words'}), 0)


class WhatTheCorpusCaught(unittest.TestCase):
    r"""Four ways a correctly translated caption looked untranslated.

    Every one of these is a real caption from a book this pipeline shipped,
    and every one of them was scored 4 or more by the first version of the
    check -- which had been calibrated on a single paper whose captions
    happen to contain no citation, no maths and no comment. Measuring
    against the other six papers is what found them.
    """

    def test_a_citation_key_is_not_shared_prose(self):
        r"""VLA-Adapter: `OpenVLA \citep{OpenVLA-2024} 및 OpenVLA-OFT
        \citep{OpenVLA-OFT-2025}` scored 9 because the key and the command
        name were counted as words. They are identical by design."""
        source = (r'Comparison with OpenVLA \citep{OpenVLA-2024} and '
                  r'OpenVLA-OFT \citep{OpenVLA-OFT-2025}.')
        korean = (r'OpenVLA \citep{OpenVLA-2024} 및 OpenVLA-OFT '
                  r'\citep{OpenVLA-OFT-2025}와의 비교.')
        self.assertLess(mb.longest_source_run(korean, {source}),
                        mb._UNTRANSLATED_RUN)

    def test_a_commented_out_original_is_not_shared_prose(self):
        r"""SINQ keeps the paper's own English wording as a `%` comment under
        the Korean. The reader never sees it; it scored 28."""
        source = ('In bold is the best result for a given setting at equal '
                  'bits other than our own.')
        korean = ('가장 좋은 결과는 굵은 글씨로 표시하였다.\n'
                  '% In bold is the best result for a given setting at '
                  'equal bits other than our own.')
        self.assertLess(mb.longest_source_run(korean, {source}),
                        mb._UNTRANSLATED_RUN)

    def test_maths_is_not_shared_prose(self):
        source = r'Comparison of the $i$th-layer $\mathcal{C}_t$ features.'
        korean = r'$i$번째 층의 $\mathcal{C}_t$ 특징 비교.'
        self.assertLess(mb.longest_source_run(korean, {source}),
                        mb._UNTRANSLATED_RUN)

    def test_a_row_of_model_names_is_not_shared_prose(self):
        r"""AlphaQ's caption opens by naming four models, and SINQ's names
        two. Those runs are what a threshold below four would fire on."""
        source = (r'Results for \textbf{DeepSeekV2-Lite, Qwen1.5-MoE, '
                  r'Mixtral-8x7B, Qwen3-235B} on WikiText2.')
        korean = (r'WikiText2에서의 \textbf{DeepSeekV2-Lite, Qwen1.5-MoE, '
                  r'Mixtral-8x7B, Qwen3-235B} 결과이다.')
        self.assertLess(mb.longest_source_run(korean, {source}),
                        mb._UNTRANSLATED_RUN)

    def test_but_prose_among_the_names_still_counts(self):
        """The names are excused; the sentence around them is not."""
        source = ('Results for DeepSeekV2-Lite and Qwen3-235B measured on '
                  'the WikiText2 perplexity benchmark.')
        half = ('DeepSeekV2-Lite 및 Qwen3-235B에 대한 결과로, measured on '
                'the WikiText2 perplexity benchmark.')
        self.assertGreaterEqual(mb.longest_source_run(half, {source}),
                                mb._UNTRANSLATED_RUN)


class TheGateStaysQuietWhenItCannotJudge(unittest.TestCase):
    r"""K68: with no source to compare against, a Latin target cannot be told
    from a Latin source and saying nothing is the honest answer. Reporting
    every caption of a French book as untranslated would be the table probe's
    old mistake -- a check that fires on correct work teaches its reader to
    skip it."""

    def test_a_latin_target_is_not_judged_without_the_source(self):
        for lang in ('fr', 'de', 'es', 'en'):
            self.assertEqual(mb.untranslated_captions(ENGLISH, lang), [], lang)

    def test_a_missing_flat_tex_is_not_an_error(self):
        """An old temp dir, or the calibre backend, has no `flat.tex`."""
        self.assertEqual(mb.source_captions(None), set())
        self.assertEqual(mb.source_captions(os.path.dirname(__file__)), set())
        self.assertEqual(mb.untranslated_captions(ENGLISH, 'fr', '/nope'), [])

    def test_an_unknown_language_is_not_judged(self):
        self.assertEqual(mb.untranslated_captions(ENGLISH, ''), [])
        self.assertEqual(mb.untranslated_captions(ENGLISH, None), [])

    def test_a_document_with_no_tables_reports_nothing(self):
        self.assertEqual(mb.untranslated_captions('just prose\n', 'ko'), [])

    def test_a_label_length_caption_is_not_prose(self):
        """`\\caption{Results}` says nothing about whether anyone translated
        it, and flagging it would fire on every table that has a short one."""
        short = ENGLISH.replace(
            'Frame classification accuracy and WER showing that the '
            'distilled\nsingle model performs about as well as the averaged '
            'predictions.', 'Results')
        self.assertEqual(mb.untranslated_captions(short, 'ko'), [])


class TheStepIsNamedInTheRefusal(unittest.TestCase):
    """A refusal that does not say what to do next is a wall, not a gate."""

    def source(self):
        import io
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / 'scripts'
                / 'merge_and_build.py')
        return io.open(path, encoding='utf-8').read()

    def test_the_build_refuses_and_names_step_4_6(self):
        src = self.source()
        at = src.index('def convert_md_to_html')
        window = src[at - 3000:at + 3000]
        self.assertIn('still in the source language', window)
        self.assertIn('4.6', window)
        self.assertIn('format_probe.py', window)
        self.assertIn('raise SystemExit(1)', window)


if __name__ == '__main__':
    unittest.main()
