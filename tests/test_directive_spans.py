# -*- coding: utf-8 -*-
r"""Layout directives printed themselves in five finished books.

`\pagestyle{empty}`, `\thispagestyle{plain}`, `\@addtoreset{equation}{section}`,
`\allowdisplaybreaks`, `\algrenewcommand{\algorithmicindent}{1em}`,
`\titlerunning{U-Net}` — none of them puts anything on the page, and pandoc
hands every one through as a raw inline. They need the same removal `\index`
does: the wrapping backticks go with the command, or the empty pair that is
left behind opens a code span and swallows the text after it (K133).

The list is deliberately short. A command whose argument is CONTENT is not in
it and must be resolved rather than dropped — `\parhead` is spectre's run-in
HEADING, twelve of them; `\subref`, `\cref` and `\newcite` are references;
`\answerYes` is a checklist answer that carries its own text. K135 holds that
inventory.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class DirectivesGo(unittest.TestCase):
    def test_a_directive_with_one_argument(self):
        got, n = mb.drop_directive_spans('before \\pagestyle{empty} after')
        self.assertEqual((got, n), ('before  after', 1))

    def test_a_directive_with_no_argument(self):
        got, n = mb.drop_directive_spans('a \\allowdisplaybreaks b')
        self.assertEqual((got, n), ('a  b', 1))

    def test_a_directive_with_two_arguments(self):
        got, n = mb.drop_directive_spans(
            r'x \algrenewcommand{\algorithmicindent}{1em} y')
        self.assertEqual((got, n), ('x  y', 1))

    def test_the_wrapping_raw_inline_goes_too(self):
        got, _ = mb.drop_directive_spans('a `\\pagestyle{empty}`{=latex} b')
        self.assertEqual(got, 'a  b')
        self.assertNotIn('`', got)

    def test_the_math_around_it_survives(self):
        got, _ = mb.drop_directive_spans(
            '$A$ `\\thispagestyle{plain}` $B$')
        self.assertEqual(got.count('$'), 4)
        self.assertNotIn('``', got)

    def test_an_at_command_is_matched(self):
        got, n = mb.drop_directive_spans(
            r'p \@addtoreset{equation}{section} q')
        self.assertEqual((got, n), ('p  q', 1))

    def test_several_in_one_pass(self):
        got, n = mb.drop_directive_spans(
            r'\pagestyle{a} mid \thispagestyle{b} end')
        self.assertEqual(n, 2)
        self.assertIn('mid', got)
        self.assertIn('end', got)


class ContentBearingCommandsStay(unittest.TestCase):
    def test_parhead_is_untouched(self):
        # spectre's run-in heading: twelve real headings.
        src = r'\parhead{Attacks using JavaScript} The attack works by'
        self.assertEqual(mb.drop_directive_spans(src), (src, 0))

    def test_references_are_untouched(self):
        for src in (r'see \subref{fig:a}', r'see \cref{sec:b}',
                    r'as \newcite{smith} showed'):
            self.assertEqual(mb.drop_directive_spans(src), (src, 0))

    def test_a_checklist_answer_is_untouched(self):
        src = r'\answerYes{The code is released.}'
        self.assertEqual(mb.drop_directive_spans(src), (src, 0))

    def test_ordinary_prose_is_untouched(self):
        src = 'The page style of the document is plain.'
        self.assertEqual(mb.drop_directive_spans(src), (src, 0))

    def test_an_unbalanced_brace_leaves_the_text_alone(self):
        src = r'\pagestyle{never closed'
        self.assertEqual(mb.drop_directive_spans(src), (src, 0))


if __name__ == '__main__':
    unittest.main()
