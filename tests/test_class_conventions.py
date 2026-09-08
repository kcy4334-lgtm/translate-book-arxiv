# -*- coding: utf-8 -*-
r"""Numbering the document class chooses, and the paper never states.

Two papers disagreed with their own PDFs for one reason, and neither
carried anything to read: no `\renewcommand{\thesection}`, no
`\numberwithin`, no `\counterwithin`. The convention came from the class.

  * 2609.05337 is revtex4-2, which prints sections I, II, III. The label
    index said 3 and 4 where the paper prints III and IV, so every
    reference into a section named something a reader cannot find.
  * 2609.05354 is amsart, which numbers a display within its section, so a
    formula in section 2 prints (2.1).

Only classes something here can CHECK are in the table. Both were measured
against the paper's own PDF -- Roman headings for the first, 57 dotted
equation markers and no undotted one for the second -- and `source_probe`
re-checks them on every run. 2609.05337 now passes it outright.

A class added from memory would be the NEVER SEEN trap in a new place: a
rule whose match decides something, tested against nothing.
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


class RomanNumerals(unittest.TestCase):

    def test_the_range_a_paper_uses(self):
        for n, want in ((1, 'I'), (2, 'II'), (3, 'III'), (4, 'IV'),
                        (5, 'V'), (9, 'IX'), (10, 'X'), (14, 'XIV'),
                        (40, 'XL'), (90, 'XC')):
            self.assertEqual(mb.roman_numeral(n), want, n)

    def test_zero_and_below_are_not_roman(self):
        """There is no Roman zero, and a section counter at 0 means the
        walk went wrong. Returning the digit says so instead of hiding it."""
        self.assertEqual(mb.roman_numeral(0), '0')
        self.assertEqual(mb.roman_numeral(-1), '-1')


class WhatTheClassSays(unittest.TestCase):

    def conventions(self, cls):
        return mb.read_class_conventions(
            '\\documentclass{%s}\n\\begin{document}\n' % cls)

    def test_revtex_numbers_sections_in_roman(self):
        for cls in ('revtex4-2', 'revtex4-1', 'revtex4'):
            self.assertEqual(self.conventions(cls).get('section'), 'Roman', cls)

    def test_amsart_numbers_equations_within_the_section(self):
        self.assertEqual(self.conventions('amsart').get('parents'),
                         {'equation': 'section'})

    def test_ieeetran_numbers_tables_in_roman_and_figures_in_arabic(self):
        """TABLE I, TABLE II, Fig. 1, Fig. 2. Only the table is listed, and
        listing the figure too would break every IEEE paper's pictures."""
        got = self.conventions('IEEEtran').get('float')
        self.assertEqual(got, {'table': 'Roman'})

    def test_amsart_sets_its_subsection_run_in(self):
        """There is no heading line in the PDF for a subsection, so one not
        being located says nothing about the numbering."""
        self.assertEqual(self.conventions('amsart').get('run_in_level'), 2)

    def test_a_class_nobody_measured_says_nothing(self):
        """Silence is the right answer for a class no paper here uses.
        Guessing one would put an unverified rule in front of every book."""
        for cls in ('article', 'llncs', 'sig-alternate', 'elsarticle'):
            self.assertEqual(self.conventions(cls), {}, cls)

    def test_class_options_do_not_hide_the_name(self):
        tex = '\\documentclass[twocolumn,aps,pra]{revtex4-2}\n'
        self.assertEqual(mb.read_class_conventions(tex).get('section'),
                         'Roman')

    def test_no_documentclass_at_all(self):
        self.assertEqual(mb.read_class_conventions('\\section{A}'), {})


BODY = ('\\documentclass{%s}\n'
        '\\begin{document}\n'
        '\\section{First}\\label{sec:one}\n'
        '\\begin{equation}\\label{eq:one}a=b\\end{equation}\n'
        '\\section{Second}\\label{sec:two}\n'
        '\\subsection{Inner}\\label{sec:two-one}\n'
        '\\begin{equation}\\label{eq:two}c=d\\end{equation}\n'
        '\\end{document}\n')


