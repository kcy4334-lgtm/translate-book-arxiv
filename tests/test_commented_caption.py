# -*- coding: utf-8 -*-
r"""A caption nobody prints is not a caption still in the source language.

DeeR-VLA's first table keeps an older caption commented out above the live
one:

    \begin{table}
    % \fontsize{9pt}{9pt}\selectfont
    % \caption{Computation cost v.s. task successful rate ...
    % }
    \captionsetup{font={footnotesize}}
    \caption{Computation cost v.s. task successful rate ...

`check_table_language` walked every `\caption` in the sidecar and counted
both, so the probe reported seven untranslated captions where the build's own
gate -- which reads the restored markdown -- reported six. The two disagreed
by exactly the dead line.

That matters because SKILL.md step 4.6 ends "re-run the format probe; it must
report zero untranslated captions". With the dead caption counted, the only
way to reach zero is to translate text no reader will ever see, which is not
translating the book.
"""
from __future__ import unicode_literals

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

import algorithm_float as af
import format_probe as fp
import sidecar_edit as se

LIVE_KO = '작업 성공률 대비 연산 비용을 RoboFlamingo++로 측정한 결과이다.'
LIVE_EN = 'Computation cost v.s. task successful rate on the CALVIN benchmark.'

FLOAT = ('\\begin{table}\n'
         '%% \\caption{Computation cost v.s. task successful rate, older wording\n'
         '%% that was replaced and left behind in the source.\n'
         '%% }\n'
         '\\captionsetup{font={footnotesize}}\n'
         '\\caption{%s}\n'
         '\\begin{tabular}{l|lll}\n'
         '\\# LLM layers & 24 & 12 & 6 \\\\\n'
         '\\end{tabular}\n'
         '\\end{table}\n')


class CommentedOut(unittest.TestCase):

    def test_a_percent_earlier_on_the_line_comments_it(self):
        text = 'x\n% \\caption{dead}\n'
        self.assertTrue(fp._commented_out(text, text.index('\\caption')))

    def test_a_live_line_is_not_commented(self):
        text = '% dead\n\\caption{live}\n'
        self.assertFalse(fp._commented_out(text, text.index('\\caption')))

    def test_an_escaped_percent_is_a_printed_sign(self):
        r"""`75\% \caption{...}` on one line is contrived, but the escape rule
        is the same one that decides whether a caption saying `78.9\%` has
        commented out everything after it."""
        text = 'Task success rate 78.9\\% \\caption{live}\n'
        self.assertFalse(fp._commented_out(text, text.index('\\caption')))

    def test_the_first_line_of_the_file_is_handled(self):
        text = '% \\caption{dead}\n'
        self.assertTrue(fp._commented_out(text, text.index('\\caption')))


class TheProbeCountsOnlyLiveCaptions(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='fmtprobe-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_chunk(self, live):
        path = os.path.join(self.dir, 'output_chunk0001.md')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(FLOAT % live)

    def write_sidecar(self, live):
        path = os.path.join(self.dir, 'chunk0001.math.json')
        payload = {'spans': [{'token': 'T0001', 'kind': 'float',
                              'latex': FLOAT % live}]}
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(payload))

    def test_a_translated_float_is_clean_despite_the_dead_caption(self):
        self.write_chunk(LIVE_KO)
        done, missing, examples = fp.check_table_language(self.dir, 'ko')
        self.assertEqual((done, missing, examples), (1, 0, []))

    def test_the_same_in_a_sidecar_where_the_real_one_lived(self):
        self.write_sidecar(LIVE_KO)
        done, missing, _ex = fp.check_table_language(self.dir, 'ko')
        self.assertEqual((done, missing), (1, 0))

    def test_an_untranslated_live_caption_is_still_caught_once(self):
        """The dead line must not go from over-counting to hiding a real one."""
        self.write_chunk(LIVE_EN)
        done, missing, examples = fp.check_table_language(self.dir, 'ko')
        self.assertEqual((done, missing), (0, 1))
        self.assertEqual(len(examples), 1)
        self.assertIn('Computation cost', examples[0])


