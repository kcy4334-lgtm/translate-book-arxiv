# -*- coding: utf-8 -*-
r"""Reading a PDF in order, and knowing whether it worked.

Calibre's PDF path lays text out by position and does not reliably recover
columns. On a two-column journal paper it interleaves them INSIDE a line,
so the output is fluent English fragments in the wrong order. Nothing
downstream sees it: every check in this pipeline compares our artefacts to
each other, and they all agree about scrambled text. The word count, the
character count, the image count and the table count were all correct.

Measured on the paper that found it: 24 of 95 of the paper's own sentences
survived calibre intact, and 92 of 95 survived reading the PDF directly.

The half worth testing hardest is not the extraction, it is the SCORE. It
is what decides, and a score that cannot tell scrambled text from ordered
text would hand the decision to a layout guess, which is what this avoids.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import pdf_text  # noqa: E402


class FakePage(object):
    def __init__(self, text):
        self._text = text

    def get_text(self, _kind='text', **_kw):
        return self._text


class FakeDoc(object):
    """Enough of a PyMuPDF document for the score, with no PyMuPDF."""

    def __init__(self, pages):
        self._pages = [FakePage(p) for p in pages]
        self.page_count = len(self._pages)

    def __getitem__(self, i):
        return self._pages[i]

    def __iter__(self):
        return iter(self._pages)


# Two long sentences per page, which is what the score is built from.
A = ('The tactile array recorded a stable proprioceptive signal while the '
     'hand approached the target object.')
B = ('Recognition accuracy remained above ninety percent under both of the '
     'interfering gas concentrations tested.')
C = ('The fusion of the two modalities tolerated defects in the input far '
     'better than either modality alone did.')


class TheScoreSeparatesOrderedTextFromScrambled(unittest.TestCase):

    def doc(self):
        return FakeDoc(['front matter', 'front matter',
                        A + ' ' + B, C + ' ' + A])

    def test_a_faithful_extraction_scores_full_marks(self):
        doc = self.doc()
        candidate = ' '.join([A, B, C, A])
        hits, total = pdf_text.sentence_fidelity(doc, candidate)
        self.assertTrue(total >= 3, total)
        self.assertEqual(hits, total)

    def test_interleaved_columns_score_near_zero(self):
        r"""The failure this exists for. Every WORD is present and every
        count agrees; only the order is gone, and that is what makes the
        translation unusable while the pipeline reports success."""
        doc = self.doc()
        first, second = A.split(), B.split()
        woven = []
        for i in range(max(len(first), len(second))):
            if i < len(first):
                woven.append(first[i])
            if i < len(second):
                woven.append(second[i])
        hits, total = pdf_text.sentence_fidelity(doc, ' '.join(woven))
        self.assertTrue(total >= 2, total)
        self.assertEqual(hits, 0)

    def test_the_front_matter_is_not_evidence(self):
        """A title page is one column and passes any converter, so counting
        it only dilutes the answer."""
        doc = FakeDoc(['a title page ' + A, 'authors ' + A, C])
        _hits, total = pdf_text.sentence_fidelity(doc, C)
        self.assertEqual(total, 1)

    def test_whitespace_differences_do_not_count_against_it(self):
        doc = self.doc()
        candidate = ' '.join([A, B, C, A]).replace(' ', '\n  ')
        hits, total = pdf_text.sentence_fidelity(doc, candidate)
        self.assertEqual(hits, total)


class WhichSentencesCountAsEvidence(unittest.TestCase):

    def test_a_short_line_is_not_evidence(self):
        """Below sixty characters, boilerplate matches by accident."""
        self.assertEqual(pdf_text.sentences_of('Results. Methods. Fig. 1.'), [])

    def test_a_running_head_is_not_evidence(self):
        for head in ('ARTICLE ' + 'x' * 70,
                     'NATURE COMMUNICATIONS ' + 'y' * 70,
                     'https://doi.org/10.1038/' + 'z' * 60):
            self.assertEqual(pdf_text.sentences_of(head), [], head[:24])

    def test_an_ordinary_sentence_is(self):
        self.assertEqual(pdf_text.sentences_of(A), [A])


class UnwrappingTheLinesAPdfPutsIn(unittest.TestCase):
    r"""A PDF has no paragraphs, only lines. Left alone each becomes its own
    markdown line, the translator works on fragments, and the seams show."""

    def test_a_mid_sentence_break_is_joined(self):
        self.assertEqual(pdf_text.unwrap('the hand approached\nthe target'),
                         'the hand approached the target')

    def test_a_sentence_end_is_left_alone(self):
        text = 'It stopped there.\nThe next paragraph began.'
        self.assertEqual(pdf_text.unwrap(text), text)

    def test_a_heading_is_left_alone(self):
        """A capital after a break is a new line the author meant."""
        text = 'Results\nWe tested eleven objects'
        self.assertEqual(pdf_text.unwrap(text), text)

    def test_a_word_split_across_lines_is_rejoined(self):
        self.assertEqual(pdf_text.unwrap('propriocep-\ntive signal'),
                         'proprioceptive signal')


class TheRepairAbstainsWhenItCannotJudge(unittest.TestCase):
    """It is only for a PDF. An EPUB or DOCX carries its reading order in
    the markup, so there is nothing to measure and nothing to repair, and
    the baseline books go through untouched."""

    def test_a_non_pdf_input_is_left_alone(self):
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        import convert
        self.assertFalse(convert.repair_reading_order(
            'book.epub', 'input.md', 'images'))
        self.assertFalse(convert.repair_reading_order(
            'book.docx', 'input.md', 'images'))

    def test_a_missing_markdown_file_is_left_alone(self):
        import convert
        self.assertFalse(convert.repair_reading_order(
            'paper.pdf', os.path.join(ROOT, 'no-such-input.md'), 'images'))


PAGE_H = 780.0
PAGE_W = 595.0
PAGE_AREA = PAGE_W * PAGE_H


def block(text, bbox=(70, 300, 500, 320), direction=(1.0, 0.0)):
    """A PyMuPDF `get_text('dict')` block, built by hand.

    The real shape, so these tests exercise what the library hands over
    rather than a convenience of their own.
    """
    return {
        'type': 0,
        'bbox': bbox,
        'lines': [{'dir': direction,
                   'spans': [{'text': line, 'font': 'Body', 'size': 9.5}]}
                  for line in text.split('\n')],
    }


TOP = (70, 12, 500, 26)          # y0/height = 0.015: the running-head band
BOTTOM = (70, 752, 500, 766)     # y1/height = 0.982: the footer band
MIDDLE = (70, 300, 500, 320)     # ordinary body position


class FurnitureIsWhatRepeatsInTheMargin(unittest.TestCase):
    """A running head is not recognised by what it says -- the next
    journal's will say something else -- but by saying the same thing in
    the same band on page after page, which body text never does."""

    @staticmethod
    def pages(texts, bbox=BOTTOM):
        return [(PAGE_H, [(bbox, t)]) for t in texts]

    def test_a_footer_on_every_page_is_furniture(self):
        keys = pdf_text.furniture_keys(self.pages(['NATURE COMMS | doi'] * 10))
        self.assertIn(('bottom', 'NATURE COMMS | doi'), keys)

    def test_a_page_number_does_not_make_two_footers(self):
        keys = pdf_text.furniture_keys(
            self.pages(['%d NATURE COMMS | doi' % n for n in range(1, 11)]))
        self.assertIn(('bottom', '# NATURE COMMS | doi'), keys)

    def test_alternating_recto_and_verso_heads_are_both_caught(self):
        """The real layout of the paper that prompted this: one wording on
        the odd pages and another on the even ones, so neither reaches a
        majority and a "most pages" rule keeps one of the two."""
        texts = ['ARTICLE | doi' if n % 2 else 'doi | ARTICLE'
                 for n in range(10)]
        keys = pdf_text.furniture_keys(self.pages(texts, TOP))
        self.assertIn(('top', 'ARTICLE | doi'), keys)
        self.assertIn(('top', 'doi | ARTICLE'), keys)

    def test_a_two_page_document_loses_nothing(self):
        """Three pages of evidence minimum. With two there is no such thing
        as a repetition worth trusting."""
        self.assertEqual(
            pdf_text.furniture_keys(self.pages(['Footer'] * 2)), set())

    def test_a_line_that_appears_once_is_not_furniture(self):
        texts = ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon',
                 'Zeta', 'Eta', 'Theta', 'Iota', 'Kappa']
        self.assertEqual(pdf_text.furniture_keys(self.pages(texts)), set())

    def test_lines_differing_only_by_a_digit_are_one_line(self):
        """Deliberate, and the reason page numbers disappear: the digit in
        `2 NATURE COMMS` is the page, not the content. The cost is that ten
        band blocks differing only by a number collapse into one, so a
        SHORT numbered line in a margin band is furniture here. Captions
        are the case that would hurt, and they are exempted by name before
        this is ever consulted -- see the whole-page tests below."""
        keys = pdf_text.furniture_keys(
            self.pages(['Unique %d' % n for n in range(10)]))
        self.assertIn(('bottom', 'Unique #'), keys)

    def test_a_repeated_line_in_the_body_is_not_furniture(self):
        """Only the margin bands. A sentence repeated in the middle of ten
        pages is the author's business."""
        self.assertEqual(
            pdf_text.furniture_keys(self.pages(['Repeated'] * 10, MIDDLE)),
            set())


