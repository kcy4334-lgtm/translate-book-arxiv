# -*- coding: utf-8 -*-
r"""The title page names the authors with their marks, their affiliations,
and what a mark means.

pandoc reads `\author{}` as metadata and drops it, and the title page was
built from the names alone, so seven corpus papers lost every affiliation:
VAE, BERT, ResNet, Neural ODE, spectre, DeeR-VLA and 2609.11801, whose
affiliations an agent then typed in by hand. Five more had no names at all
(attention, AlphaQ, DeeR-VLA, VLA-Adapter, 2609.11801): `{\L}ukasz`, a
`\enspace` or `~~~` between names, an affiliation spaced with `\quad` like
the names, a class's own `\authorlist`.

The blocks below are cut down from those papers' flat.tex.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402
import merge_and_build as mb  # noqa: E402

BS = chr(92)
NL = BS + BS


def author(body):
    return BS + 'author{' + body + '}\n' + BS + 'begin{document}'


class NamesTheParserUsedToRefuse(unittest.TestCase):

    def test_a_tex_letter_in_a_name(self):
        tex = author('{' + BS + 'L}ukasz Kaiser ' + BS + 'And Illia Polosukhin')
        self.assertEqual(ab.extract_latex_authors(tex),
                         'Łukasz Kaiser; Illia Polosukhin')

    def test_accents_in_their_braced_and_bare_spellings(self):
        self.assertEqual(
            ab.tex_letters_to_unicode(BS + 'textbf{' + BS + '.{I}smail} '
                                      'Schr' + BS + '"odinger {' + BS + "'e}"),
            BS + 'textbf{İsmail} Schrödinger é')

    def test_names_spaced_by_tildes_or_enspace(self):
        tex = author('Yang Yue$^{*' + BS + ',1}$ ~~~ Bingyi Kang$^2$ ~~~~'
                     + NL + ' $^1$ Tsinghua University ~~~ $^2$ ByteDance')
        self.assertEqual(ab.extract_latex_authors(tex), 'Yang Yue; Bingyi Kang')
        tex = author('{' + BS + 'bf Wanqi Yang}' + BS + 'textsuperscript{1}'
                     + BS + 'enspace {' + BS + 'bf Yuexiao Ma}'
                     + BS + 'textsuperscript{2}')
        self.assertEqual(ab.extract_latex_authors(tex), 'Wanqi Yang; Yuexiao Ma')

    def test_an_affiliation_spaced_like_the_names_is_not_a_name(self):
        tex = author('Ru Zhang$^{1}$ ' + BS + 'quad Jianyi Liu$^{2}$' + NL
                     + '$^{1}$Westlake University ' + BS + 'quad '
                     + '$^{2}$State Key Laboratory of Networking and '
                     'Switching Technology' + NL)
        self.assertEqual(ab.extract_latex_authors(tex), 'Ru Zhang; Jianyi Liu')
        block = ab.read_title_block(tex)
        self.assertEqual(block['affiliations'], [
            ('1', 'Westlake University'),
            ('2', 'State Key Laboratory of Networking and Switching '
                  'Technology')])


class MarkedAffiliations(unittest.TestCase):

    def test_marks_tie_names_to_affiliations(self):
        tex = author('{' + BS + 'rm Paul Kocher}$^1$, {' + BS + 'rm Daniel '
                     'Gruss}$^2$' + NL + '$^1$ Independent' + NL
                     + '%' + BS + 'textsf{' + BS + '{' + BS + 'href{x}}\n'
                     + '$^2$ Graz University of Technology' + NL)
        self.assertEqual(ab.read_title_block(tex), {
            'authors': [('Paul Kocher', ['1']), ('Daniel Gruss', ['2'])],
            'affiliations': [('1', 'Independent'),
                             ('2', 'Graz University of Technology')],
            'notes': []})

    def test_a_commented_brace_does_not_carry_the_block_on(self):
        """spectre: a commented-out `\\{\\href{` ran the brace count on
        through `\\title{}` and the abstract."""
        tex = (BS + 'author{A Person$^1$' + NL + '$^1$ Lab Name' + NL
               + '%' + BS + 'textsf{' + BS + '{' + BS + 'href{a}{b}}\n'
               + '}\n' + BS + 'title{The Title}\nAbstract words.')
        block = ab.read_title_block(tex)
        self.assertEqual(block['affiliations'], [('1', 'Lab Name')])

    def test_a_note_says_what_a_mark_means(self):
        tex = author(BS + 'centerline{Alexey Dosovitskiy$^{*,' + BS
                     + 'dagger}$, Lucas Beyer$^{*}$}' + NL + BS
                     + 'centerline{$^*$equal technical contribution, '
                     '$^' + BS + 'dagger$equal advising}' + NL + BS
                     + 'centerline{Google Research, Brain Team}' + NL)
        block = ab.read_title_block(tex)
        self.assertEqual(block['authors'][0], ('Alexey Dosovitskiy', ['*,†']))
        self.assertEqual(block['notes'],
                         ['*equal technical contribution, †equal advising'])
        self.assertEqual(block['affiliations'],
                         [('', 'Google Research, Brain Team')])

    def test_a_class_author_list(self):
        """2609.11801 fills muxlab's `\\authorlist` and `\\affiliationlist`."""
        tex = (BS + 'renewcommand{' + BS + 'authorlist}{%\n {' + BS
               + 'sffamily' + BS + 'color{muxfg}%\n ' + BS
               + 'textbf{Ayhan Suleymanzade}' + BS + 'textsuperscript{1,$*$},'
               + BS + ';' + BS + ';\n ' + BS + 'textbf{Chanhyuk Lee}' + BS
               + 'textsuperscript{2}%\n }' + NL + '[2pt]%\n {' + BS
               + 'textbf{' + BS + '.{I}smail Ceylan}' + BS
               + 'textsuperscript{3,' + BS + 'dag}}%\n}\n'
               + BS + 'renewcommand{' + BS + 'affiliationlist}{%\n {' + BS
               + 'small' + BS + 'textsuperscript{1}EPFL' + BS + 'quad '
               + BS + 'textsuperscript{2}KAIST}' + NL + '[1pt]%\n {' + BS
               + 'small' + BS + 'textsuperscript{3}University of Oxford}%\n}\n')
        block = ab.read_title_block(tex)
        self.assertEqual(block['authors'], [
            ('Ayhan Suleymanzade', ['1,*']), ('Chanhyuk Lee', ['2']),
            ('İsmail Ceylan', ['3,†'])])
        self.assertEqual(block['affiliations'], [
            ('1', 'EPFL'), ('2', 'KAIST'), ('3', 'University of Oxford')])


