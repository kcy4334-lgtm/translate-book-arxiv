# -*- coding: utf-8 -*-
r"""The reference list must come out as ONE run, not one segment per entry.

A reference chunk has its output written at conversion time, so no sub-agent
is dispatched for it and no reference is translated. That protection was
reaching exactly half the entries.

The run ended on every second `\bibitem` and reopened on the next: the escape
that says "prose again, the run is over" tests block DENSITY, and a lone
`\bibitem` block is not dense. So the segments alternated bib, not-bib, bib,
not-bib. Twenty of Attention's forty-one entries and twenty-five of ResNet's
fifty-one lost the exemption and were dispatched to be TRANSLATED — the one
thing a reference must not be — while the chunk count went from 9 to 49 and
from 11 to 61.

A block holding a `\bibitem` is not prose, whatever its density says.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import convert


def entry(key, author):
    return '\\bibitem{%s}\n%s\\newblock Some title. 2020.\n' % (key, author)


class OneRun(unittest.TestCase):

    def segments(self, blocks):
        return convert.segment_blocks_by_bibliography(blocks)

    def test_consecutive_entries_form_a_single_run(self):
        blocks = ['# References\n',
                  entry('a', 'A. Author. '),
                  entry('b', 'B. Author. '),
                  entry('c', 'C. Author. '),
                  entry('d', 'D. Author. ')]
        segs = self.segments(blocks)
        bib = [s for s in segs if s[0]]
        self.assertEqual(len(bib), 1, 'the run was broken into %d' % len(bib))
        self.assertEqual(sum(len(s[1]) for s in bib), len(blocks))

    def test_every_entry_keeps_the_exemption(self):
        blocks = [entry(chr(97 + i), '%c. Author. ' % (65 + i))
                  for i in range(8)]
        segs = self.segments(blocks)
        exempt = sum(len(s[1]) for s in segs if s[0])
        self.assertEqual(exempt, 8)

    def test_prose_after_the_list_ends_the_run(self):
        """A paper may put an appendix after its references."""
        body = 'This appendix explains the derivation in detail. ' * 6
        blocks = [entry('a', 'A. Author. '), entry('b', 'B. Author. '), body]
        segs = self.segments(blocks)
        self.assertFalse(segs[-1][0], 'the appendix was taken for a reference')

    def test_prose_before_the_list_is_not_swallowed(self):
        body = 'We conclude that the method works on every benchmark. ' * 6
        blocks = [body, entry('a', 'A. Author. '), entry('b', 'B. Author. ')]
        segs = self.segments(blocks)
        self.assertFalse(segs[0][0])
        self.assertTrue(segs[-1][0])

    def test_a_document_with_no_references_has_no_exempt_segment(self):
        blocks = ['# Introduction\n', 'Ordinary prose. ' * 20]
        self.assertFalse([s for s in self.segments(blocks) if s[0]])

    def test_the_closing_environment_stays_with_the_run(self):
        blocks = ['\\begin{thebibliography}{10}\n',
                  entry('a', 'A. Author. '),
                  '\\end{thebibliography}\n']
        segs = self.segments(blocks)
        bib = [s for s in segs if s[0]]
        self.assertEqual(len(bib), 1)
        self.assertEqual(len(bib[0][1]), 3)


if __name__ == '__main__':
    unittest.main()