class TheEditLogRecordsTheLiveCaption(unittest.TestCase):
    r"""The same blindness, in the audit trail rather than in a probe.

    `sidecar_edit.py` logs a prose digest of every guarded write so that a
    caption translated and then overwritten leaves both events on the record.
    `caption_bodies` joined the commented-out caption too, and since it comes
    first in the float, the log line for a correctly translated T0001 read as
    English. Anyone auditing the run would conclude step 4.6 was skipped for
    a table that was in fact finished.
    """

    def test_the_digest_skips_the_dead_caption(self):
        digest = se.prose_digest(FLOAT % LIVE_KO)
        self.assertTrue(digest.startswith(LIVE_KO[:20]), digest)
        self.assertNotIn('older wording', digest)

    def test_a_float_whose_only_caption_is_dead_falls_back_to_the_latex(self):
        """No live caption at all must not log an empty line."""
        dead = ('\\begin{table}\n'
                '%% \\caption{only a dead caption here}\n'
                '\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}\n'
                '\\end{table}\n')
        self.assertTrue(se.prose_digest(dead).startswith('\\begin{table}'))

    def test_an_escaped_percent_in_a_caption_stays_live(self):
        latex = ('\\begin{table}\n'
                 '\\caption{작업 성공률 78.9\\% 를 보고한다.}\n'
                 '\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}\n'
                 '\\end{table}\n')
        self.assertIn('78.9', se.prose_digest(latex))


class TheFloatFidelityCheckReadsTheLiveCaption(unittest.TestCase):
    r"""The same blindness again, and this one aborted the build.

    `check_latex_float_fidelity` fingerprints each raw-LaTeX block and asks
    whether that phrase is on the page. `extract_caption` searched the raw
    text, so it returned the commented-out caption -- and because the `%`
    that kills that caption sits in FRONT of `\caption`, outside the braces,
    the extracted body carried no marker and survived comment-stripping. The
    fingerprint became English prose no reader will ever see, it was of
    course not on the page, and the build refused to finish over a table that
    had rendered correctly.
    """

    def test_the_fingerprint_comes_from_the_live_caption(self):
        phrase = af._fingerprint(FLOAT % LIVE_KO)
        self.assertIsNotNone(phrase)
        self.assertNotIn('older wording', phrase)
        self.assertIn(phrase.split()[0], LIVE_KO)

    def test_a_rendered_float_is_not_reported_missing(self):
        md = '```{=latex}\n' + (FLOAT % LIVE_KO) + '```\n'
        html = '<table><caption>%s</caption></table>' % LIVE_KO
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_a_float_that_really_vanished_is_still_reported(self):
        """Ignoring the dead caption must not blind the check to a real loss."""
        md = '```{=latex}\n' + (FLOAT % LIVE_KO) + '```\n'
        html = '<p>이 페이지에는 표가 없다.</p>'
        missing = af.check_latex_float_fidelity(md, html)
        self.assertEqual(len(missing), 1)
        self.assertNotIn('older wording', missing[0][1])


FLAT = ('\\begin{table}\n'
        '%% \\caption{An older caption that was replaced and left behind.}\n'
        '\\caption{살아 있는 캡션이다.}\n'
        '\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}\n'
        '\\end{table}\n')


class TheSourceCountIgnoresCommentedFloats(unittest.TestCase):
    r"""A float behind `%` is not a table the book owes the reader.

    `float_units` documents its argument as comment-stripped text and
    `source_probe` strips before calling it; this one did not. DeeR-VLA keeps
    three superseded table captions commented out, so the probe reported "14
    in the source, 11 in the book" and failed a book that numbers every table
    the paper actually prints.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='fmtprobe-flat-')
        with io.open(os.path.join(self.dir, 'flat.tex'), 'w',
                     encoding='utf-8') as fh:
            fh.write(FLAT)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_only_the_live_float_is_owed(self):
        body = '표 1 (Table 1) 살아 있는 캡션이다.'
        result = fp.check_caption_numbers(self.dir, body, 'ko')
        self.assertIsNotNone(result)
        want, found, untranslated, disagree = result
        self.assertEqual(want, 1)
        self.assertEqual(found, [1])
        self.assertEqual((untranslated, disagree), ([], []))


if __name__ == '__main__':
    unittest.main()
