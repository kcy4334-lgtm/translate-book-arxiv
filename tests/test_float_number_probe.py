# -*- coding: utf-8 -*-
r"""A caption that opens another caption is not that caption.

DeeR-VLA has two tables whose captions start alike:

    Detailed results in the setting ABCD$\rightarrow$D.
    Detailed results in the setting ABC$\rightarrow$D.

`probe_of` stops the prose run at the arrow, so the second table's probe is
`Detailed results in the setting ABC` -- a literal prefix of the first one's.
`pdf_flat.find` returned the ABCD table, the number printed there was 10, and
the probe reported that the build numbered the ABC table wrongly. The build
had it right: the paper prints it as Table 11 too.

That is the same collision that defeated four hand-written comparators before
the check itself was read, so the fix belongs here, where a test can hold it.

The check may not go quiet instead. A float number that really does disagree
is the one thing this probe exists to catch, and it must still name which.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import source_probe as sp

TEX = ('\\begin{table}\n'
       '\\caption{Detailed results in the setting ABCD$\\rightarrow$D.}\n'
       '\\label{tab:ABCD}\n'
       '\\end{table}\n'
       '\\begin{table}\n'
       '\\caption{Detailed results in the setting ABC$\\rightarrow$D.}\n'
       '\\label{tab:ABC}\n'
       '\\end{table}\n')

PRINTED = ('Table 1: Detailed results in the setting ABCD\u2192D. Method Only '
           'RGB Input. Table 2: Detailed results in the setting ABC\u2192D. '
           'Method Only RGB Input.')


class ThePrefixCaptionFindsItsOwnTable(unittest.TestCase):

    def test_both_tables_agree(self):
        agree, disagree, _skipped, problems = sp.check_floats(
            None, TEX, PRINTED)
        self.assertEqual(problems, [])
        self.assertEqual(disagree, 0)
        self.assertEqual(agree, 2)

    def test_the_longer_caption_owns_the_shared_opening(self):
        """The ABCD table sits where both probes match. It keeps that spot."""
        needle = 'Detailed results in the setting ABC'
        rival = 'Detailed results in the setting ABCD'
        sites = list(sp.caption_sites(PRINTED, needle, [rival]))
        self.assertEqual(sites, [PRINTED.index(needle + '\u2192')])

    def test_with_no_rival_the_first_hit_still_wins(self):
        text = 'Table 4: Ablation study of exit criteria.'
        needle = 'Ablation study of exit criteria'
        self.assertEqual(list(sp.caption_sites(text, needle, [])),
                         [text.index(needle)])


class ARealDisagreementIsStillCaught(unittest.TestCase):
    r"""The prefix rule must not become a way for every float to fall silent."""

    def test_a_wrong_number_is_reported_and_named(self):
        printed = PRINTED.replace('Table 2:', 'Table 7:')
        agree, disagree, _skipped, problems = sp.check_floats(
            None, TEX, printed)
        self.assertEqual(agree, 1)
        self.assertEqual(disagree, 1)
        self.assertEqual(len(problems), 1)
        self.assertIn('Detailed results in the setting ABC', problems[0])
        self.assertIn('table 2', problems[0])
        self.assertIn('7', problems[0])

    def test_a_caption_the_paper_never_prints_is_skipped_not_failed(self):
        agree, disagree, skipped, problems = sp.check_floats(
            None, TEX, 'A paper with no captions in it at all.')
        self.assertEqual((agree, disagree, problems), (0, 0, []))
        self.assertEqual(skipped, 2)


class TheBodyMentionIsNotTheCaption(unittest.TestCase):
    """Papers quote a caption before printing it. The float label decides."""

    def test_a_quotation_in_the_prose_is_walked_past(self):
        printed = ('We report Detailed results in the setting ABC\u2192D '
                   'below. ') + PRINTED
        agree, disagree, _skipped, problems = sp.check_floats(
            None, TEX, printed)
        self.assertEqual(problems, [])
        self.assertEqual((agree, disagree), (2, 0))


if __name__ == '__main__':
    unittest.main()
