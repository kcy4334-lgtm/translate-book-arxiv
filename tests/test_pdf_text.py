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


if __name__ == '__main__':
    unittest.main()