class TextRotatedAgainstThePageIsNotProse(unittest.TestCase):
    """Nature Communications prints `1234567890():,;` up the left margin of
    page 1. It arrived in the built book between two paragraphs."""

    def test_text_running_up_the_margin_is_marginalia(self):
        self.assertTrue(pdf_text.is_marginalia(
            block('1234567890():,;', direction=(0.0, -1.0))))

    def test_ordinary_prose_is_not(self):
        self.assertFalse(pdf_text.is_marginalia(block('An ordinary line.')))

    def test_a_block_with_no_lines_is_not(self):
        self.assertFalse(pdf_text.is_marginalia({'bbox': MIDDLE, 'lines': []}))


class TextInsideAFigureIsThatFiguresLabel(unittest.TestCase):
    """Axis labels and panel letters are text drawn on top of the plot.
    Read as prose they cut a sentence in half and put its verb two pages
    later, and that is then what a translator works on."""

    FIGURE = (60, 50, 535, 300)

    def test_a_label_inside_the_figure_is_dropped(self):
        self.assertTrue(pdf_text.is_figure_text(
            (100, 100, 180, 112), [self.FIGURE], PAGE_AREA))

    def test_a_caption_below_the_figure_is_not(self):
        self.assertFalse(pdf_text.is_figure_text(
            (60, 310, 535, 360), [self.FIGURE], PAGE_AREA))

    def test_a_full_page_image_never_removes_the_page(self):
        """A scan or a watermark covers the page, and the text over it IS
        the page. Without this guard the whole document disappears."""
        self.assertFalse(pdf_text.is_figure_text(
            MIDDLE, [(0, 0, PAGE_W, PAGE_H)], PAGE_AREA))

    def test_overlap_is_measured_against_the_block_not_the_figure(self):
        self.assertAlmostEqual(
            pdf_text.overlap_fraction((0, 0, 10, 10), (5, 0, 500, 500)), 0.5)
        self.assertEqual(
            pdf_text.overlap_fraction((0, 0, 10, 10), (50, 50, 60, 60)), 0.0)


