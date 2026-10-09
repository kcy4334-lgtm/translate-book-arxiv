# -*- coding: utf-8 -*-
r"""The table finder opens and closes the same environments.

latex_tables.py defined `_TABULAR_BEGIN_RE` twice, and the second, wider one
-- written for rewriting preambles, and including `array`, `longtable` and
`tabularx` -- replaced the first. The finder then opened on a `tabularx` or
on the `array` inside a displayed formula, looked for `\end{tabular}` to
close it, found none, and stopped. ViT's tabularx Table 9 reached the HTML
as raw LaTeX and stopped the build; a display `array` above a table hid that
table and every one after it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import latex_tables  # noqa: E402

BS = '\\'
TABLE = (BS + 'begin{table}' + BS + 'caption{T}' + BS + 'begin{tabular}{ll}'
         + ' x & y ' + BS + BS + ' ' + BS + 'end{tabular}' + BS + 'end{table}')


class FinderEnvironments(unittest.TestCase):

    def test_a_display_array_does_not_hide_the_table_after_it(self):
        md = ('$$' + BS + 'begin{array}{cc} a & b ' + BS + 'end{array}$$\n\n'
              + TABLE)
        self.assertEqual(len(latex_tables.find_raw_latex_tables(md)), 1)

    def test_a_tabularx_is_a_table_and_does_not_hide_the_next(self):
        tabx = (BS + 'begin{table}' + BS + 'caption{X}' + BS + 'begin{tabularx}{'
                + BS + 'linewidth}{lX} x & y ' + BS + 'end{tabularx}'
                + BS + 'end{table}')
        found = latex_tables.find_raw_latex_tables(tabx + '\n\n' + TABLE)
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0]['bare'].endswith(BS + 'end{tabularx}'))

    def test_a_commented_float_boundary_leaves_no_percent_line(self):
        """ResNet: `%\\end{table}` / `%\\begin{table}[t]` between two tables
        left a bare `%` printed on a line of its own."""
        from unittest import mock
        md = (TABLE.replace('\\end{table}', '%\n%\\end{table}')
              + '\n%\\begin{table}[t]\n' + TABLE[len('\\begin{table}'):]
              + '\n\n```\n%\n```\n')

        def run(cmd, **kwargs):
            return mock.Mock(returncode=0, stdout='<table><tr><td>x</td></tr></table>',
                             stderr='')

        with mock.patch.object(latex_tables.subprocess, 'run', side_effect=run):
            out, ok, _bad = latex_tables.expand_raw_latex_tables(md, pandoc='pandoc')
        self.assertEqual(ok, 2)
        self.assertNotRegex(out.split('```')[0], r'(?m)^[ \t]*%[ \t]*$')
        self.assertIn('```\n%\n```', out, 'a code listing keeps its lines')

    def test_the_preamble_rewrite_still_reaches_tabularx(self):
        latex = BS + 'begin{tabularx}{' + BS + 'linewidth}{@{}p{1cm}X@{}} a & b ' + BS + 'end{tabularx}'
        _out, changed = latex_tables.normalise_tabular_preambles(latex)
        self.assertEqual(changed, 1)


if __name__ == '__main__':
    unittest.main()
