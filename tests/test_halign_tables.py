# -*- coding: utf-8 -*-
r"""A plain-TeX `\halign` table becomes a tabular.

planck builds its eight tables with the A&A template: `\halign` inside
`\setbox\tablebox=\vbox{...}`, printed by `\endPlancktable`. pandoc reads
none of it, and the book had none of the eight.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import halign_tables as ht  # noqa: E402

PLANCK = r'''\begin{table}
\caption{Constraints.}
\label{tab:x}
\setbox\tablebox=\vbox{
 \newdimen\digitwidth
 \setbox0=\hbox{\rm 0}
 \digitwidth=\wd0
 \catcode`*=\active
 \def*{\kern\digitwidth}
 \catcode`!=\active
 \def!{\kern\signwidth}
 \halign{\tabskip=0pt\hbox to 1.75in{#\leaderfil}\tabskip=0.5em&
 \hfil#\hfil&
 \hfil$#$\hfil\tabskip=0pt\cr   % Template goes here.
\noalign{\doubleline}
\omit Data\hfil& \multispan2\hfil Limits\hfil\cr
\noalign{\vskip 3pt\hrule\vskip 5pt}
TT{+}lowP& $< 5.7$& !*1.2\cr
\omit& *30--1197& -0.5\cr
\noalign{\vskip 3pt\hrule\vskip 5pt}
} % close halign
}
\endPlancktable                    % ends one-column \halign
\end{table}
'''


class Converted(unittest.TestCase):

    def setUp(self):
        self.out, self.n = ht.halign_tables(PLANCK)

    def test_one_table(self):
        self.assertEqual(self.n, 1)
        self.assertNotIn('\\halign{', self.out)
        self.assertNotIn('\\setbox', self.out)
        self.assertNotIn('\\endPlancktable', self.out)

    def test_the_template_gives_the_columns(self):
        self.assertIn('\\begin{tabular}{lcc}', self.out)

    def test_rows_rules_and_spans(self):
        self.assertIn('\\hline\n\\hline\nData & \\multicolumn{2}{c}{Limits} \\\\\n'
                      '\\hline\n', self.out)
        self.assertIn('TT{+}lowP & $< 5.7$ & $1.2$ \\\\', self.out)

    def test_alignment_characters_go_and_omit_drops_the_template(self):
        self.assertIn(' & 30--1197 & $-0.5$ \\\\', self.out)
        self.assertNotIn('*', self.out.split('\\begin{tabular}')[1])

    def test_caption_and_label_stay(self):
        self.assertIn('\\caption{Constraints.}\n\\label{tab:x}', self.out)


class LeftAlone(unittest.TestCase):

    def test_a_symbol_macro_built_with_halign(self):
        # planck's `\ga`: `>` over `\sim`, a template of `##` in a definition.
        tex = ('\\newcommand{\\ga}{\\mathrel{\\mathchoice {\\vcenter{'
               '\\offinterlineskip\\halign{\\hfil $\\displaystyle##$\\hfil\\cr'
               '>\\cr\\sim\\cr}}}}}')
        self.assertEqual(ht.halign_tables(tex), (tex, 0))


if __name__ == '__main__':
    unittest.main()
