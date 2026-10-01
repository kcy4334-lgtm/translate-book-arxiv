# -*- coding: utf-8 -*-
r"""Tests for how far a raw LaTeX table's float span reaches.

The expander replaces `md[start:stop]` with one rendered table and moves its
cursor to `stop`, so a span that reaches too far does not merely mislabel
something -- it deletes every paragraph inside it. That is what happened:
`_widen_to_float` searched backwards for a `\begin{table}` without checking
whether that float had already closed, found the PREVIOUS one, then searched
forward for its `\end{table}` and found the NEXT one. SINQ's table 5 came
back with a span 22,038 characters wide.

316 Korean words vanished from SINQ that way and 194 from AlphaQ, and
nothing said so: every table was still counted, every number was still in
its cell, and the prose between the tables was simply not in the book.
CafeQ, whose spans never overlapped, lost nothing -- which is how the cause
was pinned down.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

TABULAR = '\\begin{tabular}{c}\n%s \\\\\n\\end{tabular}'

DOC = ('\\begin{table}\n' + (TABULAR % 'a') + '\n\\caption{first}\n'
       '\\end{table}\n\n'
       '이 문단은 두 표 사이에 있으며 책에 남아 있어야 한다.\n\n'
       + (TABULAR % 'b') + '\n\n'
       '두 번째 문단도 마찬가지로 남아야 한다.\n\n'
       '\\begin{table}\n' + (TABULAR % 'c') + '\n\\caption{third}\n'
       '\\end{table}\n')

SHARED = ('\\begin{table*}\n'
          '\\caption{left}\n' + (TABULAR % 'a') + '\n'
          '\\caption{right}\n' + (TABULAR % 'b') + '\n'
          '\\end{table*}\n')


class FloatSpans(unittest.TestCase):

    def test_a_bare_tabular_does_not_borrow_a_closed_float(self):
        at = DOC.index(TABULAR % 'b')
        start, stop, env = mb._widen_to_float(DOC, at,
                                              at + len(TABULAR % 'b'))
        self.assertIsNone(env)
        self.assertEqual(DOC[start:stop], TABULAR % 'b')

    def test_spans_never_run_past_each_other(self):
        spans = [(t['start'], t['stop']) for t in
                 mb.find_raw_latex_tables(DOC)]
        self.assertEqual(len(spans), 3)
        for (_a, prev_stop), (start, _b) in zip(spans, spans[1:]):
            self.assertGreaterEqual(start, prev_stop, spans)

    def test_the_prose_between_tables_is_outside_every_span(self):
        prose = DOC.index('이 문단은')
        for t in mb.find_raw_latex_tables(DOC):
            self.assertFalse(t['start'] <= prose < t['stop'],
                             'a float span swallowed the paragraph')

    def test_a_float_still_widens_around_its_own_table(self):
        first = mb.find_raw_latex_tables(DOC)[0]
        self.assertEqual(first['float'], 'table')
        self.assertTrue(DOC[first['start']:first['stop']]
                        .startswith('\\begin{table}'))
        self.assertTrue(DOC[first['start']:first['stop']]
                        .endswith('\\end{table}'))

    def test_two_tabulars_in_one_float_share_its_span(self):
        # This overlap is the legitimate one: the float really does hold
        # both, and the expander emits an empty slice between them.
        tables = mb.find_raw_latex_tables(SHARED)
        self.assertEqual(len(tables), 2)
        self.assertEqual((tables[0]['start'], tables[0]['stop']),
                         (tables[1]['start'], tables[1]['stop']))


if __name__ == '__main__':
    unittest.main()
