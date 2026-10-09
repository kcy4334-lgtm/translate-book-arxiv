# -*- coding: utf-8 -*-
r"""Formulas texmath refused over a colour, a height or a font switch.

2609.11716 colours each term of its decomposition. texmath has no reader for
`\textcolor`, fails on `\color{c}` when `\boldsymbol` follows it, and has no
`\smash`, so 59 of the paper's formulas printed as raw TeX. Taking those
commands out costs the colour and a little vertical spacing; the formulas
render.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb  # noqa: E402

BS = '\\'


class MathColour(unittest.TestCase):

    def test_textcolor_keeps_its_content(self):
        out, n = mb.drop_math_colour(
            'term $' + BS + 'textcolor{termcontrast}{' + BS + 'bm{T}}$ here')
        self.assertEqual(out, 'term ${' + BS + 'bm{T}}$ here')
        self.assertEqual(n, 1)

    def test_a_colour_switch_goes(self):
        out, _n = mb.drop_math_colour(
            '${' + BS + 'color{cleanred}' + BS + 'boldsymbol{F}}(x)$')
        self.assertEqual(out, '${' + BS + 'boldsymbol{F}}(x)$')

    def test_smash_and_text_rm(self):
        out, _n = mb.drop_math_colour(
            '$$x_{' + BS + 'smash[t]{a}} && ' + BS + 'text{' + BS + 'rm(exact)}$$')
        self.assertEqual(out, '$$x_{{a}} && ' + BS + 'text{(exact)}$$')

    def test_verb_in_a_formula_becomes_texttt(self):
        """GPT-3: `$$\\verb|np.random.pareto|(\\alpha) > 1 - \\verb|document_score|$$`."""
        out, _n = mb.drop_math_colour(
            '$$' + BS + 'verb|np.random.pareto|(' + BS + 'alpha) > 1 - '
            + BS + 'verb|document_score|$$')
        self.assertEqual(out, '$$' + BS + 'texttt{np.random.pareto}(' + BS
                         + 'alpha) > 1 - ' + BS + 'texttt{document' + BS
                         + '_score}$$')

    def test_emph_in_a_formula_becomes_textit(self):
        """PaLM's table footnote letters: `62.4$^{\\emph{b}}$`."""
        out, _n = mb.drop_math_colour('62.4$^{' + BS + 'emph{b}}$')
        self.assertEqual(out, '62.4$^{' + BS + 'textit{b}}$')

    def test_text_outside_math_is_left_alone(self):
        text = 'a ' + BS + 'textcolor{red}{word} in prose'
        self.assertEqual(mb.drop_math_colour(text), (text, 0))


if __name__ == '__main__':
    unittest.main()
