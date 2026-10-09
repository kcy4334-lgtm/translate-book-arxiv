# -*- coding: utf-8 -*-
r"""Floats written between the reference list and the next section.

VAE puts Figures 4 and 5 after `\appendix` and before
`\section{Visualisations}`. LaTeX set them after that section's opening
paragraph; pandoc kept source order, and the book printed both figures
between the last reference and appendix A.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

FIG4 = '\\begin{figure}[t]\n\\includegraphics{a}\n\\caption{Four}\n\\end{figure}'
FIG5 = '\\begin{figure}[h]\n\\includegraphics{b}\n\\caption{Five}\n\\end{figure}'
VAE = ('\\begin{thebibliography}{X}\n\\bibitem{a} A.\n\\end{thebibliography}\n'
       '\\bibliographystyle{alpha} %\n\n\\appendix\n' + FIG4 + '\n\n' + FIG5
       + '\n\n\\section{Visualisations}\n\\label{ap:vis}\n'
       'See figures 4 and 5.\n\n\\section{Solution}\nText.\n')


class FloatsOutOfReferences(unittest.TestCase):

    def test_vae_figures_follow_the_first_paragraph(self):
        out, n = ab.floats_out_of_references(VAE)
        self.assertEqual(n, 2)
        self.assertLess(out.index('See figures 4 and 5.'), out.index('Four'))
        self.assertLess(out.index('Four'), out.index('Five'))
        self.assertLess(out.index('Five'), out.index('\\section{Solution}'))
        self.assertLess(out.index('\\appendix'), out.index('\\section{Vis'))
        self.assertEqual(out.count('\\begin{figure}'), 2)

    def test_a_gap_holding_text_is_left(self):
        tex = VAE.replace('\\appendix\n', '\\appendix\nSome words.\n')
        self.assertEqual(ab.floats_out_of_references(tex), (tex, 0))

    def test_no_floats_no_change(self):
        tex = ('\\end{thebibliography}\n\\appendix\n\\section{A}\nText.\n')
        self.assertEqual(ab.floats_out_of_references(tex), (tex, 0))

    def test_floats_with_no_section_after_them_stay(self):
        tex = '\\end{thebibliography}\n' + FIG4 + '\n\\end{document}\n'
        self.assertEqual(ab.floats_out_of_references(tex), (tex, 0))

    def test_a_section_opening_on_a_subsection_takes_them_after_its_heading(self):
        tex = ('\\bibliography{refs}\n' + FIG4 + '\n\\section{App}\n'
               '\\subsection{First}\nText.\n')
        out, n = ab.floats_out_of_references(tex)
        self.assertEqual(n, 1)
        self.assertLess(out.index('\\section{App}'), out.index('Four'))
        self.assertLess(out.index('Four'), out.index('\\subsection{First}'))

    def test_floats_before_the_references_are_not_touched(self):
        tex = (FIG4 + '\n\\section{Body}\nText.\n\\bibliography{refs}\n'
               '\\section{App}\nMore.\n')
        self.assertEqual(ab.floats_out_of_references(tex), (tex, 0))


if __name__ == '__main__':
    unittest.main()
