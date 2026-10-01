# -*- coding: utf-8 -*-
r"""The lookup layer over the two logs.

Together they passed 110 KB across 130-odd entries, and reading both to answer
one question costs more than the answer. Worse, the question that matters most
while editing code — "is there an entry about `_widen_to_float`?" — cannot be
asked of a symptom index at all.

`check` is here as much as the search is: an entry no index row reaches is
invisible, and writing it was wasted. An entry reached from SEVERAL rows is the
index doing its job — one cause shows up as more than one symptom — so that is
not a fault, and the first cut of this check wrongly said it was.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import kb

DOC = (
    'preamble\n\n'
    '| symptom | entry |\n'
    '|---|---|\n'
    '| a table lost its rows | [K1](#k1) |\n'
    '| a build prints OK and is wrong | [K1](#k1), [K2](#k2) |\n\n'
    '### K1\n'
    '**A cell can be a table.**\n'
    'Scanning for the first `\\end{tabular}` cut the outer table off.\n'
    '*Status: LOCKED — `tests/test_nested.py`.*\n'
    '---\n\n'
    'not part of any entry\n\n'
    '### K2\n'
    '**Something else entirely.**\n'
    'About `_widen_to_float` and nothing to do with tables.\n'
    '---\n')


class Parsing(unittest.TestCase):

    def setUp(self):
        self.entries = kb.parse(DOC, 'TEST.md')

    def test_every_entry_is_found(self):
        self.assertEqual([e['id'] for e in self.entries], ['K1', 'K2'])

    def test_the_title_is_the_first_line_without_its_emphasis(self):
        self.assertEqual(self.entries[0]['title'], 'A cell can be a table.')

    def test_the_body_stops_at_the_rule(self):
        """What follows the rule belongs to the file, not to the entry."""
        self.assertNotIn('not part of any entry', self.entries[0]['body'])

    def test_the_body_keeps_the_status_line(self):
        self.assertIn('Status: LOCKED', self.entries[0]['body'])

    def test_backticked_names_become_searchable_tokens(self):
        self.assertIn('tests/test_nested.py', self.entries[0]['tokens'])
        self.assertIn('\\end{tabular}', self.entries[0]['tokens'])


class Ranking(unittest.TestCase):

    def best(self, query):
        entries = kb.parse(DOC, 'TEST.md')
        scored = sorted(((kb.score(e, [query]), e) for e in entries),
                        key=lambda pair: -pair[0])
        return scored[0][1]['id'] if scored[0][0] else None

    def test_a_symbol_finds_the_entry_that_names_it(self):
        self.assertEqual(self.best('_widen_to_float'), 'K2')

    def test_a_word_in_the_title_outranks_the_same_word_in_a_body(self):
        self.assertEqual(self.best('cell'), 'K1')

    def test_an_id_finds_itself(self):
        self.assertEqual(self.best('k2'), 'K2')

    def test_a_word_in_neither_scores_nothing(self):
        self.assertIsNone(self.best('bibliography'))


class Index(unittest.TestCase):

    def test_rows_are_read_from_the_table(self):
        rows = [m for line in DOC.split('\n') if line.startswith('|')
                for m in kb._INDEX_ROW_RE.findall(line)]
        self.assertEqual(sorted(rows), ['K1', 'K1', 'K2'])

    def test_one_entry_under_two_symptoms_is_not_a_fault(self):
        rows = [m for line in DOC.split('\n') if line.startswith('|')
                for m in kb._INDEX_ROW_RE.findall(line)]
        self.assertEqual(rows.count('K1'), 2)
        ids = set(e['id'] for e in kb.parse(DOC, 'TEST.md'))
        self.assertEqual(set(rows) - ids, set())
        self.assertEqual(ids - set(rows), set())


class TheRealLogs(unittest.TestCase):
    """Runs against the shipped files, so drift fails the suite."""

    def test_every_entry_is_reachable_from_its_index(self):
        for name, _prefix in kb.SOURCES:
            entries = set(e['id'] for e in kb.parse(kb.read(name), name))
            rows = set(kb.index_rows(name))
            self.assertEqual(entries - rows, set(),
                             '%s: entries nobody can find' % name)

    def test_no_index_row_points_at_nothing(self):
        for name, _prefix in kb.SOURCES:
            entries = set(e['id'] for e in kb.parse(kb.read(name), name))
            self.assertEqual(set(kb.index_rows(name)) - entries, set(),
                             '%s: rows landing nowhere' % name)

    def test_there_are_entries_to_find(self):
        self.assertGreater(len(kb.load()), 50)


if __name__ == '__main__':
    unittest.main()