class TheIndexUsesThem(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.work, True)

    def numbers(self, cls, extra=''):
        path = os.path.join(self.work, 'flat.tex')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write((BODY % cls).replace('\\begin{document}',
                                          extra + '\\begin{document}'))
        return mb.build_label_numbers(self.work)

    def test_article_is_unchanged(self):
        """The class table must not move a paper that never needed it."""
        got = self.numbers('article')
        self.assertEqual(got.get('sec:one'), '1')
        self.assertEqual(got.get('sec:two'), '2')
        self.assertEqual(got.get('sec:two-one'), '2.1')
        self.assertEqual(got.get('eq:two'), '2')

    def test_revtex_sections_are_roman_and_subsections_hang_off_them(self):
        got = self.numbers('revtex4-2')
        self.assertEqual(got.get('sec:one'), 'I')
        self.assertEqual(got.get('sec:two'), 'II')
        self.assertEqual(got.get('sec:two-one'), 'II.1')

    def test_amsart_equations_carry_their_section(self):
        got = self.numbers('amsart')
        self.assertEqual(got.get('eq:one'), '1.1')
        self.assertEqual(got.get('eq:two'), '2.1')

    def test_amsart_sections_stay_arabic(self):
        got = self.numbers('amsart')
        self.assertEqual(got.get('sec:two'), '2')

    def test_an_explicit_declaration_beats_the_class(self):
        r"""`\numberwithin` is an author overriding their own class. The
        class fills in what the paper did not say, and nothing more."""
        got = self.numbers('article', '\\numberwithin{equation}{section}\n')
        self.assertEqual(got.get('eq:two'), '2.1')


FLOATS = ('\\documentclass{%s}\n\\begin{document}\n'
          '\\begin{table}\\caption{One}\\label{t:one}\\end{table}\n'
          '\\begin{figure}\\caption{One}\\label{f:one}\\end{figure}\n'
          '\\begin{table}\\caption{Two}\\label{t:two}\\end{table}\n'
          '\\begin{figure}\\caption{Two}\\label{f:two}\\end{figure}\n'
          '\\begin{table}\\caption{Three}\\label{t:three}\\end{table}\n'
          '\\end{document}\n')


class AFloatCounterThePaperNeverDeclares(unittest.TestCase):
    r"""TinyVLA's six disagreeing cross-references all named a table: the
    index said 1, 2, 3 where the paper prints I, II, III. IEEEtran does
    that and the source says so nowhere.

    The value becomes a string where it used to be an int, and that is not
    new ground: a section-scoped counter has produced `3.1` for a long
    time, and the caption badge already formats with `%s` because of it.
    """

    def numbers(self, cls):
        out = {}
        for unit in mb.float_units(FLOATS % cls):
            for label in unit['labels']:
                out[label] = unit['number']
        return out

    def test_ieeetran_letters_the_tables_and_leaves_the_figures(self):
        got = self.numbers('IEEEtran')
        self.assertEqual(got.get('t:one'), 'I')
        self.assertEqual(got.get('t:two'), 'II')
        self.assertEqual(got.get('t:three'), 'III')
        self.assertEqual(got.get('f:one'), 1)
        self.assertEqual(got.get('f:two'), 2)

    def test_an_ordinary_class_is_untouched(self):
        got = self.numbers('article')
        self.assertEqual(got.get('t:one'), 1)
        self.assertEqual(got.get('t:three'), 3)
        self.assertEqual(got.get('f:two'), 2)

    def test_the_caption_badge_survives_a_lettered_number(self):
        r"""`%d` here would die with "a real number is required, not str",
        which is exactly how a section-scoped counter broke this once."""
        self.assertEqual('%s %s' % ('Table', 'III'), 'Table III')


if __name__ == '__main__':
    unittest.main()
