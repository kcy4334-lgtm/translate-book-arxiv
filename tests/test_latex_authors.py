# -*- coding: utf-8 -*-
r"""Eight finished books say "Unknown Author" about papers that name everybody.

The title page takes its author from the source PDF's metadata, and arXiv's
GenPDF routinely leaves `/Author` empty. The names are in flat.tex either way.

This does not parse an author BLOCK — those are free-form LaTeX with a
different convention per class, and half a parse puts a false name on a title
page, which is worse than none (K121's lesson). It recovers names from the
simple forms and REFUSES everything else, and refusing costs nothing: the page
keeps saying what it says today.

Names are read line by line: the first line of an entry is names, and a later
line is names only if every part of it reads as one, so an affiliation, an
address or a note ends the list. Measured over the corpus, every list it gives
names only people on the paper's first page, and gives all of them; of the
papers it used to refuse, attention, AlphaQ, VLA-Adapter, DeeR-VLA and
2609.11801 now read (test_title_block.py), and adam has no author block.
Splitting the whole block on commas,
as it once did, refused Sentence-BERT for a comma in its affiliation and
CafeQ, ViT, BERT, GAN and ResNet for marks and spacing.
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


class BlocksOverSeveralLines(unittest.TestCase):
    """Names over several lines, and affiliations with commas in them."""

    def test_a_comma_in_the_affiliation_does_not_make_an_author(self):
        # Sentence-BERT: refused whole for "Technische Universität Darmstadt".
        self.assertEqual(
            ab.extract_latex_authors(
                '\\author{Nils Reimers and Iryna Gurevych \\\\\n'
                'Ubiquitous Knowledge Processing Lab (UKP-TUDA)\\\\\n'
                'Department of Computer Science, Technische Universit\\"at '
                'Darmstadt\\\\\n\\url{www.ukp.tu-darmstadt.de}}'),
            'Nils Reimers; Iryna Gurevych')

    def test_names_over_centred_lines_with_marks(self):
        # ViT: `$^{*,\dagger}$` and `\vspace{1mm}` refused the whole list.
        block = ('\\author{\n'
                 '\\centerline{Alexey Dosovitskiy$^{*,\\dagger}$, Lucas Beyer$^{*}$,}'
                 ' \\vspace{1mm}\\\\\n'
                 '\\centerline{\\textbf{Xiaohua Zhai$^{*}$, Thomas Unterthiner}}'
                 ' \\vspace{0.5mm} \\\\\n'
                 '\\centerline{$^*$equal technical contribution, $^\\dagger$equal '
                 'advising}  \\vspace{0.7mm} \\\\\n'
                 '\\centerline{Google Research, Brain Team} \\\\\n}')
        self.assertEqual(ab.extract_latex_authors(block),
                         'Alexey Dosovitskiy; Lucas Beyer; Xiaohua Zhai; '
                         'Thomas Unterthiner')

    def test_a_second_line_of_names_is_read(self):
        # CafeQ: seven names over two lines; four were kept.
        self.assertEqual(
            ab.extract_latex_authors(
                '\\author{Ziteng Sun$^\\dag$, Adrian Benton$^\\dag$ \\\\ '
                'Vikas Singh$^\\circ$, Ananda Theertha Suresh$^\\dag$ \\\\ '
                '$^\\dag$ Google: \\{zitengsun\\}@google.com}'),
            'Ziteng Sun; Adrian Benton; Vikas Singh; Ananda Theertha Suresh')

    def test_an_affiliation_with_no_keyword_still_ends_the_names(self):
        self.assertEqual(
            ab.extract_latex_authors('\\author{Ann Lee, Bo Ki \\\\ Brain Team}'),
            'Ann Lee; Bo Ki')


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
