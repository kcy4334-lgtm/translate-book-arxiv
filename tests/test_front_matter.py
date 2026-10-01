# -*- coding: utf-8 -*-
r"""The author's affiliation was dropped and nothing said so.

Maynard's `\address{Centre de recherches mathematiques, ... H3T 1J4}` appears
once in `flat.tex` and zero times in `input.md`, in any chunk, and in
`output.md`. pandoc has no reader for `\address`, so it discarded the command
together with five lines of real prose — the K110 swallow, invisible to every
check that counts what arrived. `\email` and `\bibliographystyle` had the
opposite failure: they were passed through, and stood on the page as literal
LaTeX for a translator to puzzle over.

The two halves need opposite treatment, which is why one rule cannot serve
both, and the nesting decides the order. In U-Net `\email` sits INSIDE
`\institute{...}`: delete `\email` and the `,\\ WWW home page:` after it is
left with nothing in front of the comma. Unwrapping outermost-first makes the
nesting harmless — measured, the U-Net text comes out as
`... Germany\\ ronneber@informatik.uni-freiburg.de,\\ WWW home page: ...`.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402


class TheAffiliationSurvives(unittest.TestCase):
    def test_address_keeps_its_text(self):
        got, n = ab.unwrap_front_matter(
            r'\author{J M}' '\n' r'\address{Centre de recherches, Montreal}')
        self.assertEqual(n, 1)
        self.assertIn('Centre de recherches, Montreal', got)
        self.assertNotIn(r'\address', got)

    def test_a_multi_line_address_keeps_every_line(self):
        src = '\\address{Centre de recherches,\nUniversite de Montreal,\n' \
              '2920 Chemin de la tour}'
        got, _ = ab.unwrap_front_matter(src)
        for line in ('Centre de recherches,', 'Universite de Montreal,',
                     '2920 Chemin de la tour'):
            self.assertIn(line, got)

    def test_email_keeps_the_address(self):
        got, n = ab.unwrap_front_matter(r'\email{maynardj@dms.umontreal.ca}')
        self.assertEqual((got, n), ('maynardj@dms.umontreal.ca', 1))

    def test_nested_braces_in_the_argument_are_kept(self):
        got, _ = ab.unwrap_front_matter(
            r'\institute{Freiburg, \texttt{http://lmb.example/}}')
        self.assertEqual(got, r'Freiburg, \texttt{http://lmb.example/}')

    def test_the_unet_nesting_leaves_no_dangling_comma(self):
        src = (r'\institute{University of Freiburg, Germany\\'
               '\n' r'\email{ronneber@example.de},\\ WWW home page:'
               '\n' r'\texttt{http://lmb.example/}' '\n}')
        got, _ = ab.unwrap_front_matter(src)
        self.assertIn(r'ronneber@example.de,\\ WWW home page:', got)
        self.assertNotIn(r'\email', got)
        self.assertNotIn(r'\institute', got)

    def test_an_optional_argument_is_consumed_with_the_command(self):
        # `\address[a]{...}` and `\ead[url]{...}` put a label between the
        # command and its brace; left behind, `[a]` prints on the page.
        got, n = ab.unwrap_front_matter(r'\address[a]{Freiburg}')
        self.assertEqual((got, n), ('Freiburg', 1))


class TheDirectivesGo(unittest.TestCase):
    def test_bibliographystyle_goes_with_its_argument(self):
        got, n = ab.unwrap_front_matter(
            'thanks.\n' r'\bibliographystyle{plain}' '\n')
        self.assertEqual(n, 1)
        self.assertNotIn('plain', got)
        self.assertIn('thanks.', got)

    def test_running_heads_go(self):
        got, _ = ab.unwrap_front_matter(
            r'\titlerunning{U-Net}\authorrunning{Ronneberger}Body')
        self.assertEqual(got, 'Body')

    def test_bibliography_is_left_alone(self):
        # citeproc still needs it to find the .bib file.
        src = r'\bibliography{main}'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_parhead_is_left_alone(self):
        # spectre's own \newcommand for a run-in heading: twelve real headings
        # that a drop-with-argument rule would delete outright.
        src = r'\parhead{Attacks using JavaScript}'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))


class CommentsAreNotRewritten(unittest.TestCase):
    def test_a_commented_out_command_is_untouched(self):
        src = '%\\institute{L2 \\and Earth}\n\\section{Real}'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_an_escaped_percent_does_not_hide_the_command(self):
        got, n = ab.unwrap_front_matter(r'100\% \address{Freiburg}')
        self.assertEqual(n, 1)
        self.assertIn('Freiburg', got)

    def test_a_live_command_after_a_comment_line_still_fires(self):
        got, n = ab.unwrap_front_matter(
            '% a note\n\\address{Freiburg}\n')
        self.assertEqual(n, 1)
        self.assertIn('Freiburg', got)


class MalformedInputIsLeftAlone(unittest.TestCase):
    def test_an_unclosed_brace_changes_nothing(self):
        src = r'\address{Centre de recherches'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_a_bare_command_with_no_argument_is_left(self):
        src = r'\email and then prose'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_a_document_with_none_of_them_is_untouched(self):
        src = '\\section{Intro}\nOrdinary text.\n'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))


if __name__ == '__main__':
    unittest.main()
