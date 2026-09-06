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


class OneCopyOfEachStep(unittest.TestCase):
    r"""The filter, the record sequence and the flag wording were each written
    more than once: `cmd_tally`, `cmd_record` and an inline block in
    `merge_and_build`. The wording had already drifted -- one copy said
    "Whatever it is, nobody has fixed it" and the other "Nobody has fixed it".
    Two hand-kept copies of one sentence is how a fix reaches one caller and
    not the other, which is exactly what this module was repaired for twice in
    one session."""

    def test_history_excludes_only_this_edition(self):
        data = {'runs': [KO, ZH]}
        self.assertEqual([r['lang'] for r in referee.history_for(data, ZH)],
                         ['ko'])

    def test_remember_replaces_this_edition_and_keeps_the_other(self):
        data = referee.remember({'runs': [KO, ZH]}, dict(ZH, failed=2))
        self.assertEqual(len(data['runs']), 2)
        by_lang = {r['lang']: r for r in data['runs']}
        self.assertEqual(by_lang['zh']['failed'], 2)
        self.assertEqual(by_lang['ko']['failed'], 5)

    def test_remember_on_an_empty_store(self):
        data = referee.remember({'runs': []}, KO)
        self.assertEqual([r['lang'] for r in data['runs']], ['ko'])

    def test_the_flag_sentences_exist_once_and_take_the_prefix(self):
        flags = [('brief', 'meta_evidence', 5, 8), ('chronic', 'structure', 3, 9)]
        plain = referee.flag_lines(flags)
        prefixed = referee.flag_lines(flags, 'REFEREE/')
        self.assertTrue(plain[0].startswith('BRIEF: '))
        self.assertTrue(prefixed[0].startswith('REFEREE/BRIEF: '))
        # Same sentence either way; only the prefix differs.
        self.assertEqual(prefixed[0][len('REFEREE/'):], plain[0])
        self.assertEqual(prefixed[1][len('REFEREE/'):], plain[1])

    def test_no_flags_prints_nothing(self):
        self.assertEqual(referee.flag_lines([]), [])


class TheBuildDoesNotKeepItsOwnCopy(unittest.TestCase):
    """A source rule, because the drift was invisible from behaviour: both
    copies worked, they just said different things and were fixed apart."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'scripts', 'merge_and_build.py')
        with open(path, encoding='utf-8') as fh:
            self.body = fh.read()

    def test_it_calls_the_shared_entry_point(self):
        self.assertIn('referee.judge_and_record(', self.body)

    def test_it_does_not_reimplement_the_flag_wording(self):
        for phrase in ('fired on %d of %d chunks', 'has now fired in %d runs'):
            self.assertNotIn(phrase, self.body,
                             'the flag wording belongs in referee.flag_lines')

    def test_it_does_not_reimplement_the_record_sequence(self):
        self.assertNotIn("data['runs'].append(run)", self.body)


if __name__ == '__main__':
    unittest.main()
