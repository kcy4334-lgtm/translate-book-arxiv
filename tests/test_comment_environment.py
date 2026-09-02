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


if __name__ == '__main__':
    unittest.main()
