# -*- coding: utf-8 -*-
r"""Floats an appendix letters by hand.

A paper can scope its float counter to the section, and `float_units` already
reads that. It can also just declare the lettering: VLA-Adapter gives each of
its nine appendix sections a `\renewcommand{\thefigure}{A\arabic{figure}}`
and a `\setcounter{figure}{0}`, so what it prints as Figure A1 is that
counter's ninth figure.

Numbering straight through sent seventeen cross-references at the wrong
float, and every internal check passed: the book was self-consistent, the
counts agreed, and only `source_probe`, which reads the number off the
original PDF, could see it.

The rule is to read what the source declares, never to evaluate TeX. A
declaration this module cannot read plainly is left alone.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


def figure(label):
    return ('\\begin{figure}\n\\includegraphics{x.png}\n'
            '\\caption{C}\\label{%s}\n\\end{figure}\n' % label)


def table(label):
    return ('\\begin{table}\n\\begin{tabular}{c}a\\end{tabular}\n'
            '\\caption{C}\\label{%s}\n\\end{table}\n' % label)


def numbers(tex):
    return {l: u['number'] for u in mb.float_units(tex) for l in u['labels']}


class CounterEvents(unittest.TestCase):

    def test_a_prefix_declaration_is_read(self):
        events = mb.counter_events(
            r'\renewcommand{\thefigure}{A\arabic{figure}}')
        self.assertEqual(events, [(0, 'figure', 'prefix', 'A')])

    def test_a_reset_is_read(self):
        events = mb.counter_events(r'\setcounter{table}{0}')
        self.assertEqual(events, [(0, 'table', 'set', 0)])

    def test_a_prefix_that_is_itself_a_command_is_skipped(self):
        r"""`\Alph{section}\arabic{figure}` needs the section counter
        evaluated. Reading the source is the contract; running TeX is not."""
        self.assertEqual(mb.counter_events(
            r'\renewcommand{\thefigure}{\Alph{section}\arabic{figure}}'), [])

    def test_a_declaration_without_arabic_is_skipped(self):
        self.assertEqual(mb.counter_events(
            r'\renewcommand{\thefigure}{\roman{figure}}'), [])

    def test_events_come_back_in_source_order(self):
        tex = (r'\setcounter{figure}{0}'
               r'\renewcommand{\thefigure}{B\arabic{figure}}')
        self.assertEqual([e[2] for e in mb.counter_events(tex)],
                         ['set', 'prefix'])


class AppendixNumbering(unittest.TestCase):

    def test_the_body_is_unchanged_by_a_later_declaration(self):
        tex = (figure('body1') + figure('body2')
               + r'\appendix' + '\n'
               + r'\renewcommand{\thefigure}{A\arabic{figure}}' + '\n'
               + r'\setcounter{figure}{0}' + '\n'
               + figure('app1'))
        got = numbers(tex)
        self.assertEqual(got['body1'], 1)
        self.assertEqual(got['body2'], 2)
        self.assertEqual(got['app1'], 'A1')

    def test_each_appendix_section_restarts_with_its_own_letter(self):
        tex = (figure('body1')
               + r'\renewcommand{\thefigure}{A\arabic{figure}}\setcounter'
                 r'{figure}{0}' + '\n' + figure('a1') + figure('a2')
               + r'\renewcommand{\thefigure}{B\arabic{figure}}\setcounter'
                 r'{figure}{0}' + '\n' + figure('b1'))
        got = numbers(tex)
        self.assertEqual([got['body1'], got['a1'], got['a2'], got['b1']],
                         [1, 'A1', 'A2', 'B1'])

    def test_figures_and_tables_are_lettered_apart(self):
        tex = (r'\renewcommand{\thefigure}{B\arabic{figure}}'
               r'\renewcommand{\thetable}{B\arabic{table}}'
               r'\setcounter{figure}{0}\setcounter{table}{0}' + '\n'
               + figure('f') + table('t'))
        got = numbers(tex)
        self.assertEqual((got['f'], got['t']), ('B1', 'B1'))

    def test_a_paper_that_declares_nothing_is_untouched(self):
        """The guard that matters: every other paper must number as before."""
        tex = figure('a') + table('b') + figure('c')
        self.assertEqual(numbers(tex), {'a': 1, 'b': 1, 'c': 2})

    def test_a_reset_without_a_prefix_still_restarts_the_count(self):
        tex = figure('a') + r'\setcounter{figure}{0}' + '\n' + figure('b')
        got = numbers(tex)
        self.assertEqual((got['a'], got['b']), (1, 1))


if __name__ == '__main__':
    unittest.main()
