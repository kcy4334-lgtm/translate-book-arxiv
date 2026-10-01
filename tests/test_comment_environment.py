# -*- coding: utf-8 -*-
r"""A section the author deleted was counted as one the translation had lost.

`\begin{comment}...\end{comment}` (comment.sty, verbatim.sty) hides its
contents as completely as a `%` does. pandoc drops it correctly; what reads
flat.tex afterwards did not. Maynard leaves a 54-line block holding
`\section{Motivation}`, so `read_tex_headings` returned eleven headings against
the translation's ten and the build printed

    Sections: not numbered — 11 headings in flat.tex vs 10 in the translation
    — refusing to guess

and shipped a book with no section numbers at all, over a section the author
had already removed. The block hides two theorems and their labels as well, so
every theorem number after it would have been one too high.

`strip_tex_comments` is the right place: every caller reads flat.tex to learn
structure, and none of them produces shipped content.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402

NL = '\n'


class TheCommentEnvironmentIsRemoved(unittest.TestCase):
    def test_a_block_goes_with_its_contents(self):
        tex = ('before' + NL +
               r'\begin{comment}' + NL + r'\section{Motivation}' + NL +
               r'\end{comment}' + NL + 'after')
        got = mb.strip_tex_comments(tex)
        self.assertNotIn('Motivation', got)
        self.assertIn('before', got)
        self.assertIn('after', got)

    def test_a_heading_after_the_block_survives(self):
        tex = (r'\begin{comment}' + NL + r'\section{Hidden}' + NL +
               r'\end{comment}' + NL + r'\section{Real}')
        got = mb.strip_tex_comments(tex)
        self.assertNotIn('Hidden', got)
        self.assertIn('Real', got)

    def test_two_blocks_are_both_removed_without_joining(self):
        tex = (r'\begin{comment}a\end{comment}' + 'KEEP' +
               r'\begin{comment}b\end{comment}')
        got = mb.strip_tex_comments(tex)
        self.assertEqual(got.strip(), 'KEEP')

    def test_whitespace_inside_the_command_is_tolerated(self):
        tex = r'\begin {comment}' + 'x' + r'\end {comment}' + 'Y'
        self.assertEqual(mb.strip_tex_comments(tex).strip(), 'Y')

    def test_an_unclosed_block_is_left_alone(self):
        # Better to keep a heading that should have gone than to swallow the
        # rest of the document on a malformed source.
        tex = r'\begin{comment}' + NL + r'\section{Real}'
        self.assertIn('Real', mb.strip_tex_comments(tex))

    def test_percent_comments_still_go(self):
        self.assertEqual(mb.strip_tex_comments('keep %drop' + NL + 'next'),
                         'keep ' + NL + 'next')

    def test_an_escaped_percent_still_survives(self):
        self.assertEqual(mb.strip_tex_comments('100' + chr(92) + '% done'),
                         '100' + chr(92) + '% done')


class HeadingsSkipTheHiddenOnes(unittest.TestCase):
    def test_read_tex_headings_ignores_a_commented_section(self):
        import tempfile
        import shutil
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(r'\section{Introduction}' + NL +
                     r'\begin{comment}' + NL + r'\section{Motivation}' + NL +
                     r'\end{comment}' + NL +
                     r'\section{Notation}' + NL)
        titles = [t for _lvl, t, _n in mb.read_tex_headings(d)]
        self.assertEqual(titles, ['Introduction', 'Notation'])


class FalseConditionalsAreSkipped(unittest.TestCase):
    r"""`\iffalse ... \fi` hides a passage exactly as `comment` does.

    AdamX (2609.11867) disables a "Strongly Convex Losses" subsection and two
    figures that way. pandoc skipped them, so the translation was right, but
    every count read from flat.tex included them: an extra section in the
    heading list and a figure numbered 3 that the paper prints as 1.
    """

    def test_a_block_goes_with_its_contents(self):
        tex = ('before' + NL + r'\iffalse' + NL +
               r'\subsection{Strongly Convex Losses}' + NL + r'\fi' + NL +
               'after')
        got = mb.strip_tex_comments(tex)
        self.assertNotIn('Strongly', got)
        self.assertIn('before', got)
        self.assertIn('after', got)

    def test_line_positions_do_not_move(self):
        tex = 'a' + NL + r'\iffalse' + NL + 'x' + NL + r'\fi' + NL + 'b'
        got = mb.drop_false_conditionals(tex)
        self.assertEqual(got.count(NL), tex.count(NL))
        self.assertEqual(got.split(NL)[-1], 'b')

    def test_the_else_branch_is_kept(self):
        got = mb.drop_false_conditionals(
            r'\iffalse hidden \else shown \fi end')
        self.assertNotIn('hidden', got)
        self.assertIn('shown', got)
        self.assertIn('end', got)

    def test_a_nested_conditional_does_not_end_the_block(self):
        # The inner \fi closes the inner \ifx, not the \iffalse.
        got = mb.drop_false_conditionals(
            r'\iffalse a \ifx\x\y b \fi c \fi d')
        self.assertEqual(got.split(), ['d'])

    def test_the_maths_arrow_is_not_a_conditional(self):
        # `\iff` opening a level would swallow everything after the block.
        got = mb.drop_false_conditionals(
            r'\iffalse $p \iff q$ \fi kept')
        self.assertEqual(got.split(), ['kept'])

    def test_ifthenelse_and_newif_open_nothing(self):
        got = mb.drop_false_conditionals(
            r'\iffalse \ifthenelse{1=1}{a}{b} \newif\ifdraft \fi kept')
        self.assertEqual(got.split(), ['kept'])

    def test_an_unmatched_iffalse_deletes_nothing(self):
        tex = r'\iffalse' + NL + r'\section{Everything after}' + NL + 'more'
        self.assertEqual(mb.drop_false_conditionals(tex), tex)

    def test_a_longer_command_is_not_a_fi_or_an_else(self):
        # \fill and \elsewhere are words, not the tokens that end a block.
        got = mb.drop_false_conditionals(
            r'\iffalse \fill \elsewhere x \fi kept')
        self.assertEqual(got.split(), ['kept'])

    def test_a_commented_iffalse_hides_nothing(self):
        tex = r'% \iffalse' + NL + r'\section{Shown}' + NL + r'% \fi'
        self.assertIn('Shown', mb.strip_tex_comments(tex))


if __name__ == '__main__':
    unittest.main()
