# -*- coding: utf-8 -*-
r"""One equation number shared a line with its equation, and the probe failed.

`check_equations` counts a printed number only when the `(N)` stands alone on
its extracted line. Maynard's `(6.15)` does not, so the PDF side read 105 about
a paper that prints 106 — and the probe reported a mismatch on a book whose
equation numbering was, by then, exactly right.

The counter runs 1..max within each group, so the per-group maxima are the true
total and survive a gap. The guard matters as much as the extrapolation: if the
extraction is patchy the maxima are not evidence of anything, so below nine
tenths of a group the raw count stands and the probe stays honest about not
knowing.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import source_probe as sp  # noqa: E402


def markers(*items):
    return ['(%s)' % s for s in items]


class OneMissingNumberIsRecovered(unittest.TestCase):
    def test_a_complete_run_counts_itself(self):
        self.assertEqual(sp.printed_equation_count(
            markers('1.1', '1.2', '1.3')), 3)

    def test_a_single_gap_is_bridged(self):
        got = sp.printed_equation_count(
            markers(*['6.%d' % i for i in range(1, 23) if i != 15]))
        self.assertEqual(got, 22)

    def test_several_groups_sum(self):
        got = sp.printed_equation_count(
            markers('1.1', '1.2', '2.1', '2.2', '2.3'))
        self.assertEqual(got, 5)

    def test_undotted_numbering_works_too(self):
        self.assertEqual(sp.printed_equation_count(markers(*'123456789')), 9)


class APatchyExtractionIsNotExtrapolated(unittest.TestCase):
    def test_a_large_gap_falls_back_to_the_raw_count(self):
        # Half the group missing: the maxima say nothing trustworthy.
        got = sp.printed_equation_count(markers('5.1', '5.20'))
        self.assertEqual(got, 2)

    def test_nothing_extracted_returns_zero(self):
        self.assertEqual(sp.printed_equation_count([]), 0)

    def test_a_non_numeric_marker_is_ignored_not_fatal(self):
        self.assertEqual(sp.printed_equation_count(['(a)', '(1)', '(2)']), 2)

    def test_a_group_of_one_is_not_inflated(self):
        self.assertEqual(sp.printed_equation_count(markers('4.1')), 1)


if __name__ == '__main__':
    unittest.main()
