# -*- coding: utf-8 -*-
r"""Two language editions of one paper are two runs, not one.

`cmd_record` keyed its store on the paper alone, so the second edition
replaced the first. DeeR-VLA was translated into Korean and then Chinese in a
single session: the Chinese row overwrote the Korean one, and what it erased
was the Korean run's `meta_evidence` firing on five chunks out of eight --
past BRIEF_FAULT_SHARE, which is the exact shape this store exists to
remember. The surviving row read `failed: 0`.

`cmd_tally` excluded the same key from history, so judging the Chinese run
could not see the Korean one either. That is the comparison most worth
having: a defect in BOTH editions of one paper says the brief or the tool is
at fault rather than the language.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import referee


KO = {'paper': '2411.02359', 'lang': 'ko', 'chunks': 18, 'failed': 5,
      'checks': {'meta_evidence': {'severity': 'fail',
                                   'chunks': ['chunk0001', 'chunk0002',
                                              'chunk0004', 'chunk0005',
                                              'chunk0006']}}}
ZH = {'paper': '2411.02359', 'lang': 'zh', 'chunks': 18, 'failed': 0,
      'checks': {}}


class EditionKey(unittest.TestCase):

    def test_the_same_paper_in_two_languages_is_two_editions(self):
        self.assertNotEqual(referee.edition_of(KO), referee.edition_of(ZH))

    def test_a_rerun_of_one_edition_is_the_same_edition(self):
        again = dict(ZH, failed=1)
        self.assertEqual(referee.edition_of(ZH), referee.edition_of(again))

    def test_a_row_missing_its_language_still_keys(self):
        self.assertEqual(referee.edition_of({'paper': 'x'}), ('x', None))


class RecordingKeepsBothEditions(unittest.TestCase):
    """The replace-my-own-row rule, exercised the way cmd_record uses it."""

    def keep(self, rows, run):
        return [r for r in rows
                if referee.edition_of(r) != referee.edition_of(run)] + [run]

    def test_the_second_edition_does_not_erase_the_first(self):
        rows = self.keep([KO], ZH)
        self.assertEqual(len(rows), 2)
        langs = sorted(r['lang'] for r in rows)
        self.assertEqual(langs, ['ko', 'zh'])
        # The Korean run's five-chunk failure is still on the record.
        korean = [r for r in rows if r['lang'] == 'ko'][0]
        self.assertIn('meta_evidence', korean['checks'])

    def test_re_recording_one_edition_replaces_only_itself(self):
        rows = self.keep(self.keep([KO], ZH), dict(ZH, failed=2))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r for r in rows if r['lang'] == 'zh'][0]['failed'], 2)
        self.assertEqual([r for r in rows if r['lang'] == 'ko'][0]['failed'], 5)


class TallySeesTheOtherEdition(unittest.TestCase):

    def test_the_other_edition_counts_as_history(self):
        history = [r for r in [KO] if referee.edition_of(r) !=
                   referee.edition_of(ZH)]
        self.assertEqual(len(history), 1)

    def test_a_run_is_never_its_own_history(self):
        history = [r for r in [KO, ZH] if referee.edition_of(r) !=
                   referee.edition_of(ZH)]
        self.assertEqual([r['lang'] for r in history], ['ko'])


if __name__ == '__main__':
    unittest.main()
