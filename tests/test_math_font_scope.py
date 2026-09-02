# -*- coding: utf-8 -*-
r"""Tests for the scope of the pre-LaTeX2e font-switch rewrite.

`\mathbf` is a math-mode command. The rewrite that produces it ran on the
whole document, so it fired on text-mode `{\bf ...}` too -- and a `tabular`
cell is text mode. CafeQ's table 4 held `{\bf 46.6}`; the rewrite made it
`\mathbf{46.6}`, the table renderer could not parse the cell, and the row
went missing from the book while the build reported `8 converted, 0 failed`.
v1 shipped those three numbers and v3 did not.

Nothing tested this pass before, which is exactly how a text-mode/math-mode
confusion stayed in it. The fixtures below run in both directions: the
modernisation still has to happen inside math, and must not happen outside.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class MathFontScope(unittest.TestCase):

    def rewrite(self, text):
        out, _stats = mb.normalize_math_commands(text)
        return out

    # ---- inside math: the modernisation still happens ----

    def test_inline_math_is_modernised(self):
        self.assertEqual(self.rewrite(r'value $ {\bf x} $ here'),
                         r'value $ \mathbf{x} $ here')

    def test_display_math_is_modernised(self):
        self.assertIn(r'\mathrm{Q}', self.rewrite(r'$$ {\rm Q}(W) $$'))

    def test_math_environment_is_modernised(self):
        got = self.rewrite('\\begin{align}\n  {\\bf A} = B\n\\end{align}')
        self.assertIn(r'\mathbf{A}', got)

    def test_bracket_display_is_modernised(self):
        self.assertIn(r'\mathit{y}', self.rewrite(r'\[ {\it y} \]'))

    def test_operator_body_keeps_the_command_alone(self):
        # \mathrm{\min} is not valid TeX; the older behaviour is preserved.
        self.assertEqual(self.rewrite(r'$ {\rm \min} $'), r'$ \min $')

    # ---- outside math: the source is left exactly as written ----

    def test_tabular_cell_is_left_alone(self):
        row = r'CafeQ & {\bf 46.6} & {\bf 47.6} & {\bf 46.8} \\'
        tex = ('\\begin{table}\n\\begin{tabular}{lccc}\n'
               + row + '\n\\end{tabular}\n\\end{table}\n')
        got = self.rewrite(tex)
        self.assertIn(row, got)
        self.assertNotIn(r'\mathbf', got)

    def test_font_switch_nested_in_textbf_is_left_alone(self):
        cell = r'\textbf{{\rm CafeQ}~(ours)} & \textbf{35.1} \\'
        tex = ('\\begin{tabular}{lc}\n' + cell + '\n\\end{tabular}\n')
        self.assertIn(cell, self.rewrite(tex))

    def test_math_inside_a_table_is_still_modernised(self):
        # Held back from the cells, not from the formulas in them: texmath
        # cannot read `{\rm Q}` and leaves the span unrendered.
        tex = ('\\begin{tabular}{lc}\n'
               'map & ${\\rm Q}(W)$ \\\\\n'
               '\\end{tabular}\n')
        got = self.rewrite(tex)
        self.assertIn(r'$\mathrm{Q}(W)$', got)

    def test_prose_math_is_modernised_next_to_a_table(self):
        # Holding a table back must not shift what happens around it.
        doc = ('Before $ {\\rm Q}(W) $ here.\n\n'
               '\\begin{tabular}{lc}\nCafeQ & {\\bf 46.6} \\\\\n'
               '\\end{tabular}\n\n'
               'After $ {\\rm Q}(V) $ too.\n')
        got = self.rewrite(doc)
        self.assertIn(r'$ \mathrm{Q}(W) $', got)
        self.assertIn(r'$ \mathrm{Q}(V) $', got)
        self.assertIn(r'{\bf 46.6}', got)

    def test_code_region_is_left_alone(self):
        fenced = '```\n$ {\\bf x} $\n```\n'
        self.assertEqual(self.rewrite(fenced), fenced)

    def test_inline_code_is_left_alone(self):
        self.assertEqual(self.rewrite(r'use `$ {\bf x} $` verbatim'),
                         r'use `$ {\bf x} $` verbatim')

    # ---- the two together, as they occur in one document ----

    def test_math_and_table_in_one_document(self):
        doc = ('Then $\\widehat{W} \\leftarrow {\\rm Q}(W)$ follows.\n\n'
               '\\begin{table}\n\\begin{tabular}{lc}\n'
               'CafeQ & {\\bf 46.6} \\\\\n'
               '\\end{tabular}\n\\end{table}\n')
        got = self.rewrite(doc)
        self.assertIn(r'\mathrm{Q}', got)          # the math was modernised
        self.assertIn(r'{\bf 46.6}', got)          # the cell was not
        self.assertEqual(got.count(r'\mathbf'), 0)

    def test_stats_count_only_what_was_rewritten(self):
        _out, stats = mb.normalize_math_commands(
            '$ {\\bf a} $\n\n\\begin{tabular}{c}\n{\\bf b} \\\\\n'
            '\\end{tabular}\n')
        self.assertEqual(stats['fonts'], 1)


if __name__ == '__main__':
    unittest.main()
