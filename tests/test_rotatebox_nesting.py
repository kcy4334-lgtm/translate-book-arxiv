# -*- coding: utf-8 -*-
r"""Tests for band labels written as one box inside another.

A narrow column carries its group name rotated, and pandoc drops
`\rotatebox` and `\multirow` whole -- argument, body and all. `unwrap_rotatebox`
exists for that, and it handled each call alone while SINQ writes every one
of its 32 labels nested:

    \multirow{4}{*}{\rotatebox[origin=c]{90}{\scriptsize\textsc{3-bit}}}

One pass took the `\multirow` and stepped the cursor past the whole group, so
the `\rotatebox` inside started behind the cursor and was skipped. Nine of
SINQ's nineteen tables then rendered their group column empty: table 1
printed the same four method rows twice -- RTN, Hadamard + RTN, HQQ, SINQ --
with nothing saying which block was 3-bit and which was 4-bit, and the
section text claiming a win in every uncalibrated case could not be checked
against it.

The existing tests covered `\rotatebox` alone, `\multirow` alone, and the two
in different cells. None of them nested one in the other.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab


class RotateboxNesting(unittest.TestCase):

    def test_multirow_around_rotatebox(self):
        got, n = ab.unwrap_rotatebox(
            r'\multirow{4}{*}{\rotatebox[origin=c]{90}'
            r'{\scriptsize\textsc{3-bit}}}')
        self.assertEqual(got, r'\scriptsize\textsc{3-bit}')
        self.assertEqual(n, 2)

    def test_rotatebox_around_multirow(self):
        got, n = ab.unwrap_rotatebox(
            r'\rotatebox{90}{\multirow{3}{*}{\textsc{Calibrated}}}')
        self.assertEqual(got, r'\textsc{Calibrated}')
        self.assertEqual(n, 2)

    def test_each_alone_still_works(self):
        self.assertEqual(
            ab.unwrap_rotatebox(r'\rotatebox[origin=c]{90}{\textsc{4-bit}}'),
            (r'\textsc{4-bit}', 1))
        self.assertEqual(
            ab.unwrap_rotatebox(r'\multirow{10}{*}{\textsc{Calibration-free}}'),
            (r'\textsc{Calibration-free}', 1))

    def test_a_plain_cell_is_untouched(self):
        row = r'RTN & 1.28 & 32.43 & 31.10 \\'
        self.assertEqual(ab.unwrap_rotatebox(row), (row, 0))

    def test_two_nested_labels_in_one_row(self):
        got, n = ab.unwrap_rotatebox(
            r'& \multirow{4}{*}{\rotatebox{90}{\textsc{3-bit}}}'
            r' & \multirow{4}{*}{\rotatebox{90}{\textsc{4-bit}}} \\')
        self.assertNotIn('rotatebox', got)
        self.assertNotIn('multirow', got)
        self.assertIn(r'\textsc{3-bit}', got)
        self.assertIn(r'\textsc{4-bit}', got)
        self.assertEqual(n, 4)

    def test_nothing_is_left_for_pandoc_to_eat(self):
        # The whole point: after this pass no box command survives, because
        # every one that does takes its label with it.
        source = (r'\begin{tabular}{ccl}' '\n'
                  r'& \multirow{4}{*}{\rotatebox[origin=c]{90}'
                  r'{\scriptsize\textsc{3-bit}}} & RTN & 1.28 \\' '\n'
                  r'\end{tabular}')
        got, _n = ab.unwrap_rotatebox(source)
        self.assertNotIn('rotatebox', got)
        self.assertNotIn('multirow', got)


if __name__ == '__main__':
    unittest.main()
