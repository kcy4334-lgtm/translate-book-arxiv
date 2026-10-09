# -*- coding: utf-8 -*-
r"""A section number on its own line above the title is still its number.

Some classes set the number and the title apart with a wide skip, and PyMuPDF
then extracts them as two lines: `1`, `Introduction`. Only the joined form
`1 Introduction` was read, so every such heading counted as unnumbered and the
book printed it without a number. Looped flows, the repository's demo book,
shipped with no section numbers while its own prose said "(5.1절)"; AlphaQ,
CafeQ and VLA-Adapter read the same way, and a code comment had concluded from
it that those papers "suppress the number in the heading". They do not.

The lines below are what those PDFs actually produce.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb  # noqa: E402


def read(lines, heads, run_in_level=0):
    return mb.prefixes_from_lines(lines, heads, run_in_level)[0]


class SentenceBertHeadings(unittest.TestCase):
    """Two of Sentence-BERT's headings printed with no number."""

    def test_a_wrapped_title_under_its_own_number_line(self):
        lines = ['4', 'Evaluation - Semantic Textual', 'Similarity',
                 'We evaluate ...']
        heads = [(1, 'Evaluation - Semantic Textual Similarity', True)]
        self.assertEqual(read(lines, heads), ['4'])

    def test_a_ligature_in_the_pdf_still_matches(self):
        lines = ['7', 'Computational Efﬁciency', 'Sentence ...']
        heads = [(1, 'Computational Efficiency', True)]
        self.assertEqual(read(lines, heads), ['7'])


class AFixedChapter(unittest.TestCase):
    r"""randmat is chapter 5 of a book (`\setcounter{chapter}{5}`) and prints
    `5.1 Introduction`. Read as level 1, two parts did not fit, the heading
    counted as unnumbered, and a stray `40` above another heading won."""

    def test_the_chapter_part_is_allowed_for(self):
        lines = ['5.1', 'Introduction', 'Text', '40',
                 'Random matrices with independent rows', '5.4',
                 'Random matrices with independent rows', 'In this section']
        heads = [(1, 'Introduction', True),
                 (1, 'Random matrices with independent rows', True)]
        self.assertEqual(mb.prefixes_from_lines(lines, heads, offset=1)[0],
                         ['5.1', '5.4'])

    def test_a_cited_section_in_a_title_takes_its_number(self):
        heads = [(4, 'For Section {s: rows}', False), (4, 'Plain', False)]
        self.assertEqual(mb.cited_titles(heads, {'s: rows': '5.4'}),
                         [(4, 'For Section 5.4', False), (4, 'Plain', False)])


class MathInTheTitle(unittest.TestCase):
    def test_a_formula_mid_title_under_its_own_number_line(self):
        # VAE's appendix B, as its PDF extracts.
        lines = ['B', 'Solution of −DKL(qφ(z)||pθ(z)), Gaussian case',
                 'The variational lower bound ...']
        heads = [(1, r'Solution of $-D_{KL}(q_{\phi}(\mathbf{z}) || '
                     r'p_{\theta}(\mathbf{z}))$, Gaussian case', True)]
        self.assertEqual(read(lines, heads), ['B'])


class RepeatedTitles(unittest.TestCase):
    """ViT has "4.6 Self-supervision" and, in the appendix, "B.1.2
    Self-supervision". One number was kept per title, so the second printed
    with none while the body cited "B.1.2절"."""

    def test_the_same_with_the_number_on_its_own_line(self):
        """The ViT PDF sets the number apart: `4.6`, then the title."""
        lines = ['4.6', 'Self-supervision', 'Transformers show ...',
                 'B.1.2', 'Self-supervision', 'We employ ...']
        heads = [(2, 'Self-supervision', True), (3, 'Self-supervision', True)]
        self.assertEqual(read(lines, heads), ['4.6', 'B.1.2'])

    def test_a_title_printed_twice_takes_its_numbers_in_order(self):
        lines = ['4.6 Self-supervision', 'Transformers show ...',
                 'B.1.2 Self-supervision', 'We employ ...']
        heads = [(2, 'Self-supervision', True), (3, 'Self-supervision', True)]
        self.assertEqual(read(lines, heads), ['4.6', 'B.1.2'])

    def test_a_title_printed_once_still_numbers_every_use(self):
        lines = ['2 Related work', 'Prior ...']
        heads = [(1, 'Related work', True)]
        self.assertEqual(read(lines, heads), ['2'])


