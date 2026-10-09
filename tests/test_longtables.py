# -*- coding: utf-8 -*-
r"""A longtable becomes a `table` float holding a `tabular`.

PaLM's datasheet is a longtable with lists in five cells. pandoc read it into
a 50,000-character grid table, the chunker cut that into four, and the book
printed four tables where the paper has one; every table after it was then
compared with the wrong source table.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

PALM = ('Text.\n\\begin{longtable}[c]{ p{.32\\textwidth} | p{.62\\textwidth} }\n'
        '\\toprule\n\\multicolumn{2}{c}{\\textbf{Motivation}} \\\\ \\toprule\n'
        'Q1? & A \\begin{itemize}\\item x\\item y\\end{itemize} \\\\ \\midrule\n'
        'Q2? & No. \\\\\n\\bottomrule\n\\caption{{{PaLM}} Datasheet}\n'
        '\\label{tab:datasheet}\n\\end{longtable}\nAfter.')


class LongtablesAsFloats(unittest.TestCase):

    def test_palm_datasheet(self):
        out, n = ab.longtables_as_floats(PALM)
        self.assertEqual(n, 1)
        self.assertNotIn('longtable', out)
        self.assertIn('\\begin{table}', out)
        self.assertIn('\\begin{tabular}{ p{.32\\textwidth} | p{.62\\textwidth} }',
                      out)
        # Below the rows, where the paper wrote it, and outside the tabular.
        self.assertLess(out.index('\\end{tabular}'), out.index('\\caption'))
        self.assertIn('\\caption{{{PaLM}} Datasheet}\\label{tab:datasheet}', out)
        self.assertIn('\\begin{itemize}\\item x', out)
        self.assertTrue(out.startswith('Text.\n') and out.endswith('After.'))

    def test_a_caption_first_goes_above(self):
        tex = ('\\begin{longtable}{ll}\\caption{Top}\\label{t:x}\\\\\n'
               'a & b \\\\\n\\end{longtable}')
        out, _n = ab.longtables_as_floats(tex)
        self.assertLess(out.index('\\caption{Top}'), out.index('\\begin{tabular}'))
        self.assertNotIn('\\label{t:x}\\\\', out)

    def test_repeated_heads_and_feet_are_dropped(self):
        tex = ('\\begin{longtable}{ll}\nH1 & H2 \\\\ \\endfirsthead\n'
               'H1 (cont.) & H2 \\\\ \\endhead\nmore \\\\ \\endfoot\n'
               'last \\\\ \\endlastfoot\nr1 & 1 \\\\\nr2 & 2 \\\\\n'
               '\\end{longtable}')
        out, _n = ab.longtables_as_floats(tex)
        self.assertIn('H1 & H2', out)
        self.assertNotIn('cont.', out)
        self.assertNotIn('more', out)
        self.assertLess(out.index('r2 & 2'), out.index('last'))
        self.assertNotRegex(out, r'\\end(first)?head|\\end(last)?foot')

    def test_numbering_still_sees_one_table(self):
        import numbering
        out, _n = ab.longtables_as_floats(PALM)
        self.assertEqual([u['kind'] for u in numbering.float_units(out)],
                         ['table'])


if __name__ == '__main__':
    unittest.main()
