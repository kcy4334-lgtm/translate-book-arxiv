# -*- coding: utf-8 -*-
r"""The math check was counting MathML's own annotation as unrendered math.

pandoc's MathML carries the formula's original TeX in
`<annotation encoding="application/x-tex">`. A display that nests math inside
a text argument keeps real `$...$` pairs in there — Maynard's

    \text{for infinitely many $n$ all of $n+h_1$, $\dotsc$, $n+h_m$ are prime}

puts four of them in one annotation. The build warned that four TeX spans had
reached the HTML unrendered while that display was on the page, correctly
typeset: `#{{h1,…,hm}⊆𝒜:for infinitely many n all of n+h1, …, n+hm are prime}`.

The reason this matters is not the false alarm. A real leak reports the same
number and reads identically, so for any paper with nested text-math the check
could not tell a formula printed as source from one rendered and described.
These tests hold both halves: the annotation is ignored, a genuine leak is not.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402

RENDERED = (
    '<p><math display="block"><semantics><mrow><mi>n</mi></mrow>'
    '<annotation encoding="application/x-tex">'
    r'\text{for infinitely many $n$ all of $n+h_1$, $\dotsc$, '
    r'$n+h_m$ are prime}'
    '</annotation></semantics></math></p>'
)

LEAKED = '<p>The bound is $\\alpha \\le \\beta$ in every case.</p>'


class MathFidelityIgnoresTheAnnotation(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.md = os.path.join(self.dir, 'output.md')
        with open(self.md, 'w', encoding='utf-8') as fh:
            fh.write('Text with $x$ and $y$ in it.\n')

    def test_a_rendered_formula_reports_no_leftovers(self):
        self.assertEqual(
            mb._MATH_SPAN_RE.findall(
                mb._MATHML_ANNOTATION_RE.sub(' ', RENDERED)), [])

    def test_the_annotation_really_did_contain_four_pairs(self):
        # Without the exclusion this is what the check was counting; if this
        # ever stops being four, the regression it guards has moved.
        self.assertEqual(len(mb._MATH_SPAN_RE.findall(RENDERED)), 4)

    def test_a_genuine_leak_is_still_counted(self):
        self.assertEqual(
            len(mb._MATH_SPAN_RE.findall(
                mb._MATHML_ANNOTATION_RE.sub(' ', LEAKED))), 1)

    def test_a_leak_beside_a_rendered_formula_is_still_counted(self):
        page = RENDERED + LEAKED
        self.assertEqual(
            len(mb._MATH_SPAN_RE.findall(
                mb._MATHML_ANNOTATION_RE.sub(' ', page))), 1)

    def test_the_check_passes_on_a_page_that_only_has_an_annotation(self):
        self.assertTrue(mb.check_math_fidelity(self.md, RENDERED))

    def test_an_unclosed_annotation_does_not_swallow_the_page(self):
        # A truncated tag must not let the substitution run to the end of the
        # file and hide every real leak behind it.
        page = '<annotation encoding="application/x-tex">' + LEAKED
        self.assertEqual(
            len(mb._MATH_SPAN_RE.findall(
                mb._MATHML_ANNOTATION_RE.sub(' ', page))), 1)


if __name__ == '__main__':
    unittest.main()