class FakePixmap(object):
    def __init__(self, width, height, n, samples):
        self.width, self.height = width, height
        self.n, self.samples = n, samples
        self.alpha = 0


class AnImageWithOneColourCarriesNoInformation(unittest.TestCase):
    """Not a size test. Measured on the paper that prompted this, the dead
    images ran from 18x24 to 301x341 pixels and 104 to 1042 bytes while a
    real figure was 282x238 and 9 KB: every threshold on size or on bytes
    puts at least one of them on the wrong side."""

    def test_a_solid_fill_has_one_colour(self):
        self.assertEqual(
            pdf_text.distinct_colours(FakePixmap(4, 4, 3, b'\xff\x00\x00' * 16)),
            1)

    def test_a_real_image_has_more(self):
        samples = b''.join(bytes((i * 7 % 256, i, 255 - i)) for i in range(16))
        self.assertGreater(
            pdf_text.distinct_colours(FakePixmap(4, 4, 3, samples)), 1)

    def test_two_colours_is_a_silhouette_and_is_kept(self):
        """A line drawing, a 1-bit scan, and this paper's publication date
        set as a bitmap all live here. Only ONE colour is dropped."""
        self.assertEqual(
            pdf_text.distinct_colours(FakePixmap(4, 4, 1, b'\x00\xff' * 8)), 2)

    def test_an_unreadable_pixmap_is_treated_as_real(self):
        """Abstaining keeps the image; guessing deletes a figure."""
        self.assertGreater(
            pdf_text.distinct_colours(FakePixmap(4, 4, 3, b'')), 1)


