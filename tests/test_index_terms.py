# -*- coding: utf-8 -*-
r"""`\index{sub-gaussian}` printed itself 79 times in randmat's body.

The paper builds a real index — `makeidx`, `\makeindex`, `\printindex` — and
this pipeline builds none, so every `\index{...}` marker reached the page as
literal LaTeX beside the word it was marking.

Dropping them is a reduction, not a repair: the original has an index and the
book will not. That is why the build says so — a loss nobody reports is what
K110 is about, and this one had gone unreported through every build.

The trap is the code span. pandoc hands these through as raw inlines, so the
markdown says `` `\index{Condition number}` ``, and removing only the command
leaves an empty pair of backticks — which is a code-span DELIMITER that
swallows text to the next one, `$` included. Done that way the fix took
randmat from 0 unrendered formulas to 29 while removing the 79 markers. The
span goes with the command.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class IndexMarkersGo(unittest.TestCase):
    def test_a_bare_marker_takes_its_term_with_it(self):
        got, n = mb.drop_index_terms(r'준가우시안\index{sub-gaussian} 변수')
        self.assertEqual(got, '준가우시안 변수')
        self.assertEqual(n, 1)

    def test_a_wrapped_marker_takes_its_backticks_too(self):
        got, n = mb.drop_index_terms('의 *조건수* `\\index{Condition number}`가')
        self.assertEqual(got, '의 *조건수* 가')
        self.assertEqual(n, 1)
        self.assertNotIn('`', got)

    def test_the_pandoc_raw_marker_goes_with_it(self):
        got, _ = mb.drop_index_terms('a `\\index{x}`{=latex} b')
        self.assertEqual(got, 'a  b')

    def test_the_math_around_it_survives(self):
        # The regression this exists for: an empty code span between two
        # dollars re-pairs them and the formula prints as source.
        got, _ = mb.drop_index_terms(
            '$A$의 *조건수* `\\index{Condition number}`가 $B$')
        self.assertEqual(got.count('$'), 4)
        self.assertNotIn('``', got)

    def test_a_nested_brace_in_the_term_is_consumed(self):
        got, _ = mb.drop_index_terms(r'x\index{norm!{inner} more} y')
        self.assertEqual(got, 'x y')

    def test_printindex_goes(self):
        got, n = mb.drop_index_terms('before \\printindex after')
        self.assertEqual(got, 'before  after')
        self.assertEqual(n, 1)

    def test_several_in_one_line(self):
        got, n = mb.drop_index_terms(r'a\index{one} b\index{two} c')
        self.assertEqual((got, n), ('a b c', 2))

    def test_an_unbalanced_brace_leaves_the_text_alone(self):
        text = r'a\index{never closed'
        got, n = mb.drop_index_terms(text)
        self.assertEqual((got, n), (text, 0))

    def test_a_document_with_none_is_untouched(self):
        text = 'The index of the matrix is 3.'
        self.assertEqual(mb.drop_index_terms(text), (text, 0))

    def test_a_neighbouring_code_span_is_not_eaten(self):
        # Only the backtick that OWNS the marker may go; `x` here is content.
        got, _ = mb.drop_index_terms('`x` and \\index{y} done')
        self.assertIn('`x`', got)


class TheBuildReportsIt(unittest.TestCase):
    def test_the_count_reaches_the_stats(self):
        _got, stats = mb.normalize_latex_leftovers(
            r'a\index{one} b\index{two} c')
        self.assertEqual(stats['index_terms'], 2)

    def test_zero_when_there_are_none(self):
        _got, stats = mb.normalize_latex_leftovers('ordinary text')
        self.assertEqual(stats['index_terms'], 0)


if __name__ == '__main__':
    unittest.main()
