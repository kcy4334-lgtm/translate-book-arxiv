# -*- coding: utf-8 -*-
r"""Tests for math in the bilingual suffix of a heading.

CafeQ writes `\newcommand{\tx}{\ensuremath{M}}` and then
`\paragraph{Constraints on $\tx$}`. Expanding the macro gives
`$\ensuremath{M}$`, and wrapping the body in dollars a second time gives
`$$M$$` — display math. pandoc emits a centred block for it, so the heading
printed as `M에 대한 제약 (Constraints on` with a lone centred `M` 27pt below
and the closing bracket after that: one heading across three lines.

The source had already opened math there. The pair it opened is the pair to
use.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

MACROS = {'tx': r'\ensuremath{M}'}


class HeadingMath(unittest.TestCase):

    def test_ensuremath_inside_existing_math_stays_inline(self):
        got = mb.clean_heading_title(r'Constraints on $\tx$', MACROS)
        self.assertEqual(got, 'Constraints on $M$')
        self.assertNotIn('$$', got)

    def test_ensuremath_outside_math_still_gets_its_dollars(self):
        got = mb.clean_heading_title(r'Optimization of \tx', MACROS)
        self.assertEqual(got, 'Optimization of $M$')

    def test_a_heading_with_no_math_is_unchanged(self):
        self.assertEqual(mb.clean_heading_title('Main Results', MACROS),
                         'Main Results')

    def test_two_of_them_in_one_heading(self):
        got = mb.clean_heading_title(
            r'Learning an orthonormal $\tx$ from $\tx$', MACROS)
        self.assertEqual(got, 'Learning an orthonormal $M$ from $M$')
        self.assertNotIn('$$', got)

    def test_plain_inline_math_is_left_alone(self):
        got = mb.clean_heading_title(r'Sensitivity of $\gamma$', MACROS)
        self.assertEqual(got, r'Sensitivity of $\gamma$')

    def test_no_heading_suffix_carries_display_math(self):
        # Display math in a heading is never wanted: it is a line of text.
        for raw in (r'Constraints on $\tx$', r'On \tx and $\tx$'):
            self.assertNotIn('$$', mb.clean_heading_title(raw, MACROS))


class GlossMathShorthand(unittest.TestCase):
    r"""VAE's appendix heading kept `\qPhi` in its original-title bracket,
    which texmath cannot read: `$- D_{KL}(\qPhi(\bz) || \pT(\bz))$` printed."""

    def test_the_bracket_gets_the_same_expansion_as_the_title(self):
        import shutil
        import tempfile
        import latex_cleanup
        real = latex_cleanup.read_pdf_section_prefixes
        latex_cleanup.read_pdf_section_prefixes = lambda d, h: (
            ['1', '2', 'A'], {'matched': 3, 'unnumbered': 0, 'missing': 0,
                              'wrapped': 0, 'reason': None})
        self.addCleanup(setattr, latex_cleanup, 'read_pdf_section_prefixes', real)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write('\\newcommand{\\bz}{\\mathbf{z}}\n'
                     '\\section{Intro}\nx\n\\section{Method}\ny\n'
                     '\\section{Solution of $\\bz$, Gaussian case}\nz\n')
        md = ('# 서론\n\n본문.\n\n# 방법\n\n본문.\n\n'
              '# $\\mathbf{z}$의 해, 가우시안 경우\n\n본문.\n')
        out, stats = mb.number_sections(md, d)
        self.assertEqual(stats['numbered'], 3, stats)
        self.assertIn('(Solution of $\\mathbf{z}$, Gaussian case)', out)
        self.assertNotIn('\\bz', out)


if __name__ == '__main__':
    unittest.main()
