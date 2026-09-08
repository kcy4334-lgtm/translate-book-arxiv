# -*- coding: utf-8 -*-
r"""An appendix opened as an ENVIRONMENT still letters its sections.

`\appendix` is a command that switches the section counter from 1, 2, 3 to
A, B, C, and the label index has read it for a long time. The appendix
package offers the same thing as an environment, `\begin{appendix}` or
`\begin{appendices}`, and a paper that uses one does not also write the
other. Nothing here matched the environment.

Found by running a real paper rather than reasoning about one. 2609.05354
opens its appendix with `\begin{appendix}` and carries no `\appendix`
anywhere, so its appendix sections numbered 11 and 11.5 where the paper
prints A and A.5, and every `\ref` into them followed the wrong number.
`source_probe` went from four disagreeing cross-references to one.

Both spellings share ONE capture group in `_label_token_re`, because the
branches after it are read by position and a new group would renumber all
of them. That is the sort of change a test should hold down, so the group
count is asserted here too.
"""
from __future__ import unicode_literals

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402

BODY = ('\\section{First}\\label{sec:one}\n'
        '\\section{Second}\\label{sec:two}\n'
        '%s\n'
        '\\section{Proofs}\\label{app:a}\n'
        '\\subsection{A lemma}\\label{app:a1}\n'
        '\\section{Extra}\\label{app:b}\n')


class AppendixNumbering(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.work, True)

    def index(self, opener):
        path = os.path.join(self.work, 'flat.tex')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(BODY % opener)
        return mb.build_label_numbers(self.work)

    def assert_lettered(self, opener):
        got = self.index(opener)
        self.assertEqual(got.get('sec:one'), '1', opener)
        self.assertEqual(got.get('sec:two'), '2', opener)
        self.assertEqual(got.get('app:a'), 'A', opener)
        self.assertEqual(got.get('app:a1'), 'A.1', opener)
        self.assertEqual(got.get('app:b'), 'B', opener)

    def test_the_command_still_works(self):
        """The path that was already right. Kept because the regex that
        reads it was rewritten to read the environment as well."""
        self.assert_lettered('\\appendix')

    def test_the_appendix_environment(self):
        """The measured one."""
        self.assert_lettered('\\begin{appendix}')

    def test_the_appendices_environment(self):
        """The appendix package's plural spelling."""
        self.assert_lettered('\\begin{appendices}')

    def test_whitespace_before_the_brace(self):
        self.assert_lettered('\\begin {appendix}')

    def test_without_an_appendix_the_sections_stay_arabic(self):
        got = self.index('')
        self.assertEqual(got.get('app:a'), '3')
        self.assertEqual(got.get('app:a1'), '3.1')
        self.assertEqual(got.get('app:b'), '4')

    def test_closing_the_environment_does_not_restore_arabic(self):
        r"""A decision, not an oversight. `\appendix` is one-way, an
        appendix is the last thing in a paper, and no paper measured here
        has sections after `\end{appendix}`. Restoring the counter would
        also have to restore its VALUE, which nothing records."""
        path = os.path.join(self.work, 'flat.tex')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\\section{First}\\label{sec:one}\n'
                     '\\begin{appendix}\n'
                     '\\section{Proofs}\\label{app:a}\n'
                     '\\end{appendix}\n'
                     '\\section{After}\\label{sec:after}\n')
        got = mb.build_label_numbers(self.work)
        self.assertEqual(got.get('app:a'), 'A')
        self.assertEqual(got.get('sec:after'), 'B')


class TheScannerKeptItsShape(unittest.TestCase):
    r"""`_label_token_re` reads its branches by position: group 2 is the
    `sub` run of a `\section`, group 3 its star, and so on down. Adding a
    capture for the environment spelling would have renumbered every one
    of them, and the failure would have been silent -- a number attached
    to the wrong kind of thing."""

    def test_both_spellings_share_one_group(self):
        pattern = mb._label_token_re(mb._DEFAULT_THEOREM_ENVS)
        for text, expected in (('\\appendix', 'appendix'),
                               ('\\begin{appendix}', 'begin{appendix}'),
                               ('\\begin{appendices}', 'begin{appendices}')):
            m = pattern.search(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(m.group(1), expected)

    def test_a_section_still_lands_in_groups_two_and_three(self):
        pattern = mb._label_token_re(mb._DEFAULT_THEOREM_ENVS)
        m = pattern.search('\\subsection*{Title}')
        self.assertEqual(m.group(2), 'sub')
        self.assertEqual(m.group(3), '*')

    def test_a_longer_command_is_not_an_appendix(self):
        r"""`\appendixname` is the word "Appendix", not the switch."""
        pattern = mb._label_token_re(mb._DEFAULT_THEOREM_ENVS)
        m = pattern.search('\\appendixname')
        self.assertTrue(m is None or m.group(1) is None)


if __name__ == '__main__':
    unittest.main()
