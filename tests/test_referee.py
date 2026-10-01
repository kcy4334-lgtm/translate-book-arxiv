# -*- coding: utf-8 -*-
r"""The counting half of the referee, which is the half a script can be sure of.

`verify_chunk` rejects one chunk. What it cannot see is the shape of the
failures: a defect on a third of a run is the BRIEF — every instance of a role
read the same prompt — and a defect in three books is something nobody has
fixed. Both readings are arithmetic, so they belong here; the judgement of
whose fault it is belongs to the agent, which can read the check's code.

The trap this locks shut: a run compared against its own earlier row reports
every defect as a repeat, which is the one thing a repeat-detector must never
do. TinyVLA's first tally said "seen before in TinyVLA".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import referee


def run(paper, chunks, **checks):
    return {'paper': paper, 'lang': 'ko', 'chunks': chunks,
            'failed': len(checks),
            'checks': dict((k, {'severity': 'fail', 'chunks': list(v)})
                           for k, v in checks.items())}


class BriefFault(unittest.TestCase):

    def flags(self, this, history=()):
        return referee.judge(this, list(history))[1]

    def test_a_third_of_a_run_reads_as_the_brief(self):
        flags = self.flags(run('p1', 9, meta_evidence=('c1', 'c2', 'c3')))
        self.assertIn('brief', [kind for kind, _k, _n, _t in flags])

    def test_one_chunk_does_not(self):
        flags = self.flags(run('p1', 9, meta_evidence=('c1',)))
        self.assertEqual(flags, [])

    def test_two_of_twenty_does_not(self):
        flags = self.flags(run('p1', 20, placeholders=('c1', 'c2')))
        self.assertEqual([k for k, _a, _b, _c in flags], [])

    def test_a_single_chunk_run_is_never_a_brief_fault(self):
        """1 of 1 is 100% and still one agent slipping once."""
        flags = self.flags(run('p1', 1, placeholders=('c1',)))
        self.assertEqual(flags, [])


class Chronic(unittest.TestCase):

    def flags(self, this, history=()):
        return referee.judge(this, list(history))[1]

    def test_a_third_run_is_chronic(self):
        history = [run('p1', 9, placeholders=('c1',)),
                   run('p2', 9, placeholders=('c1',))]
        flags = self.flags(run('p3', 9, placeholders=('c1',)), history)
        self.assertIn('chronic', [kind for kind, _k, _n, _t in flags])

    def test_a_second_run_is_not_yet(self):
        history = [run('p1', 9, placeholders=('c1',))]
        flags = self.flags(run('p2', 9, placeholders=('c1',)), history)
        self.assertNotIn('chronic', [kind for kind, _k, _n, _t in flags])

    def test_a_different_check_does_not_accumulate(self):
        history = [run('p1', 9, placeholders=('c1',)),
                   run('p2', 9, images=('c1',))]
        flags = self.flags(run('p3', 9, fences=('c1',)), history)
        self.assertEqual(flags, [])


class CleanRun(unittest.TestCase):

    def test_nothing_fired_says_so_and_flags_nothing(self):
        lines, flags = referee.judge(run('p1', 9), [])
        self.assertEqual(flags, [])
        self.assertIn('nothing fired', ' '.join(lines))


class History(unittest.TestCase):

    def test_a_papers_own_row_is_not_its_history(self):
        """Comparing a run with itself makes every defect look like a repeat."""
        this = run('p1', 9, placeholders=('c1',))
        stored = [run('p1', 9, placeholders=('c1',)),
                  run('p2', 9, images=('c1',))]
        history = [r for r in stored if r['paper'] != this['paper']]
        lines, _flags = referee.judge(this, history)
        self.assertNotIn('seen before in p1', ' '.join(lines))

    def test_another_papers_row_is(self):
        this = run('p2', 9, placeholders=('c1',))
        history = [run('p1', 9, placeholders=('c1',))]
        lines, _flags = referee.judge(this, history)
        self.assertIn('seen before in p1', ' '.join(lines))


if __name__ == '__main__':
    unittest.main()
