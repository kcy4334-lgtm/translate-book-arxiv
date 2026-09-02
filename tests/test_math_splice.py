# -*- coding: utf-8 -*-
r"""Tests for emphasis spliced through MathML, and the reader flag that stops it.

pandoc parses markdown inside block-level HTML by default. The only such
blocks this pipeline emits are the raw-LaTeX tables, rendered as finished
HTML with MathML inside -- and a literal `*` in one formula pairs with the
next `*` further down the table, opening an `<em>` inside one `<math>` and
closing it inside another. CafeQ's table 3 printed `45.6^{}` where the paper
prints `45.6*`, and the asterisk its own caption explains was gone.

Every count still balanced: 225 formulas in, 225 out. That is why the check
below looks at what is inside a formula rather than how many there are.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

CLEAN = ('<math display="inline"><semantics><msup><mi>x</mi><mo>*</mo></msup>'
         '<annotation encoding="application/x-tex">x^{*}</annotation>'
         '</semantics></math>')
SPLICED = ('<math display="inline"><semantics><msup><mi></mi><mo><em></mo>'
           '</msup><annotation encoding="application/x-tex">^{</em>}'
           '</annotation></semantics></math>')


class SplicedMath(unittest.TestCase):

    def test_clean_mathml_is_silent(self):
        self.assertEqual(mb.find_spliced_math('<p>a</p>' + CLEAN), [])

    def test_emphasis_inside_a_formula_is_found(self):
        self.assertEqual(len(mb.find_spliced_math(SPLICED)), 1)

    def test_emphasis_beside_a_formula_is_not_a_finding(self):
        # Italic prose next to a formula is ordinary text, not damage.
        self.assertEqual(mb.find_spliced_math('<p><em>note</em></p>' + CLEAN),
                         [])

    def test_strong_counts_too(self):
        blob = CLEAN.replace('<mo>*</mo>', '<mo><strong>*</strong></mo>')
        self.assertEqual(len(mb.find_spliced_math(blob)), 1)

    def test_several_damaged_formulas_are_all_reported(self):
        self.assertEqual(len(mb.find_spliced_math(SPLICED * 3 + CLEAN)), 3)

    def test_check_fails_the_build_on_spliced_math(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, 'output.md')
            with open(md, 'w', encoding='utf-8') as fh:
                fh.write('text $x^{*}$ more\n')
            self.assertFalse(mb.check_math_fidelity(md, SPLICED))

    def test_check_passes_on_clean_math(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, 'output.md')
            with open(md, 'w', encoding='utf-8') as fh:
                fh.write('text $x^{*}$ more\n')
            self.assertTrue(mb.check_math_fidelity(md, CLEAN))


class ReaderFlags(unittest.TestCase):

    def test_markdown_in_html_blocks_is_off(self):
        self.assertIn('-markdown_in_html_blocks', mb.PANDOC_FROM)

    def test_the_extensions_the_pipeline_needs_stay_on(self):
        for ext in ('tex_math_dollars', 'raw_html', 'pipe_tables',
                    'grid_tables'):
            self.assertIn('+' + ext, mb.PANDOC_FROM)


if __name__ == '__main__':
    unittest.main()