class SectionsAreMatchedByNameOrNotAtAll(unittest.TestCase):
    """The typographic version was written first and measured: it produced
    222 headings on AlphaQ and 141 on OpenVLA, because those papers draw
    their figures in vector so the axis labels stay in the prose. A line
    reading exactly `References` cannot be imitated by an axis label."""

    def test_a_section_name_on_its_own_line_is_a_heading(self):
        self.assertEqual(pdf_text.section_heading('References'), 'References')
        self.assertEqual(pdf_text.section_heading('Acknowledgements'),
                         'Acknowledgements')

    def test_a_number_or_a_colon_does_not_hide_it(self):
        self.assertEqual(pdf_text.section_heading('4. Methods'), 'Methods')
        self.assertEqual(pdf_text.section_heading('Methods:'), 'Methods')
        self.assertEqual(pdf_text.section_heading('2.1 Related work'),
                         'Related work')

    def test_a_sentence_mentioning_the_word_is_not_a_heading(self):
        self.assertIsNone(pdf_text.section_heading(
            'The methods we used are described below.'))
        self.assertIsNone(pdf_text.section_heading('See the references.'))
        self.assertIsNone(pdf_text.section_heading(''))

    def test_a_name_used_as_a_table_header_is_refused(self):
        """AlphaQ carries a `Method` column header on eight pages. A paper
        has one Methods section."""
        allowed = pdf_text.section_names_used(['Method'] * 8 + ['References'])
        self.assertNotIn('method', allowed)
        self.assertIn('references', allowed)

    def test_a_heading_glued_to_its_paragraph_is_split_off(self):
        """This paper puts `References` and its first entry in one block."""
        pieces = pdf_text.split_sections(
            'References\n1. Rudovic, O. et al. Sci. Robot. 3 (2018).',
            {'references'})
        self.assertEqual(pieces[0], (True, 'References'))
        self.assertFalse(pieces[1][0])
        self.assertIn('Rudovic', pieces[1][1])

    def test_a_name_not_allowed_stays_prose(self):
        pieces = pdf_text.split_sections('Method\n0.51 0.62', set())
        self.assertEqual(len(pieces), 1)
        self.assertFalse(pieces[0][0])


class TheDocumentsOwnPunctuationIsNotMarkup(unittest.TestCase):
    """`# Trials`, `# Modules` and `# LLM layers` are column headers reading
    "number of". Emitted raw they become markdown headings, and on OpenVLA
    they outnumbered the real ones."""

    def test_a_leading_hash_is_escaped(self):
        self.assertEqual(pdf_text.escape_markdown('# Trials'), '\\# Trials')
        self.assertEqual(pdf_text.escape_markdown('a\n## Successes'),
                         'a\n\\## Successes')

    def test_a_hash_inside_a_line_is_left_alone(self):
        self.assertEqual(pdf_text.escape_markdown('run #3 failed'),
                         'run #3 failed')


class WhatComesOutOfAWholePage(unittest.TestCase):
    """The three defects that prompted the rewrite, end to end: a journal
    footer printed ten times between two sentences, a figure's rotated
    y-axis label printed as prose, and a page of blank rectangles."""

    @staticmethod
    def records():
        out = []
        for n in range(6):
            out.append((PAGE_H, PAGE_AREA, [
                block('%d NATURE COMMS | doi' % n, BOTTOM),
                block('Output Voltage (mV)', (100, 100, 180, 112)),
                block('Fig. %d The sensing array in use.' % n,
                      (60, 310, 535, 360)),
                block('The array recorded a stable signal.', MIDDLE),
                block('1234567890():,;', (6, 300, 12, 340), (0.0, -1.0)),
            ], [(60, 50, 535, 300)]))
        return out

    def test_the_furniture_the_labels_and_the_marginalia_all_go(self):
        md, report = pdf_text.render_blocks(self.records())
        self.assertNotIn('NATURE COMMS', md)
        self.assertNotIn('Output Voltage', md)
        self.assertNotIn('1234567890', md)
        self.assertEqual(report['dropped_furniture'], 6)
        self.assertEqual(report['dropped_figure_text'], 6)
        self.assertEqual(report['dropped_marginalia'], 6)

    def test_the_prose_and_the_captions_stay(self):
        md, _report = pdf_text.render_blocks(self.records())
        self.assertIn('The array recorded a stable signal.', md)
        self.assertIn('The sensing array in use.', md)

    def test_a_numbered_caption_in_the_footer_band_survives(self):
        """The case that would hurt: `Figure 3:` and `Figure 7:` normalise
        to one key, they sit in the band on page after page, and every one
        of them is content. The caption exemption is what stops it, so it
        is checked here rather than assumed."""
        pages = [(PAGE_H, PAGE_AREA,
                  [block('Fig. %d Sensitivity of the array.' % n, BOTTOM)], [])
                 for n in range(8)]
        md, report = pdf_text.render_blocks(pages)
        self.assertEqual(report['dropped_furniture'], 0)
        self.assertEqual(md.count('Sensitivity of the array.'), 8)

    def test_a_caption_is_kept_even_where_it_overlaps_its_figure(self):
        """Losing a caption costs more than any axis label is worth, and a
        caption typeset into the figure's own box would otherwise go."""
        md, report = pdf_text.render_blocks(
            [(PAGE_H, PAGE_AREA,
              [block('Fig. 1 Bioinspired sensing.', (100, 100, 400, 120))],
              [(60, 50, 535, 300)])])
        self.assertIn('Bioinspired sensing', md)
        self.assertEqual(report['dropped_figure_text'], 0)


if __name__ == '__main__':
    unittest.main()
