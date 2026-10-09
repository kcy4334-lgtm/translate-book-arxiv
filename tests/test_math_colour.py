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

    def test_text_outside_math_is_left_alone(self):
        text = 'a ' + BS + 'textcolor{red}{word} in prose'
        self.assertEqual(mb.drop_math_colour(text), (text, 0))


if __name__ == '__main__':
    unittest.main()
