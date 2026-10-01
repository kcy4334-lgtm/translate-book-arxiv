# -*- coding: utf-8 -*-
r"""Five failures found by putting ten well-cited papers through the front end.

Three papers never reached the translator at all, and each failed differently:

* Adam's arXiv "source" is 298 bytes whose body is `\includepdf` — a finished
  PDF in a LaTeX envelope. The backend converted it to 43 characters and
  reported "Conversion completed successfully!". Worse, `input.md` is reused,
  so that 43-character document would have been picked up as already
  converted by every later run.
* ResNet died on `\newcolumntype{x}[1]{>{\centering}p{#1pt}}` and fell back to
  calibre, which cannot recover an equation — while `--backend arxiv` had been
  asked for explicitly, and that is documented to fail loudly instead.
* Planck and a random-matrix survey died on `\def` with delimited parameters
  (`\def\tablenote#1 #2\par{...}`) and on a `\def` of a control SYMBOL
  (`\def \< {\langle}`), which is how maths papers shorten notation.

Two of the ten have no LaTeX source on arXiv at all. That is not a defect —
it is a fact about the corpus, and the right behaviour is to say so.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

WRAPPER = ('\\documentclass{article}\n\\usepackage{pdfpages}\n'
           '\\begin{document}\n\\includepdf[pages=1-last]{main.pdf}\n'
           '\\end{document}\n')
REAL = ('\\begin{document}\n\\section{Introduction}\n' + ('word ' * 300) +
        '\n\\end{document}\n')


class NoBody(unittest.TestCase):

    def test_an_includepdf_envelope_is_named_as_such(self):
        why = ab.no_latex_body(WRAPPER, '\\includepdf[pages=1-last]{main.pdf}')
        self.assertIn('includepdf', why)

    def test_a_conversion_that_produced_nothing_is_refused(self):
        self.assertTrue(ab.no_latex_body(REAL, '   \n  \n'))

    def test_a_real_paper_passes(self):
        self.assertEqual(ab.no_latex_body(REAL, 'word ' * 300), '')

    def test_includepdf_outside_the_document_body_is_not_the_test(self):
        """A preamble may load pdfpages without the paper being a wrapper."""
        tex = ('\\usepackage{pdfpages}\n\\begin{document}\n'
               + ('word ' * 300) + '\n\\end{document}\n')
        self.assertEqual(ab.no_latex_body(tex, 'word ' * 300), '')


class TexDefs(unittest.TestCase):

    def clean(self, tex):
        return ab.neutralize_tex_defs(tex)

    def test_a_delimited_parameter_def_goes(self):
        got, n = self.clean('\\def\\tablenote#1 #2\\par{\\begingroup x}\nbody\n')
        self.assertEqual(n, 1)
        self.assertNotIn('tablenote', got)
        self.assertIn('body', got)

    def test_a_control_symbol_def_goes_whatever_follows_it(self):
        got, n = self.clean('\\def \\< {\\langle}\nbody\n')
        self.assertEqual(n, 1)
        self.assertNotIn('langle', got)

    def test_a_plain_parameter_def_is_left_for_pandoc_to_expand(self):
        tex = '\\def\\vect#1{\\mathbf{#1}}\n'
        self.assertEqual(self.clean(tex), (tex, 0))

    def test_a_def_with_no_parameters_is_left_alone(self):
        tex = '\\def\\R{\\mathbb{R}}\n'
        self.assertEqual(self.clean(tex), (tex, 0))

    def test_a_long_def_is_recognised(self):
        _got, n = self.clean('\\long\\def\\note#1 #2\\par{x}\n')
        self.assertEqual(n, 1)

    def test_the_body_is_taken_whole_including_nested_braces(self):
        got, _n = self.clean('\\def\\a#1 #2\\par{x{y{z}}}\nafter\n')
        self.assertNotIn('y{z}', got)
        self.assertIn('after', got)


class ColumnTypes(unittest.TestCase):

    def test_the_definition_goes(self):
        got, n = ab.neutralize_newcolumntype(
            '\\newcolumntype{x}[1]{>{\\centering}p{#1pt}}\ntext\n')
        self.assertEqual(n, 1)
        self.assertNotIn('newcolumntype', got)

    def test_a_use_becomes_a_plain_column(self):
        got, _n = ab.neutralize_newcolumntype(
            '\\newcolumntype{x}[1]{>{\\centering}p{#1pt}}\n'
            '\\begin{tabular}{|x{20}|x{30}|}\na & b \\\\\n\\end{tabular}\n')
        self.assertIn('{|c|c|}', got)

    def test_the_column_count_survives(self):
        got, _n = ab.neutralize_newcolumntype(
            '\\newcolumntype{y}{c}\n\\begin{tabular}{lyy}\nx\n\\end{tabular}\n')
        self.assertIn('{lcc}', got)

    def test_a_document_with_none_is_untouched(self):
        tex = '\\begin{tabular}{lcc}\nx\n\\end{tabular}\n'
        self.assertEqual(ab.neutralize_newcolumntype(tex), (tex, 0))


if __name__ == '__main__':
    unittest.main()
