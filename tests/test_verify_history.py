# -*- coding: utf-8 -*-
r"""The gate writes down what it saw, because nothing else is there to see it.

The referee described a run by running `verify_chunk` once, at the end. By
then the failures are repaired: the build refuses to finish while a chunk
fails, so every run reached that moment clean. DeeR-VLA's Korean edition had
`meta_evidence` fire on five chunks out of eight, past BRIEF_FAULT_SHARE and
exactly the shape the store exists to catch, and it was recorded as
`failed: 0`.

The obvious answer -- tell whoever runs it to record after every batch -- is
not one. That is a prose step, and this repository's own record is that prose
steps get skipped. It was skipped in the session that found the bug, by the
agent that had just read the rule.

So the gate journals every verdict as it goes, and the referee reads that
back. A chunk that failed and was then fixed still counts, because
BRIEF_FAULT_SHARE asks how many chunks a check FIRED on, not how many are
still broken.
"""
from __future__ import unicode_literals

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import referee
import verify_chunk as vc


def result(chunk, ok, findings=()):
    return {'chunk': chunk, 'ok': ok, 'findings': list(findings)}


def finding(check, severity='fail'):
    return {'check': check, 'severity': severity, 'detail': '', 'evidence': ''}


class TheGateJournalsWhatItSaw(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='verifyhist-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def rows(self):
        path = os.path.join(self.dir, vc.VERIFY_HISTORY)
        with io.open(path, encoding='utf-8') as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_a_failure_is_written_down(self):
        vc.journal_run(self.dir, 'ko', [
            result('chunk0001', False, [finding('meta_evidence')]),
            result('chunk0002', True)])
        row = self.rows()[0]
        self.assertEqual(row['lang'], 'ko')
        self.assertEqual(row['failed'], ['chunk0001'])
        self.assertEqual(row['checks']['meta_evidence']['chunks'],
                         ['chunk0001'])

    def test_a_clean_run_still_records_its_chunks(self):
        """The denominator BRIEF_FAULT_SHARE divides by."""
        vc.journal_run(self.dir, 'ko', [result('chunk0001', True)])
        row = self.rows()[0]
        self.assertEqual(row['checks'], {})
        self.assertEqual(row['chunks'], ['chunk0001'])

    def test_each_run_appends(self):
        vc.journal_run(self.dir, 'ko', [result('chunk0001', True)])
        vc.journal_run(self.dir, 'ko', [result('chunk0002', True)])
        self.assertEqual(len(self.rows()), 2)

    def test_it_never_raises_when_it_cannot_write(self):
        """A record that can break the thing it observes gets removed."""
        missing = os.path.join(self.dir, 'nope', 'deeper')
        vc.journal_run(missing, 'ko', [result('chunk0001', True)])
        vc.journal_run(None, 'ko', [result('chunk0001', True)])


class TheRefereeReadsItBack(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='verifyhist-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_failure_survives_being_fixed(self):
        """The whole point: five chunks failed, then passed, and the record
        still says the check fired on five."""
        vc.journal_run(self.dir, 'ko', [
            result('chunk000%d' % n, False, [finding('meta_evidence')])
            for n in range(1, 6)])
        vc.journal_run(self.dir, 'ko', [
            result('chunk000%d' % n, True) for n in range(1, 6)])
        checks, seen = referee.journalled_checks(self.dir)
        self.assertEqual(seen, 5)
        self.assertEqual(len(checks['meta_evidence']['chunks']), 5)
        self.assertEqual(checks['meta_evidence']['severity'], 'fail')

    def test_a_warning_does_not_overwrite_a_failure(self):
        vc.journal_run(self.dir, 'ko', [
            result('chunk0001', False, [finding('structure', 'fail')])])
        vc.journal_run(self.dir, 'ko', [
            result('chunk0002', True, [finding('structure', 'warn')])])
        checks, _seen = referee.journalled_checks(self.dir)
        self.assertEqual(checks['structure']['severity'], 'fail')
        self.assertEqual(sorted(checks['structure']['chunks']),
                         ['chunk0001', 'chunk0002'])

    def test_no_journal_is_not_an_error(self):
        self.assertEqual(referee.journalled_checks(self.dir), ({}, 0))
        self.assertEqual(referee.journalled_checks(None), ({}, 0))

    def test_a_damaged_line_is_skipped_not_fatal(self):
        vc.journal_run(self.dir, 'ko', [
            result('chunk0001', False, [finding('meta_evidence')])])
        with io.open(os.path.join(self.dir, vc.VERIFY_HISTORY), 'a',
                     encoding='utf-8') as fh:
            fh.write('{not json\n\n')
        checks, seen = referee.journalled_checks(self.dir)
        self.assertIn('meta_evidence', checks)
        self.assertEqual(seen, 1)


if __name__ == '__main__':
    unittest.main()