class SplitLineNumbers(unittest.TestCase):
    def test_a_number_on_the_line_above_is_read(self):
        lines = ['sine Similarity.', '1', 'Introduction', 'Gradient-based ...',
                 '2', 'Method', 'We consider ...']
        heads = [(1, 'Introduction', True), (1, 'Method', True)]
        self.assertEqual(read(lines, heads), ['1', '2'])

    def test_dotted_numbers_follow_their_level(self):
        lines = ['3', 'Looped flows', '3.1', 'Training', '3.2', 'Inference']
        heads = [(1, 'Looped flows', True), (2, 'Training', True),
                 (2, 'Inference', True)]
        self.assertEqual(read(lines, heads), ['3', '3.1', '3.2'])

    def test_a_table_cell_cannot_number_a_top_level_heading(self):
        # Looped flows prints `11.1` in a table cell above a row labelled
        # `Looped flows`. A section number has one part per level.
        lines = ['11.1', 'Looped flows', 'text', '3', 'Looped flows']
        heads = [(1, 'Looped flows', True)]
        self.assertEqual(read(lines, heads), ['3'])

    def test_a_repeated_title_takes_its_numbers_in_order(self):
        # CafeQ: `2 Related work` in the body, `A Related work` in the
        # appendix. First-wins gave the appendix 2 as well.
        lines = ['2', 'Related work', 'body', 'A', 'Related work', 'more']
        heads = [(1, 'Related work', True), (1, 'Related work', True)]
        self.assertEqual(read(lines, heads), ['2', 'A'])

    def test_appendix_letters_are_read(self):
        lines = ['A', 'Architecture', 'x', 'E', 'Experimental details',
                 'E.1', 'Training and evaluation']
        heads = [(1, 'Architecture', True), (1, 'Experimental details', True),
                 (2, 'Training and evaluation', True)]
        self.assertEqual(read(lines, heads), ['A', 'E', 'E.1'])

    def test_the_joined_form_still_wins(self):
        lines = ['2.1 Background', 'text']
        self.assertEqual(read(lines, [(2, 'Background', True)]), ['2.1'])

    def test_a_title_with_no_number_anywhere_is_unnumbered(self):
        lines = ['some prose.', 'Acknowledgements', 'We thank ...']
        self.assertEqual(read(lines, [(1, 'Acknowledgements', False)]), [''])

    def test_a_run_in_level_is_counted_apart_from_missing(self):
        stats = {'matched': 0, 'unnumbered': 0, 'missing': 0,
                 'wrapped': 0, 'run_in': 0, 'reason': None}
        mb.prefixes_from_lines(['Baseline Algorithms To evaluate AdamX, we'],
                               [(3, 'Baseline Algorithms', True)], 3, stats)
        self.assertEqual((stats['run_in'], stats['missing']), (1, 0))


class PrefixFitsLevel(unittest.TestCase):
    def test_parts_must_match_the_level(self):
        self.assertTrue(mb._prefix_fits_level('3', 1))
        self.assertTrue(mb._prefix_fits_level('3.1', 2))
        self.assertTrue(mb._prefix_fits_level('A.3.1', 3))
        self.assertFalse(mb._prefix_fits_level('11.1', 1))
        self.assertFalse(mb._prefix_fits_level('4', 2))

    def test_ieee_letters_and_numerals_fit_any_level(self):
        # IEEE numbers subsections `A.`, `B.` under `I.`, `II.`.
        self.assertTrue(mb._prefix_fits_level('B', 2))
        self.assertTrue(mb._prefix_fits_level('IV', 1))


if __name__ == '__main__':
    unittest.main()
