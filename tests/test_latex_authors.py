# -*- coding: utf-8 -*-
r"""Eight finished books say "Unknown Author" about papers that name everybody.

The title page takes its author from the source PDF's metadata, and arXiv's
GenPDF routinely leaves `/Author` empty. The names are in flat.tex either way.

This does not parse an author BLOCK — those are free-form LaTeX with a
different convention per class, and half a parse puts a false name on a title
page, which is worse than none (K121's lesson). It recovers names from the
simple forms and REFUSES everything else, and refusing costs nothing: the page
keeps saying what it says today.

Measured over the corpus, it accepts maynard, shor, unet, SINQ and planck, and
refuses gan (a name glued to its affiliation), gpt3 ("OpenAI" as the 32nd
author), spectre (271 fragments), attention, bert, ddpm, resnet, AlphaQ and
DeeR-VLA.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402


class SimpleFormsAreRead(unittest.TestCase):
    def test_one_author(self):
        self.assertEqual(ab.extract_latex_authors(r'\author{James Maynard}'),
                         'James Maynard')

    def test_and_separated(self):
        self.assertEqual(
            ab.extract_latex_authors(
                r'\author{Olaf Ronneberger \and Philipp Fischer \and Thomas Brox}'),
            'Olaf Ronneberger; Philipp Fischer; Thomas Brox')

    def test_comma_separated(self):
        self.assertEqual(ab.extract_latex_authors(r'\author{A Bee, C Dee}'),
                         'A Bee; C Dee')

    def test_a_thanks_note_comes_off(self):
        self.assertEqual(
            ab.extract_latex_authors(
                r'\author{Peter W. Shor\thanks{AT\&T Research, Room 2D-149}}'),
            'Peter W. Shor')

    def test_a_superscript_mark_comes_off(self):
        self.assertEqual(
            ab.extract_latex_authors(
                r'\author{Ann Lee\textsuperscript{1,2} \and Bo Ki\textsuperscript{3}}'),
            'Ann Lee; Bo Ki')

    def test_a_bracketed_footnotemark_comes_off(self):
        self.assertEqual(
            ab.extract_latex_authors(
                r'\author{Tom Brown \and Ben Mann\footnotemark[1]}'),
            'Tom Brown; Ben Mann')

    def test_the_icml_list_is_preferred(self):
        self.assertEqual(
            ab.extract_latex_authors(
                r'\author{ignored}' '\n'
                r'\icmlauthor{Lorenz K. Muller}{comp}' '\n'
                r'\icmlauthor{Philippe Bich}{comp}'),
            'Lorenz K. Muller; Philippe Bich')

    def test_a_duplicate_name_appears_once(self):
        self.assertEqual(ab.extract_latex_authors(r'\author{A Bee \and A Bee}'),
                         'A Bee')


class AnythingUncertainIsRefused(unittest.TestCase):
    def test_no_author_command(self):
        self.assertEqual(ab.extract_latex_authors(r'\title{Only a title}'), '')

    def test_an_institution_among_the_names(self):
        # gpt3 ends its list with "OpenAI".
        self.assertEqual(
            ab.extract_latex_authors(r'\author{Tom Brown \and OpenAI}'), '')

    def test_a_name_glued_to_its_affiliation(self):
        # gan: "Yoshua Bengio D\'epartement d'informatique ..."
        self.assertEqual(
            ab.extract_latex_authors(
                r'\author{Ian Goodfellow \and Yoshua Bengio Universite de Montreal}'),
            '')

    def test_an_email_address(self):
        self.assertEqual(
            ab.extract_latex_authors(r'\author{A Bee \and a@example.com}'), '')

    def test_an_affiliation_line_after_the_name_is_dropped(self):
        # The name is the first line of the entry; `\\` starts the rest.
        self.assertEqual(
            ab.extract_latex_authors(
                '\\author{Ashish Vaswani\\\\ Google Brain\\\\ av@google.com}'),
            'Ashish Vaswani')

    def test_a_commented_out_author_is_ignored(self):
        self.assertEqual(
            ab.extract_latex_authors(
                '\\author{%% Ghost Writer\nReal Name}'),
            'Real Name')

    def test_an_empty_block(self):
        self.assertEqual(ab.extract_latex_authors(r'\author{}'), '')

    def test_no_text_at_all(self):
        self.assertEqual(ab.extract_latex_authors(''), '')
        self.assertEqual(ab.extract_latex_authors(None), '')


if __name__ == '__main__':
    unittest.main()
