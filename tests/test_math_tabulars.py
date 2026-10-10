# -*- coding: utf-8 -*-
r"""A tabular inside a formula becomes an array.

planck lists results as a brace over a two-column tabular inside an
`equation`. The table expander turned all seven into HTML tables in the
middle of `$$...$$`, the HTML writer dropped them, and the build stopped.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import math_tabulars as mt  # noqa: E402
import merge_and_build as mb  # noqa: E402

PLANCK = ('The bounds are\n\\begin{equation}\n\\omega_\\mathrm{b} =\n\\left\\{\n'
          '\\mathrm{\n\\begin{tabular}{ll}\n'
          '$0.02222^{+0.00045}_{-0.00043}$ & \\textit{Planck}\\ {\\rm TT}{+}{\\rm lowP}, \\\\\n'
          '$0.02226^{+0.00040}_{-0.00039}$ & \\datalabel{\\planckTTBAO}, \\\\\n'
          '\\end{tabular}\n}\n\\right.\n\\end{equation}\nand more.\n')


class InsideAFormula(unittest.TestCase):

    def test_the_tabular_becomes_an_array_and_its_wrapper_goes(self):
        out, n = mt.tabulars_in_math_as_arrays(PLANCK)
        self.assertEqual(n, 1)
        self.assertNotIn('tabular', out)
        self.assertNotIn('\\mathrm{\n', out)
        self.assertIn('\\begin{array}{ll}0.02222^{+0.00045}_{-0.00043} & ', out)
        self.assertIn('\\textit{Planck}\\ \\text{TT}\\text{+}\\text{lowP}'
                      '\\text{,}', out)
        self.assertIn('\\datalabel{\\planckTTBAO} \\text{,}', out)
        self.assertIn('\\end{array}\n\\right.', out)

    def test_a_starred_tabular_loses_its_width(self):
        tex = ('$$x = \\begin{tabular*}{5cm}{ll} $a$ & b \\\\ \\end{tabular*}$$')
        out, n = mt.tabulars_in_math_as_arrays(tex)
        self.assertEqual(n, 1)
        self.assertIn('\\begin{array}{ll}a & \\text{b}\\end{array}', out)

    def test_a_line_break_spacing_is_not_a_display(self):
        # 2609.11801: `\\[2pt]` in the author block, then a results table.
        tex = ('Authors\\\\[2pt] names.\n\\begin{table}\\begin{tabular}{ll}'
               'a & b \\\\ \\end{tabular}\\end{table} and later x \\] y')
        self.assertEqual(mt.tabulars_in_math_as_arrays(tex), (tex, 0))

    def test_a_tabular_in_prose_is_left(self):
        tex = 'text \\begin{tabular}{ll} a & b \\\\ \\end{tabular} more'
        self.assertEqual(mt.tabulars_in_math_as_arrays(tex), (tex, 0))

    def test_widths_and_spacing_leave_the_column_letters(self):
        self.assertEqual(mt._array_spec('@{}p{2cm}|c@{\\hspace{1em}}r'), 'l|cr')

    def test_escapes_stay_escaped_in_text(self):
        self.assertEqual(mt._cell_as_math(' 95\\% CL '), '\\text{95\\% CL}')

    @unittest.skipUnless(mb.resolve_pandoc(), 'needs pandoc')
    def test_texmath_reads_the_result(self):
        out, _n = mt.tabulars_in_math_as_arrays(
            PLANCK.replace('\\datalabel{\\planckTTBAO}', 'BAO'))
        start = out.index('\\begin{equation}')
        stop = out.index('\\end{equation}') + len('\\end{equation}')
        proc = subprocess.run(
            [mb.resolve_pandoc(), '--from', 'markdown', '--to', 'html5',
             '--mathml'], input='$$' + out[start:stop] + '$$\n',
            capture_output=True, text=True, encoding='utf-8')
        self.assertNotIn('Could not convert', proc.stderr)
        self.assertIn('<mtable>', proc.stdout)


if __name__ == '__main__':
    unittest.main()