class UnmarkedAffiliations(unittest.TestCase):

    def test_one_shared_affiliation_takes_no_numbers(self):
        tex = author('Jacob Devlin ' + BS + 'quad Kenton Lee' + NL
                     + 'Google AI Language' + NL + '{' + BS + 'tt ' + BS
                     + '{jacobdevlin,kentonl' + BS + '}@google.com}')
        block = ab.read_title_block(tex)
        self.assertEqual(block['authors'],
                         [('Jacob Devlin', []), ('Kenton Lee', [])])
        self.assertEqual(block['affiliations'], [('', 'Google AI Language')])

    def test_lines_under_one_name_are_one_affiliation(self):
        tex = author('Diederik P. Kingma' + NL + 'Machine Learning Group' + NL
                     + 'Universiteit van Amsterdam' + NL + BS
                     + 'texttt{dpkingma@gmail.com}')
        block = ab.read_title_block(tex)
        self.assertEqual(block['affiliations'], [
            ('', 'Machine Learning Group, Universiteit van Amsterdam')])

    def test_different_affiliations_are_numbered(self):
        """Attention writes each author's affiliation under the name."""
        tex = author('Ashish Vaswani' + NL + 'Google Brain' + NL + BS
                     + 'texttt{a@google.com} ' + BS + 'And Aidan N. Gomez'
                     + BS + 'hspace{1.7mm}' + BS + 'thanks{Work performed '
                     'while at Google Brain.}' + NL + 'University of Toronto'
                     + NL + BS + 'texttt{aidan@cs.toronto.edu}')
        block = ab.read_title_block(tex)
        self.assertEqual(block['authors'], [('Ashish Vaswani', ['1']),
                                            ('Aidan N. Gomez', ['2'])])
        self.assertEqual(block['affiliations'], [
            ('1', 'Google Brain'), ('2', 'University of Toronto')])

    def test_a_project_page_or_a_dedication_is_not_an_affiliation(self):
        tex = author('Jane Roe' + NL + 'Some University' + NL
                     + 'https://project.github.io/' + NL + 'www.lab.de')
        self.assertEqual(ab.read_title_block(tex)['affiliations'],
                         [('', 'Some University')])


class TitlePage(unittest.TestCase):

    BLOCK = {'authors': [('Ann Lee', ['1,*']), ('Bo Kim', ['2'])],
             'affiliations': [('1', 'EPFL'), ('2', 'KAIST')],
             'notes': ['*equal contribution']}

    def test_the_names_carry_their_marks(self):
        self.assertEqual(mb.marked_byline(self.BLOCK),
                         'Ann&nbsp;Lee<sup>1,*</sup>, Bo&nbsp;Kim<sup>2</sup>')

    def test_marks_with_nothing_to_point_at_are_left_off(self):
        block = {'authors': [('Ann Lee', ['1'])], 'affiliations': [],
                 'notes': []}
        self.assertEqual(mb.marked_byline(block), 'Ann&nbsp;Lee')

    def test_affiliations_and_notes_are_on_the_page(self):
        page = mb.build_title_page('A Title', 'arXiv:1', self.BLOCK)
        self.assertIn('<p class="title-page-affiliations"><sup>1</sup>EPFL · '
                      '<sup>2</sup>KAIST</p>', page)
        self.assertIn('<p class="title-page-notes">*equal contribution</p>',
                      page)
        self.assertLess(page.index('affiliations'), page.index('arXiv:1'))

    def test_without_a_block_the_page_is_as_before(self):
        self.assertNotIn('affiliations', mb.build_title_page('T', 'arXiv:1'))


if __name__ == '__main__':
    unittest.main()
