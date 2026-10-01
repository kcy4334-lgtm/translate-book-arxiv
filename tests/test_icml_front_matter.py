# -*- coding: utf-8 -*-
r"""SINQ's six authors and its affiliation appear zero times in its own book.

`\icmlauthor{Lorenz K. Muller}{comp}` and `\icmlaffiliation{comp}{Huawei}` have
no pandoc reader, so the command went and the names went with it — K123's
swallow in a second costume, and this one reached a shipped book.

The content is in a DIFFERENT argument for each command, read out of
`icml2026.sty` rather than recalled: `\icmlauthor{#1}{#2}` sets
`\mbox{\bf #1}` and treats #2 as affiliation KEYS, while
`\icmlaffiliation{#1}{#2}` keys on #1 and stores #2. Backwards, an affiliation
key would print where a name belongs.

The enclosing `icmlauthorlist` has to go too. Rescuing the names into an
environment pandoc cannot read only moves the loss one level out.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402

BLOCK = (r'\begin{icmlauthorlist}' '\n'
         r'\icmlauthor{Lorenz K. Muller}{comp}' '\n'
         r'\icmlauthor{Philippe Bich}{comp}' '\n'
         r'\end{icmlauthorlist}' '\n'
         r'\icmlaffiliation{comp}{Huawei}' '\n'
         r'\icmlcorrespondingauthor{Lorenz K. Muller}{lorenz@example.com}' '\n'
         r'\icmlkeywords{Machine Learning, ICML}' '\n')


class TheNamesSurvive(unittest.TestCase):
    def setUp(self):
        self.got, self.n = ab.unwrap_front_matter(BLOCK)

    def test_the_author_names_are_kept(self):
        self.assertIn('Lorenz K. Muller', self.got)
        self.assertIn('Philippe Bich', self.got)

    def test_the_affiliation_key_is_not_printed_as_a_name(self):
        # `\icmlauthor`'s second argument is a key, not content.
        self.assertNotIn('comp', self.got)

    def test_the_affiliation_is_kept_from_the_second_argument(self):
        self.assertIn('Huawei', self.got)

    def test_the_corresponding_author_keeps_both(self):
        self.assertIn('Lorenz K. Muller, lorenz@example.com', self.got)

    def test_the_keywords_directive_goes(self):
        self.assertNotIn('icmlkeywords', self.got)
        self.assertNotIn('Machine Learning, ICML', self.got)

    def test_the_wrapper_environment_goes(self):
        self.assertNotIn('icmlauthorlist', self.got)

    def test_no_icml_command_survives(self):
        self.assertNotIn('\\icml', self.got)


class ItIsNarrow(unittest.TestCase):
    def test_a_paper_with_none_of_them_is_untouched(self):
        src = '\\section{Intro}\nOrdinary text.\n'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_a_commented_out_author_is_left_alone(self):
        src = '%\\icmlauthor{Ghost}{comp}\n\\section{Real}\n'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_a_command_with_too_few_arguments_is_left_alone(self):
        src = r'\icmlauthor{OnlyOne}'
        self.assertEqual(ab.unwrap_front_matter(src), (src, 0))

    def test_a_nested_brace_in_a_name_survives(self):
        got, _ = ab.unwrap_front_matter(
            r'\icmlauthor{Lorenz K. M\"{u}ller}{comp}')
        self.assertIn(r'Lorenz K. M\"{u}ller', got)


if __name__ == '__main__':
    unittest.main()
