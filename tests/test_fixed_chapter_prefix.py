# -*- coding: utf-8 -*-
r"""One chapter of a book, shipped alone, numbers everything `5.x`.

randmat is `\documentclass{book}` with `\setcounter{chapter}{5}` just before
its first section and no `\chapter{}` anywhere. Its own text says
"Theorem 5.39", "Section 5.4.3", "(5.25)" — 258 dotted references and not one
plain — while this pipeline had nothing that could produce the `5` and printed
every number flat. `source_probe`: 0 agree, 157 disagree.

The `5` is in the source, not only in the PDF. The guard is what keeps it
honest: a document that really uses `\chapter{}` has a prefix that moves, and
pinning it to whatever `\setcounter` last said would be worse than leaving it
flat. So the prefix applies only when the counter is set and never advanced.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class TheFixedPrefixIsRead(unittest.TestCase):
    def test_a_counter_set_and_never_advanced(self):
        self.assertEqual(
            mb.read_fixed_counter_prefix(
                r'\setcounter{chapter}{5}' '\n' r'\section{Intro}'),
            {'chapter': '5'})

    def test_a_counter_whose_command_is_used_is_not_pinned(self):
        tex = (r'\setcounter{chapter}{5}' '\n'
               r'\chapter{Real}' '\n' r'\section{Intro}')
        self.assertNotIn('chapter', mb.read_fixed_counter_prefix(tex))

    def test_no_setcounter_means_nothing(self):
        self.assertEqual(mb.read_fixed_counter_prefix(r'\section{Intro}'), {})

    def test_whitespace_inside_the_call_is_tolerated(self):
        self.assertEqual(
            mb.read_fixed_counter_prefix(r'\setcounter { chapter } { 5 }'),
            {'chapter': '5'})


class TheLabelCarriesIt(unittest.TestCase):
    def test_a_chapter_scoped_theorem(self):
        self.assertEqual(
            mb._counter_label('theorem', 44, {'theorem': 'chapter'}, '',
                              {'chapter': '5'}),
            '5.44')

    def test_a_section_scope_still_wins(self):
        self.assertEqual(
            mb._counter_label('thrm', 1, {'thrm': 'section'}, '4',
                              {'chapter': '5'}),
            '4.1')

    def test_no_parent_stays_flat(self):
        self.assertEqual(
            mb._counter_label('theorem', 44, {}, '', {'chapter': '5'}), '44')

    def test_a_parent_with_no_fixed_value_stays_flat(self):
        self.assertEqual(
            mb._counter_label('theorem', 44, {'theorem': 'chapter'}, '', {}),
            '44')


class SectionsCarryItToo(unittest.TestCase):
    def make(self, tex):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with io.open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(tex)
        return d

    def test_a_section_reference_gets_the_chapter(self):
        # randmat's own text writes "Section 5.4.3" and never "Section 4.3".
        d = self.make(r'\newtheorem{theorem}{Theorem}[chapter]' '\n'
                      r'\begin{document}' '\n'
                      r'\setcounter{chapter}{5}' '\n'
                      r'\section{A}\label{s:a}' '\n'
                      r'\subsection{B}\label{s:b}' '\n'
                      r'\end{document}' '\n')
        index = mb.build_label_index(d)
        self.assertEqual(index['s:a'], ('5.1', 'section'))
        self.assertEqual(index['s:b'], ('5.1.1', 'section'))

    def test_without_the_setcounter_the_section_stays_plain(self):
        d = self.make(r'\begin{document}' '\n'
                      r'\section{A}\label{s:a}' '\n'
                      r'\end{document}' '\n')
        self.assertEqual(mb.build_label_index(d)['s:a'], ('1', 'section'))

    def test_an_appendix_letter_is_not_prefixed(self):
        d = self.make(r'\begin{document}' '\n'
                      r'\setcounter{chapter}{5}' '\n'
                      r'\section{A}\label{s:a}' '\n'
                      r'\appendix' '\n'
                      r'\section{B}\label{s:b}' '\n'
                      r'\end{document}' '\n')
        index = mb.build_label_index(d)
        self.assertEqual(index['s:a'], ('5.1', 'section'))
        self.assertEqual(index['s:b'], ('A', 'section'))


if __name__ == '__main__':
    unittest.main()
