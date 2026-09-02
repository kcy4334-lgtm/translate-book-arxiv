# -*- coding: utf-8 -*-
r"""`table` must reach the pipeline's own converter, not pandoc's grid writer.

pandoc has no reader for `table*`, so with `+raw_tex` a starred float passes
through verbatim and the pipeline converts it itself, keeping every
`\multicolumn`. `table` it does read — and its markdown writer cannot express
a span in a grid table, so it emits one whose top border declares four
columns while the rows carry seven. pandoc's own reader then locks onto the
border and DISCARDS the overflow. Twelve values from CafeQ's table 1 and six
from table 5 left the book that way, while the prose went on citing them, and
every count in the pipeline still agreed: the rows were there, the numbers
that remained were correct, and nothing counted what was gone.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab


TABLE = ('\\begin{table}[h]\n\\caption{Cap.}\n'
         '\\begin{tabular}{lcc}\n\\toprule\n'
         'A & \\multicolumn{2}{c}{G} \\\\\n1 & 2 & 3 \\\\\n'
         '\\bottomrule\n\\end{tabular}\n\\end{table}\n')


class ProtectTests(unittest.TestCase):
    def test_an_unstarred_float_is_renamed(self):
        out, n = ab.protect_table_floats(TABLE)
        self.assertEqual(n, 1)
        self.assertNotIn('\\begin{table}', out)
        self.assertIn('\\begin{%s}' % ab._PROTECTED_TABLE_ENV, out)
        self.assertIn('\\end{%s}' % ab._PROTECTED_TABLE_ENV, out)

    def test_the_starred_float_is_left_alone(self):
        src = TABLE.replace('{table}', '{table*}')
        out, n = ab.protect_table_floats(src)
        self.assertEqual((out, n), (src, 0))

    def test_the_contents_are_untouched(self):
        out, _n = ab.protect_table_floats(TABLE)
        self.assertIn('\\multicolumn{2}{c}{G}', out)
        self.assertIn('\\begin{tabular}{lcc}', out)

    def test_the_round_trip_restores_the_name(self):
        out, _n = ab.protect_table_floats(TABLE)
        self.assertEqual(ab.restore_table_floats(out), TABLE)

    def test_several_floats_are_counted_once_each(self):
        _out, n = ab.protect_table_floats(TABLE * 3)
        self.assertEqual(n, 3)

    def test_a_document_with_no_float_is_unchanged(self):
        src = 'Plain text with $x$ and \\begin{figure}f\\end{figure}\n'
        self.assertEqual(ab.protect_table_floats(src), (src, 0))

    def test_restore_is_safe_on_text_that_was_never_protected(self):
        src = 'nothing to restore here\n'
        self.assertEqual(ab.restore_table_floats(src), src)

    def test_the_marker_name_cannot_collide_with_a_real_environment(self):
        # It has to be an environment pandoc has no reader for, and one no
        # paper would define.
        self.assertNotIn(ab._PROTECTED_TABLE_ENV,
                         ('table', 'tabular', 'figure', 'longtable',
                          'tabularx', 'array', 'algorithm'))
        self.assertTrue(re.match(r'^[a-z]+$', ab._PROTECTED_TABLE_ENV))


if __name__ == '__main__':
    unittest.main()
