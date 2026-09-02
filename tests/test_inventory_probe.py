# -*- coding: utf-8 -*-
r"""Tests for the source-inventory probe.

Every other check in this pipeline compares two things the pipeline made,
so it can only see a disagreement between stages. It is blind by
construction to what is missing from every stage at once — and that is the
shape most of the real defects have had. CafeQ shipped 61 references in
`output.md` and none in the book while every count agreed with every other,
because nothing counted references at all.

This probe starts from the source instead. It reports only TOTAL absence:
counts in LaTeX and counts in HTML do not line up (a three-panel float is
one environment and three `<figure>` elements), and reading that difference
as a shortfall is how a check earns a reputation for crying wolf. What does
not vary is zero.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inventory_probe as ip

SOURCE = (r'\author{Ada Lovelace, Alan Turing}' '\n'
          r'\begin{figure}\caption{One}\end{figure}' '\n'
          r'\begin{table}\caption{Two}\end{table}' '\n'
          r'\begin{algorithm}\caption{Three}\end{algorithm}' '\n'
          r'\begin{equation}x=1\end{equation}' '\n'
          r'Body text.\footnote{A real note.}' '\n'
          r'\cite{knuth1984}' '\n'
          r'\bibitem[Knuth(1984)]{knuth1984} D. Knuth.' '\n')

COMPLETE = ('<p class="byline">Ada Lovelace, Alan Turing</p>'
            '<figure><img src="a.png"></figure>'
            '<table><tr><td>x</td></tr></table>'
            '<div class="algorithm"><p>step</p></div>'
            '<math display="block"></math>'
            '<section class="footnotes"><li id="fn1">note</li></section>'
            '<h1>참고문헌</h1><p>D. Knuth.</p>')


class SourceSide(unittest.TestCase):

    def test_counts_what_the_paper_is_made_of(self):
        got = ip.source_inventory(SOURCE)
        self.assertEqual(got['figures'], 1)
        self.assertEqual(got['tables'], 1)
        self.assertEqual(got['algorithms'], 1)
        self.assertEqual(got['numbered equations'], 1)
        self.assertEqual(got['footnotes'], 1)
        self.assertEqual(got['bibliography entries'], 1)
        self.assertEqual(got['works cited'], 1)

    def test_a_macro_definition_is_not_a_footnote(self):
        # `\footnote{#1}` is the command being defined, not used. Counting
        # CafeQ's two definitions said the book had lost two footnotes it
        # never had.
        tex = r'\newcommand{\note}[1]{\footnote{#1}}' '\n' r'x\footnote{real}'
        self.assertEqual(ip._count_footnotes(tex), 1)

    def test_author_detection_survives_every_spelling(self):
        for tex in (r'\author{A. Person}',
                    r'\icmlauthor{A. Person}{lab}',
                    r'\author{{\bf A. Person}\textsuperscript{1}}'):
            self.assertTrue(ip.names_authors(tex), tex)
        self.assertFalse(ip.names_authors(r'\title{No one}'))


class BothDirections(unittest.TestCase):

    def build(self, html):
        temp = tempfile.mkdtemp(prefix='tb-inv-')
        with open(os.path.join(temp, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(SOURCE)
        with open(os.path.join(temp, 'book_doc.html'), 'w',
                  encoding='utf-8') as fh:
            fh.write(html)
        return temp

    def run_probe(self, html):
        temp = self.build(html)
        try:
            return ip.probe(temp, 'ko', strict=True)
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def test_silent_when_the_page_has_everything(self):
        self.assertEqual(self.run_probe(COMPLETE), 0)

    def test_speaks_up_when_the_reference_list_is_gone(self):
        self.assertEqual(
            self.run_probe(COMPLETE.replace('<h1>참고문헌</h1><p>D. Knuth.</p>',
                                            '')), 1)

    def test_speaks_up_when_the_algorithm_is_gone(self):
        self.assertEqual(
            self.run_probe(COMPLETE.replace(
                '<div class="algorithm"><p>step</p></div>', '')), 1)

    def test_speaks_up_when_the_book_names_no_one(self):
        self.assertEqual(
            self.run_probe(COMPLETE.replace(
                '<p class="byline">Ada Lovelace, Alan Turing</p>', '')), 1)

    def test_a_count_that_differs_is_not_a_finding(self):
        # One figure environment, three rendered panels. Legitimate.
        more = COMPLETE.replace('<figure><img src="a.png"></figure>',
                                '<figure><img src="a.png"></figure>' * 3)
        self.assertEqual(self.run_probe(more), 0)


if __name__ == '__main__':
    unittest.main()
