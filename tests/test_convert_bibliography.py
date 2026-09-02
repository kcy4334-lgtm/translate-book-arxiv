# -*- coding: utf-8 -*-
"""The reference list gets its own chunks, and the feature is not a no-op.

Measured across three papers, 27-34% of everything handed to the translation
sub-agents was the bibliography, which comes back unchanged because keeping it
in the original language is the decision. Those were also the largest chunks —
CafeQ's was 25,296 characters, a third of the paper in one chunk — so they set
the wall-clock floor as well as burning the tokens.

The first class here exists because the first implementation did NOTHING. It
guessed that a structural block was a dict when it is a `(text, kind)` tuple,
so the text accessor returned `''` for every block, nothing ever matched, and
the feature compiled cleanly and passed all 767 tests. Fixtures I invented
could not catch it because the same wrong assumption was in the fixtures. So
these tests assert against the REAL block shape and require the segmenter to
actually separate something.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import convert                                                   # noqa: E402


def blocks_of(text):
    """Parse with the real parser, so the shape is the real shape."""
    return convert.weld_figure_blocks(convert.parse_structural_blocks(text))


def segments(text):
    return convert.segment_blocks_by_bibliography(blocks_of(text))


def bib_text(segs):
    return "\n".join(convert._block_text(b)
                     for is_bib, group in segs if is_bib for b in group)


def prose_text(segs):
    return "\n".join(convert._block_text(b)
                     for is_bib, group in segs if not is_bib for b in group)


PROSE = (
    "## Limitation\n\n"
    "This work still has several limitations that we describe now.\n\n"
    "Second, AlphaQ relies on heavy-tailedness as a proxy for importance, "
    "following Martin and Mahoney 2019.\n\n"
)
ENTRIES = "".join(
    "Author%d, First, Second Author, and Third Author. 202%d. "
    "\u201cA Paper Title Here.\u201d In *Proceedings of the Conference*, pp. 1-9.\n\n"
    % (i, i % 10) for i in range(8))
LATEX_BIB = (
    "\\begin{thebibliography}{29}\n"
    "\\providecommand{\\natexlab}[1]{#1}\n"
    + "".join("\\bibitem[Brown et~al.(2020)]{b%d}\n"
              "Tom Brown, Benjamin Mann, Nick Ryder, and Melanie Subbiah.\n"
              "\\newblock Language models are few-shot learners.\n" % i
              for i in range(6))
    + "\\end{thebibliography}\n")


class TheFeatureActuallyRunsTests(unittest.TestCase):
    """Guards against the failure mode that a green suite cannot see."""

    def test_the_text_accessor_reads_a_real_block(self):
        found = blocks_of("# Title\n\nSome prose here.\n")
        self.assertTrue(found, "the parser returned nothing to test against")
        self.assertTrue(
            any(convert._block_text(b).strip() for b in found),
            "_block_text returned '' for every real block — the accessor is "
            "guessing the block shape again, and everything downstream of it "
            "silently does nothing")

    def test_a_real_block_is_a_text_kind_tuple(self):
        first = blocks_of("# Title\n")[0]
        self.assertIsInstance(first, tuple)
        self.assertEqual(len(first), 2)
        self.assertEqual(convert._block_text(first), first[0])

    def test_the_segmenter_separates_something(self):
        """Not 'returns without error' — actually splits."""
        segs = segments(PROSE + ENTRIES)
        self.assertTrue(any(is_bib for is_bib, _ in segs),
                        "no bibliography segment was produced at all, which "
                        "is what a no-op looks like from the outside")
        self.assertTrue(any(not is_bib for is_bib, _ in segs))

    def test_the_citation_predicate_is_the_checker_s_own(self):
        # One copy, so the splitter and verify_chunk cannot drift apart.
        import verify_chunk
        self.assertIs(convert._is_reference_line,
                      verify_chunk._is_reference_line)


class ThreeShapesOfBibliographyTests(unittest.TestCase):
    """A paper delivers its references in one of three forms."""

    def test_the_latex_environment(self):
        segs = segments(PROSE + LATEX_BIB)
        self.assertIn("thebibliography", bib_text(segs))
        self.assertNotIn("Limitation", bib_text(segs))

    def test_a_references_heading(self):
        segs = segments(PROSE + "## References\n\n" + ENTRIES)
        self.assertIn("References", bib_text(segs))
        self.assertIn("Author0", bib_text(segs))
        self.assertNotIn("Limitation", bib_text(segs))

    def test_bare_entries_with_no_marker_at_all(self):
        # AlphaQ: citeproc emits paragraphs, and the heading is added later
        # during the build, so neither structural marker exists here.
        segs = segments(PROSE + ENTRIES)
        self.assertIn("Author0", bib_text(segs))
        self.assertIn("Limitation", prose_text(segs))

    def test_a_paper_with_no_bibliography_is_left_alone(self):
        segs = segments(PROSE)
        self.assertEqual([is_bib for is_bib, _ in segs], [False])


class ProseIsNotABibliographyTests(unittest.TestCase):

    def test_a_discourse_connective_does_not_open_a_run(self):
        # "Second, AlphaQ relies on ... Martin and Mahoney 2019" has the shape
        # of an author list and a year, and opened a run for a while.
        segs = segments(PROSE)
        self.assertNotIn("Second, AlphaQ", bib_text(segs))

    def test_one_citation_shaped_paragraph_does_not_open_a_run(self):
        text = ("## Method\n\nWe follow the setup described earlier.\n\n"
                "Author1, First, and Second Author. 2021. \u201cA Title.\u201d "
                "In *Proceedings*.\n\n"
                "The rest of this section describes the training procedure "
                "and the hyperparameters we used throughout.\n")
        segs = segments(text)
        self.assertFalse(any(is_bib for is_bib, _ in segs),
                         "a run needs two consecutive entries to open")

    def test_prose_after_the_bibliography_stays_prose(self):
        # Chunk order is document order, so a segment cannot be moved.
        text = PROSE + LATEX_BIB + "\n## Appendix A\n\nExtra material here.\n"
        segs = segments(text)
        self.assertIn("Appendix A", prose_text(segs))
        self.assertNotIn("Appendix A", bib_text(segs))
        self.assertEqual([is_bib for is_bib, _ in segs], [False, True, False])


class DocumentOrderTests(unittest.TestCase):
    """The merge concatenates chunks by number, so order is not negotiable."""

    def test_every_block_survives_in_its_original_order(self):
        text = PROSE + LATEX_BIB + "\n## Appendix A\n\nExtra material.\n"
        original = [convert._block_text(b) for b in blocks_of(text)]
        segmented = [convert._block_text(b)
                     for _is_bib, group in segments(text) for b in group]
        self.assertEqual(segmented, original,
                         "segmenting must not drop, duplicate or reorder a "
                         "block — the merge would produce a different book")

    def test_blank_blocks_between_entries_do_not_end_the_run(self):
        # Entries are separated by empty blocks; looking at the next index
        # rather than the next non-empty one meant a run never opened.
        segs = segments(PROSE + ENTRIES)
        bib = bib_text(segs)
        for i in range(8):
            self.assertIn("Author%d" % i, bib,
                          "a blank block between entries broke the run")


if __name__ == "__main__":
    unittest.main()
