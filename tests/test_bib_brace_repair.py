# -*- coding: utf-8 -*-
r"""BibTeX and pandoc disagree about `\}`, and the paper is right.

BibTeX does not treat a backslash as escaping a brace: it counts `{` and `}`
and nothing else. pandoc's reader follows the LaTeX convention, where `\}` is
a literal brace. So a `.bib` can be valid to the program it was written for
and unreadable to ours.

One paper ends a field with an escaped brace where the closer belonged.
BibTeX closes the field there, which is why the paper builds on arXiv. pandoc
never closes the entry, meets the next `@` and exits 25, taking the whole
conversion with it, on a paper whose body cites 22 keys that live only in
that file (KNOWLEDGE.md K145). Repairing it by hand did not survive, because
the work directory is re-unpacked before every run.

Measured against the installed pandoc, on the real file:

    as shipped                    exit 25, "Error reading bibliography file"
    one backslash dropped         exit 0, the entry renders correctly

The repair drops a backslash BibTeX was already ignoring, so the file still
says the same thing to the program it was written for.
"""
from __future__ import unicode_literals

import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

BROKEN = (
    '@PhdThesis{one,\n'
    '  Author = {A. Writer},\n'
    '  School = {A University in a Town i.\\ Br.\\},\n'
    '  Year = {1999}\n'
    '}\n'
    '\n'
    '@Article{two,\n'
    '  Author = {B. Writer},\n'
    '  Title = {A perfectly ordinary title},\n'
    '  Year = {2000}\n'
    '}\n')

CLEAN = (
    '@Article{two,\n'
    '  Author = {B. Writer},\n'
    '  Title = {A perfectly ordinary title},\n'
    '  Year = {2000}\n'
    '}\n')

# A brace the author really did want printed, in an entry that closes fine.
LITERAL_BRACE = (
    '@Article{three,\n'
    '  Title = {On the set \\{a, b\\} and its friends},\n'
    '  Year = {2001}\n'
    '}\n')


class RepairingWhatPandocCannotRead(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='bibrepair-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, text, name='refs.bib'):
        path = os.path.join(self.dir, name)
        with io.open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
        return path

    def read(self, path):
        with io.open(path, encoding='utf-8') as fh:
            return fh.read()

    def test_the_broken_entry_is_closed(self):
        path = self.write(BROKEN)
        self.assertEqual(ab.repair_bib_braces(path), 1)
        text = self.read(path)
        self.assertIn('i.\\ Br.},', text)
        self.assertNotIn('Br.\\},', text)

    def test_the_entry_after_it_is_untouched(self):
        """The next entry is what pandoc collided with; it was never at fault."""
        path = self.write(BROKEN)
        ab.repair_bib_braces(path)
        self.assertIn('A perfectly ordinary title', self.read(path))

    def test_a_clean_file_is_not_rewritten(self):
        path = self.write(CLEAN)
        before = self.read(path)
        self.assertEqual(ab.repair_bib_braces(path), 0)
        self.assertEqual(self.read(path), before)

    def test_a_deliberate_literal_brace_survives(self):
        r"""`\{a, b\}` is a set the author wanted printed, in an entry that
        closes. Nothing here may touch it."""
        path = self.write(LITERAL_BRACE)
        self.assertEqual(ab.repair_bib_braces(path), 0)
        self.assertIn('\\{a, b\\}', self.read(path))

    def test_running_twice_changes_nothing_the_second_time(self):
        path = self.write(BROKEN)
        self.assertEqual(ab.repair_bib_braces(path), 1)
        after = self.read(path)
        self.assertEqual(ab.repair_bib_braces(path), 0)
        self.assertEqual(self.read(path), after)

    def test_an_entry_it_cannot_close_is_left_alone(self):
        """A file this cannot fix is one to report, not to guess at."""
        hopeless = '@Article{x,\n  Title = {no closer at all\n'
        path = self.write(hopeless)
        self.assertEqual(ab.repair_bib_braces(path), 0)
        self.assertEqual(self.read(path), hopeless)

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(
            ab.repair_bib_braces(os.path.join(self.dir, 'nope.bib')), 0)


class BraceCounting(unittest.TestCase):
    """The two readings, which is the whole of the problem."""

    def test_bibtex_closes_on_an_escaped_brace(self):
        text = '{a \\} b'          # index 3 is the backslash, 4 the brace
        self.assertEqual(ab._closes_at(text, 0, escaped=False), 4)
        self.assertEqual(text[4], '}')

    def test_pandoc_does_not(self):
        text = '{a \\} b'
        self.assertEqual(ab._closes_at(text, 0, escaped=True), -1)

    def test_both_agree_on_an_ordinary_group(self):
        text = '{a {b} c}'
        self.assertEqual(ab._closes_at(text, 0, escaped=True), len(text) - 1)
        self.assertEqual(ab._closes_at(text, 0, escaped=False), len(text) - 1)


if __name__ == '__main__':
    unittest.main()
