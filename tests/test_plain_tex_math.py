# -*- coding: utf-8 -*-
r"""Plain TeX inside a formula, rewritten to what texmath reads.

planck, written to A&A's class, lost formulas to `\over`, to `\mathchoice`
(the class's `\vec` and `\tens`) and to `\boldmath`; each printed as source.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import latex_cleanup as lc  # noqa: E402
import merge_and_build as mb  # noqa: E402


class PlainTexMath(unittest.TestCase):

    def test_over_in_a_brace_group(self):
        self.assertEqual(lc._plain_tex_math(r'$\left( {\ell \over 3000} \right)$'),
                         r'$\left( {\frac{\ell}{3000}} \right)$')

    def test_over_in_a_left_right_pair(self):
        self.assertEqual(lc._plain_tex_math(r'$A \left (\ell \over 1500 \right )$'),
                         r'$A \left (\frac{\ell}{1500}\right )$')

    def test_over_at_the_top_of_a_formula(self):
        self.assertEqual(lc._plain_tex_math(r'$$1 \over 4 \pi$$'),
                         r'$$\frac{1}{4 \pi}$$')

    def test_over_in_one_cell(self):
        # As TeX reads it: `\over` takes the whole cell, `=` included.
        self.assertEqual(lc._plain_tex_math(r'a &= {x \over y} \\ b &= 1 \over 2'),
                         r'a &= {\frac{x}{y}} \\ b &\frac{= 1}{2}')

    def test_mathchoice_takes_the_display_branch(self):
        self.assertEqual(
            lc._plain_tex_math(r'$\ensuremath{\mathchoice{\boldmath\displaystyle\hat C}'
                               r' {\boldmath\textstyle\hat C} {\boldmath\scriptstyle\hat C}'
                               r' {\boldmath\scriptscriptstyle\hat C}}^{TT}$'),
            r'$\ensuremath{\boldsymbol{\hat C}}^{TT}$')

    def test_a_font_switch_needs_no_space_before_punctuation(self):
        # planck: `C^{TT{\rm(defect)}}_{10}`.
        out, _stats = lc.normalize_math_commands(
            r'$C^{TT{\rm(defect)}}_{10}$ and ${\rm \min}$')
        self.assertEqual(out, r'$C^{TT\mathrm{(defect)}}_{10}$ and $\min$')

    def test_a_box_around_a_maths_font_goes(self):
        # planck's `\twoonesig` label: `\mbox{\text{...}}` -> `\mbox{\mathrm{..}}`.
        self.assertEqual(lc._unbox_math(r'$\right\} \ \mbox{\mathrm{\mathit{P}\ TT.}}$'),
                         r'$\right\} \ \mathrm{\mathit{P}\ TT.}$')

    def test_a_text_box_holding_maths_fonts_is_split(self):
        # planck's `\twotwosig`: `\mbox{95\%, \text{\planckTT}}`.
        self.assertEqual(
            lc._unbox_math(r'$\right\} \mbox{95\%, \mathrm{\mathit{P}\ \mathrm{TT}}}$'),
            r'$\right\} \text{95\%, }\mathrm{\mathit{P}\ \mathrm{TT}} $')

    def test_dollars_inside_a_mathrm_come_out(self):
        # planck's `\onesig` with `$\Delta N_\mathrm{eff}=0.39$` in its text.
        self.assertEqual(
            lc._unbox_math(r'$(68\%, \mathrm{TT; $\Delta N=0.39$})$'),
            r'$(68\%, \mathrm{TT; }\Delta N=0.39)$')

    def test_a_letter_command_and_a_stray_break(self):
        # planck: `M$\o$ller`, `$400\\,{\rm deg}^2$`.
        self.assertEqual(lc._plain_tex_math(r'$\o$'), r'$\text{ø}$')
        self.assertEqual(lc._plain_tex_math(r'$400\\,{\rm deg}^2$'),
                         r'$400 ,{\rm deg}^2$')
        span = r'$$\begin{aligned}a\\b\end{aligned}$$'
        self.assertEqual(lc._plain_tex_math(span), span)
        self.assertEqual(lc._plain_tex_math(r'$\omega + \ss$'), r'$\omega + \text{ß}$')

    def test_a_font_switch_inside_text(self):
        # 2609.11716's underbrace labels.
        self.assertEqual(
            lc._plain_tex_math(r'$\underbrace{a}_{\substack{\text{\bfseries rel '
                               r'(\bfseries block): }{T}}}$'),
            r'$\underbrace{a}_{\substack{\textbf{rel (block): }{T}}}$')

    def test_a_letter_formula_inside_a_word(self):
        out, _stats = lc.normalize_math_commands(r'the M$\o$ller velocity')
        self.assertEqual(out, 'the Møller velocity')

    def test_overline_and_others_are_untouched(self):
        span = r'$\overline{x} + \overset{a}{b}$'
        self.assertEqual(lc._plain_tex_math(span), span)

    @unittest.skipUnless(mb.resolve_pandoc(), 'needs pandoc')
    def test_texmath_reads_every_result(self):
        for span in (r'$$\left( {\ell \over 3000} \right)^{\gamma}$$',
                     r'$$\hat D = A \left (\ell \over 1500 \right )^{\epsilon}$$',
                     r'$$f = {1 \over 4 \pi} \sum w_i^2$$',
                     r'$\ensuremath{\mathchoice{\boldmath\displaystyle\hat C}'
                     r'{\boldmath\textstyle\hat C}{\boldmath\scriptstyle\hat C}'
                     r'{\boldmath\scriptscriptstyle\hat C}}^{TT}$'):
            md = lc._plain_tex_math(span)
            proc = subprocess.run(
                [mb.resolve_pandoc(), '--from', 'markdown', '--to', 'html5',
                 '--mathml'], input=md + '\n', capture_output=True, text=True,
                encoding='utf-8')
            self.assertNotIn('Could not convert', proc.stderr, md)


if __name__ == '__main__':
    unittest.main()
