# -*- coding: utf-8 -*-
r"""Counters scoped to a section, and the four places that must agree.

Shor 1995 prints `(2.1)` and `Table 3.1`. Nothing in the pipeline read either
signal, so all 29 cross-references named a number the paper does not print --
and the mismatch was very nearly accepted as a limit of the supported subset.
It was not: the number on an equation or a float is stamped by this pipeline,
so it was ours to choose all along. Only theorem-likes are numbered by pandoc
and stay out of reach (K113).

The dangerous part is not the numbering. It is that the index, the float
walker, the markdown tagger, the HTML tagger and the link builder must all
agree, and a disagreement between them is silent: an anchor that is never
created and a reference that points at nothing raise nothing at all (K80).
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class ReadCounterParents(unittest.TestCase):
    def test_def_the_naming_another_counter(self):
        tex = (r'\def\theequation{\thesection.\arabic{equation}}'
               '\n\\begin{document}\n')
        self.assertEqual(mb.read_counter_parents(tex),
                         {'equation': 'section'})

    def test_renewcommand_form(self):
        tex = (r'\renewcommand{\thefigure}{\thesection.\arabic{figure}}'
               '\n\\begin{document}\n')
        self.assertEqual(mb.read_counter_parents(tex), {'figure': 'section'})

    def test_counterwithin_and_numberwithin(self):
        tex = ('\\counterwithin{equation}{section}\n'
               '\\numberwithin{table}{chapter}\n\\begin{document}\n')
        self.assertEqual(mb.read_counter_parents(tex),
                         {'equation': 'section', 'table': 'chapter'})

    def test_printing_arabic_names_no_parent(self):
        # `\def\theequation{\arabic{equation}}` says how to print, not what to
        # print in front. Reading it as a parent would prefix every number
        # with itself.
        tex = r'\def\theequation{\arabic{equation}}' '\n\\begin{document}\n'
        self.assertEqual(mb.read_counter_parents(tex), {})

    def test_a_paper_that_says_nothing(self):
        self.assertEqual(mb.read_counter_parents('\\begin{document}\nx\n'), {})

    def test_only_the_preamble_is_read(self):
        tex = ('\\begin{document}\n'
               r'\def\theequation{\thesection.\arabic{equation}}' '\n')
        self.assertEqual(mb.read_counter_parents(tex), {})


class CounterLabel(unittest.TestCase):
    def test_scoped_counter_carries_the_section(self):
        self.assertEqual(
            mb._counter_label('equation', 1, {'equation': 'section'}, '2'),
            '2.1')

    def test_unscoped_counter_is_unchanged(self):
        self.assertEqual(mb._counter_label('equation', 7, {}, '2'), '7')

    def test_before_the_first_section_there_is_no_prefix(self):
        self.assertEqual(
            mb._counter_label('equation', 1, {'equation': 'section'}, ''), '1')


class LabelIndexNumbersWithinSections(unittest.TestCase):
    def _index(self, tex):
        d = tempfile.mkdtemp(prefix='tb-counter-')
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(tex)
        return mb.build_label_index(d)

    def test_equations_restart_and_carry_the_section(self):
        tex = (r'\def\theequation{\thesection.\arabic{equation}}'
               '\n\\begin{document}\n'
               '\\section{One}\n'
               '\\begin{equation}\\label{a}x\\end{equation}\n'
               '\\begin{equation}\\label{b}y\\end{equation}\n'
               '\\section{Two}\n'
               '\\begin{equation}\\label{c}z\\end{equation}\n')
        idx = self._index(tex)
        self.assertEqual(idx['a'], ('1.1', 'equation'))
        self.assertEqual(idx['b'], ('1.2', 'equation'))
        self.assertEqual(idx['c'], ('2.1', 'equation'))

    def test_a_flat_paper_is_untouched(self):
        tex = ('\\begin{document}\n\\section{One}\n'
               '\\begin{equation}\\label{a}x\\end{equation}\n'
               '\\section{Two}\n'
               '\\begin{equation}\\label{b}y\\end{equation}\n')
        idx = self._index(tex)
        self.assertEqual(idx['a'], ('1', 'equation'))
        self.assertEqual(idx['b'], ('2', 'equation'))

    def test_a_starred_section_numbers_nothing(self):
        tex = (r'\def\theequation{\thesection.\arabic{equation}}'
               '\n\\begin{document}\n'
               '\\section{One}\n'
               '\\section*{Unnumbered}\n'
               '\\begin{equation}\\label{a}x\\end{equation}\n')
        self.assertEqual(self._index(tex)['a'], ('1.1', 'equation'))


class EquationNumbersFromTheSource(unittest.TestCase):
    # Plain `$$...$$` is UNNUMBERED in LaTeX and takes no number here either,
    # so a numbered block has to carry the environment that numbers it.
    NUMBERED = ('$$\\begin{equation}\na\n\\end{equation}$$\n\ntext\n\n'
                '$$\\begin{equation}\nb\n\\end{equation}$$\n')

    def test_supplied_strings_replace_the_flat_count(self):
        got = [n for _s, _e, n in
               mb.equation_numbers(self.NUMBERED, ['2.1', '2.2'])]
        self.assertEqual(got, ['2.1', '2.2'])

    def test_a_length_mismatch_is_refused_rather_than_guessed(self):
        # Two views disagreeing about how many numbers exist must not be
        # reconciled by lining them up from the left: that misnumbers the rest
        # of the book and nothing would say so.
        got = [n for _s, _e, n in mb.equation_numbers(self.NUMBERED, ['2.1'])]
        self.assertEqual(got, [1, 2])

    def test_no_strings_keeps_todays_behaviour(self):
        self.assertEqual(
            [n for _s, _e, n in mb.equation_numbers(self.NUMBERED)], [1, 2])

    def test_plain_display_math_takes_no_number(self):
        md = '$$\na\n$$\n'
        self.assertEqual([n for _s, _e, n in mb.equation_numbers(md)], [None])

    def test_flat_paper_yields_no_override(self):
        d = tempfile.mkdtemp(prefix='tb-flateq-')
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write('\\begin{document}\n\\begin{equation}x\\end{equation}\n')
        self.assertIsNone(mb.flat_equation_numbers(d))


class DottedNumbersReachTheAnchors(unittest.TestCase):
    """The silent half: an id that is never created (K80)."""

    def test_math_eqno_regex_accepts_a_dotted_number(self):
        html = '<math display="block" data-eqno="(2.1)">x</math>'
        m = mb._MATH_EQNO_RE.search(html)
        self.assertIsNotNone(m, 'a section-scoped equation got no anchor')
        self.assertEqual(m.group(2), '2.1')

    def test_math_eqno_regex_still_accepts_a_plain_number(self):
        m = mb._MATH_EQNO_RE.search('<math data-eqno="(7)">x</math>')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), '7')


if __name__ == '__main__':
    unittest.main()
