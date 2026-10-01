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
        # Every entry, and only the entries: the `# References` heading opens
        # the run but is kept in the prose before it, so that a translator
        # sees it. Inside the run nothing would ever translate it.
        self.assertEqual(sum(len(s[1]) for s in bib), len(blocks) - 1)

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


class AHeadingDeclaresTheExtentAndDensityDoesNot(unittest.TestCase):
    r"""Read out of a PDF, this journal's entries arrive as `1.` on one
    line, the authors on the next and the journal name on a third. Barely a
    third of the lines look like a reference, so the density escape fired on
    the first entry and closed the run: 48 references, 398 characters
    exempted, and the rest dispatched to be translated.

    A paper writing `## References` has declared where its bibliography
    begins, and the next heading of the same rank declares where it ends.
    Entry density in between can then only overrule the paper about its own
    structure."""

    PDF_ENTRY = ('%d.\n'
                 'Rudovic, O., Lee, J. & Picard, R. W. Personalized machine\n'
                 'learning for robot perception. Sci.\n'
                 'Robot. 3, eaao6760 (2018).\n')

    def segments(self, blocks):
        return convert.segment_blocks_by_bibliography(blocks)

    def test_a_declared_run_survives_entries_that_do_not_look_dense(self):
        blocks = ['## References\n'] + [self.PDF_ENTRY % n
                                        for n in range(1, 13)]
        bib = [s for s in self.segments(blocks) if s[0]]
        self.assertEqual(len(bib), 1, 'broken into %d runs' % len(bib))
        # 12, not 13: the heading opens the run and stays outside it.
        self.assertEqual(len(bib[0][1]), 12)

    def test_the_next_heading_of_the_same_rank_still_ends_it(self):
        blocks = (['## References\n']
                  + [self.PDF_ENTRY % n for n in range(1, 5)]
                  + ['## Acknowledgements\n',
                     'We thank the reviewers for their time.\n'])
        segs = self.segments(blocks)
        bib = [s for s in segs if s[0]]
        self.assertEqual(len(bib), 1)
        self.assertEqual(len(bib[0][1]), 4)   # the 4 entries, not the heading
        self.assertNotIn('## Acknowledgements\n', bib[0][1])

    def test_a_heading_only_opener_stays_in_the_prose_before_it(self):
        """`## References` is a section heading, not a reference. Left in the
        run it is copied verbatim with the entries and nothing translates
        it, so the book prints one English heading among the Korean ones."""
        blocks = ['Earlier prose that ends the body. ' * 4,
                  '## References\n'] + [self.PDF_ENTRY % n for n in (1, 2, 3)]
        segs = self.segments(blocks)
        bib = [s for s in segs if s[0]]
        self.assertEqual(len(bib), 1)
        self.assertNotIn('## References\n', bib[0][1])
        self.assertIn('## References\n', [b for s in segs if not s[0]
                                          for b in s[1]])
        self.assertEqual(len(bib[0][1]), 3)

    def test_a_heading_glued_to_its_entries_is_not_moved(self):
        """Moving that block would send the entries to a translator."""
        glued = '## References\n' + (self.PDF_ENTRY % 1)
        segs = self.segments([glued] + [self.PDF_ENTRY % n for n in (2, 3)])
        bib = [s for s in segs if s[0]]
        self.assertEqual(len(bib), 1)
        self.assertIn(glued, bib[0][1])

    def test_an_unmarked_citeproc_list_still_closes_on_prose(self):
        """Density is the only signal when the paper declares nothing, so
        it has to keep working exactly as it did."""
        blocks = ['Rudovic, O., Lee, J. Sci. Robot. 3, eaao6760 (2018).\n',
                  'Li, G., Zhu, R. Nat. Electron. 5, eabc8134 (2020).\n',
                  'The discussion resumes here in ordinary prose that '
                  'carries no citation shape at all. ' * 3]
        segs = self.segments(blocks)
        bib = [s for s in segs if s[0]]
        self.assertEqual(len(bib), 1)
        self.assertNotIn(blocks[-1], bib[0][1])


if __name__ == '__main__':
    unittest.main()
