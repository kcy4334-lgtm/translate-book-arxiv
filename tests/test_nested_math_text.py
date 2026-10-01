# -*- coding: utf-8 -*-
r"""`$` nested inside `\text{}` -- and why deleting it is the wrong repair.

Two papers carry the same shape and disagree about it. ResNet's
`\text{3$\times$3, 64}` renders as written; Neural ODE's
`\mathrm{event at time $t$}` does not. Deleting the inner delimiters fixes the
second and breaks the first, because `\times` in text mode means nothing --
that regression took a clean ResNet to 112 leaked tokens.

Splitting the group satisfies both. These tests pin that, and pin the two ways
the pattern previously reached too far.

Splitting alone is not enough, though, and the missing half shipped: the split
put X back with no delimiters, which is right inside a formula and wrong in a
table cell, where `\pm` in text mode is nothing and pandoc drops it in
silence. Looped flows' table 1 read `97.9 0.4` where the paper says
`97.9 ± 0.4`, in the three cells that were bold. X is reopened with
`\ensuremath` now, which is correct in both modes and so needs nobody to
work out which mode this is.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class SplitNestedMathText(unittest.TestCase):
    def test_group_is_split_not_flattened(self):
        got, n = mb.split_nested_math_text(r'$\text{3$\times$3, 64}$')
        self.assertEqual(n, 1)
        self.assertEqual(got, r'$\text{3}\ensuremath{\times}\text{3, 64}$')
        # The delimiters must not simply vanish: that is the broken repair.
        self.assertNotIn(r'\text{3\times3, 64}', got)

    def test_inner_math_keeps_its_braces(self):
        got, n = mb.split_nested_math_text(
            r'$p(\mathrm{event at time $\mathbf{z}(t)$}|x)$')
        self.assertEqual(n, 1)
        self.assertIn(r'\mathbf{z}(t)', got)
        self.assertNotIn(r'$\mathbf{z}(t)$', got)

    def test_bold_table_cell_keeps_its_symbol(self):
        # Looped flows' table 1. The cell is in TEXT mode, so the split has to
        # put `\pm` back into maths: left bare, pandoc drops it and the column
        # reads `97.9 0.4`, which is a different number from the one the paper
        # reports. The neighbouring cell is not bold, so it never nested and
        # never showed the defect -- that is why the table looked half right.
        got, n = mb.split_nested_math_text(
            r'\textbf{97.9 $\pm$ 0.4} & 86.7 $\pm$ 1.1 \\')
        self.assertEqual(n, 1)
        self.assertEqual(
            got, r'\textbf{97.9 }\ensuremath{\pm}\textbf{ 0.4} & 86.7 $\pm$ 1.1 \\')

    def test_symbol_is_never_left_in_text_mode(self):
        # The shape the defect had. Whatever else changes, the symbol may not
        # come out of this pass standing between two text groups on its own.
        for text, symbol in ((r'\textbf{97.9 $\pm$ 0.4}', r'\pm'),
                             (r'\textrm{a $\times$ b}', r'\times'),
                             (r'\text{3$\times$3, 64}', r'\times')):
            got, n = mb.split_nested_math_text(text)
            self.assertEqual(n, 1)
            self.assertIn(r'\ensuremath{%s}' % symbol, got)
            self.assertNotIn('}%s' % symbol, got)

    def test_same_output_whatever_the_surrounding_mode(self):
        # The point of `\ensuremath`: the pass does not have to know whether
        # the group sits in a formula, and so cannot get that question wrong.
        # A display the pass has no scanner for -- an amsmath environment --
        # comes out exactly as the inline form does.
        inline, _a = mb.split_nested_math_text(r'$\text{3$\times$3}$')
        env, _b = mb.split_nested_math_text(
            '\\begin{equation}\n\\text{3$\\times$3}\n\\end{equation}')
        cell, _c = mb.split_nested_math_text(r'x & \text{3$\times$3} \\')
        body = r'\text{3}\ensuremath{\times}\text{3}'
        for got in (inline, env, cell):
            self.assertIn(body, got)

    def test_does_not_reach_across_two_formulas(self):
        # `\text{` in one formula and `}` in a later one must never pair up:
        # doing so deletes two real delimiters.
        text = r'$a\text{x}b$ and $c\text{y}d$'
        got, n = mb.split_nested_math_text(text)
        self.assertEqual(n, 0)
        self.assertEqual(got, text)

    def test_span_without_nesting_is_untouched(self):
        text = r'$\text{plain}$'
        self.assertEqual(mb.split_nested_math_text(text), (text, 0))

    def test_two_nested_spans_in_one_argument_are_left_alone(self):
        # A documented boundary, not an oversight. One nested span per
        # argument is handled; two are left exactly as they were rather than
        # widened for — an over-reaching version of this pattern is what took
        # a clean ResNet to 112 leaked tokens.
        text = r'$\text{a$x$b$y$c}$'
        self.assertEqual(mb.split_nested_math_text(text), (text, 0))

    def test_prose_dollars_are_not_math(self):
        text = r'It costs $5 and \text{then} $6 total'
        self.assertEqual(mb.split_nested_math_text(text), (text, 0))


class MathDirectivesAndPhantoms(unittest.TestCase):
    def test_vphantom_removed_at_any_brace_depth(self):
        span = (r'$a\vphantom{\frac{\partial p(\mathbf{z}(t), t)}'
                r'{\partial \mathbf{z}(t)}}b$')
        got, _ = mb.rewrite_text_fonts_in_math(span)
        self.assertNotIn(r'\vphantom', got)
        self.assertIn('a', got)
        self.assertIn('b', got)

    def test_qedhere_and_notag_are_dropped(self):
        got, _ = mb.rewrite_text_fonts_in_math(r'$$x = y \qedhere$$')
        self.assertNotIn(r'\qedhere', got)
        got, _ = mb.rewrite_text_fonts_in_math(r'$$x = y \notag$$')
        self.assertNotIn(r'\notag', got)


class SpacingLeftovers(unittest.TestCase):
    def test_bare_length_on_its_own_line_is_dropped(self):
        # What a half-stripped `\vspace*{-2.5mm}` leaves above a figure.
        text = 'para\n\n{-2.5mm}\n![](images/x.png)\n'
        got = mb._SPACING_INLINE_RE.sub('', text)
        self.assertNotIn('{-2.5mm}', got)
        self.assertIn('![](images/x.png)', got)

    def test_a_brace_inside_prose_is_left_alone(self):
        text = 'the set {-2.5mm} appears inline here'
        self.assertEqual(mb._SPACING_INLINE_RE.sub('', text), text)


if __name__ == '__main__':
    unittest.main()
