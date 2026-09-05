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


class TheGateStaysQuietWhenItCannotJudge(unittest.TestCase):
    r"""K68: a Latin target cannot be told from a Latin source this way, and
    saying nothing is the honest answer. Reporting every caption of a French
    book as untranslated would be the table probe's old mistake -- a check
    that fires on correct work teaches its reader to skip it."""

    def test_a_latin_target_is_not_judged(self):
        for lang in ('fr', 'de', 'es', 'en'):
            self.assertEqual(mb.untranslated_captions(ENGLISH, lang), [], lang)

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
