# -*- coding: utf-8 -*-
r"""A `\ref` inside a table caption.

Table floats are protected behind a placeholder so the translator never sees
`\caption{}`, which also means they never meet `resolve_references`. Their
`\ref` calls therefore reach pandoc untouched, and pandoc prints the key:
VLA-Adapter shipped twenty captions reading `[TableD1]`, `[AppendixG]`,
`[Figure_LIBERO]` -- each one a pointer the reader is invited to follow and
cannot.

Two decisions are worth keeping, and the tests below are what hold them:

Only the number is substituted. Every one of those twenty already had a
Korean label word in front of it, written by the translator, so supplying
another would print `그림 그림 A1`; and a section key would force a choice
between 부록 and 절 that this code has no way to make correctly.

The number comes from the index, never from the key. This paper labels its
appendix H `AppendixG`. Reading the letter off the key name would print a
confident, wrong, unfalsifiable G.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

NUMBERS = {'TableD1': 'D1', 'AppendixG': 'H', 'Figure_LIBERO': '7'}


class SubstitutingTheNumber(unittest.TestCase):

    def test_the_key_is_replaced_by_the_number_alone(self):
        out, done, missed = mb.resolve_fragment_references(
            r'\caption{표 \ref{TableD1}의 결과}', NUMBERS)
        self.assertEqual(out, r'\caption{표 D1의 결과}')
        self.assertEqual(done, 1)
        self.assertEqual(missed, [])

    def test_no_label_word_is_supplied(self):
        """The translator's word stays the only one on the page."""
        out, _done, _missed = mb.resolve_fragment_references(
            r'그림 \ref{Figure_LIBERO}', NUMBERS)
        self.assertEqual(out, '그림 7')
        self.assertEqual(out.count('그림'), 1)

    def test_the_index_wins_over_the_key_name(self):
        r"""`AppendixG` prints H. Anything that reads the letter off the key
        is wrong here and cannot be caught by looking at the page."""
        out, _done, _missed = mb.resolve_fragment_references(
            r'부록 \ref{AppendixG} 참고', NUMBERS)
        self.assertIn('부록 H', out)
        self.assertNotIn('G', out)

    def test_an_unknown_key_is_left_visible(self):
        """A raw key can be reported and fixed. A guessed number cannot be
        noticed at all."""
        tex = r'표 \ref{NeverDeclared}'
        out, done, missed = mb.resolve_fragment_references(tex, NUMBERS)
        self.assertEqual(out, tex)
        self.assertEqual(done, 0)
        self.assertEqual(missed, ['NeverDeclared'])

    def test_several_in_one_caption_are_counted_separately(self):
        out, done, missed = mb.resolve_fragment_references(
            r'\ref{TableD1}, \ref{Figure_LIBERO}, \ref{Gone}', NUMBERS)
        self.assertEqual(out, 'D1, 7, ' + r'\ref{Gone}')
        self.assertEqual(done, 2)
        self.assertEqual(missed, ['Gone'])

    def test_spacing_between_the_command_and_the_brace(self):
        out, done, _missed = mb.resolve_fragment_references(
            r'\ref {TableD1}', NUMBERS)
        self.assertEqual(out, 'D1')
        self.assertEqual(done, 1)

    def test_an_empty_map_changes_nothing(self):
        tex = r'표 \ref{TableD1}'
        self.assertEqual(mb.resolve_fragment_references(tex, {}),
                         (tex, 0, ['TableD1']))

    def test_the_cell_separators_are_not_disturbed(self):
        tex = r'A & \ref{TableD1} & 90.6 \\'
        out, _done, _missed = mb.resolve_fragment_references(tex, NUMBERS)
        self.assertEqual(out.count('&'), tex.count('&'))
        self.assertTrue(out.endswith(r'\\'))


class WhereTheNumbersComeFrom(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, body):
        with io.open(os.path.join(self.dir, 'flat.tex'), 'w',
                     encoding='utf-8') as fh:
            fh.write(body)

    def test_a_float_label_resolves_to_its_number(self):
        self.write('\n'.join([
            r'\begin{document}',
            r'\begin{table}\caption{One}\label{TableOne}\end{table}',
            r'\begin{table}\caption{Two}\label{TableTwo}\end{table}',
            r'\end{document}']))
        numbers = mb.fragment_reference_numbers(self.dir)
        self.assertEqual(numbers.get('TableTwo'), '2')

    def test_a_section_label_resolves_too(self):
        self.write('\n'.join([
            r'\begin{document}',
            r'\section{First}\label{Section_intro}',
            r'\section{Second}\label{Section_method}',
            r'\end{document}']))
        numbers = mb.fragment_reference_numbers(self.dir)
        self.assertEqual(numbers.get('Section_method'), '2')

    def test_a_colon_in_a_label_is_part_of_the_name(self):
        r"""`eq:main` and `tab:main` are two labels, not one.

        The colon in `\label{eq:pqe}` is how authors namespace their labels;
        it is not a kind prefix the index adds. A first version registered
        the tail as well, so both of these would have answered to `main` and
        one would have silently won -- printing the equation's number under
        the table's name, or the reverse, with nothing on the page to show
        which. `\ref` always writes the label in full, so the tail is not
        needed for anything.
        """
        self.write('\n'.join([
            r'\begin{document}',
            r'\section{First}\label{sec:main}',
            r'\begin{table}\caption{T}\label{tab:main}\end{table}',
            r'\end{document}']))
        numbers = mb.fragment_reference_numbers(self.dir)
        self.assertIn('sec:main', numbers)
        self.assertIn('tab:main', numbers)
        self.assertNotIn('main', numbers)

    def test_every_number_is_a_string(self):
        """The float builder returns ints and the label index strings. A
        caller that formats the map, or compares against one, should not
        have to know which side an entry came from."""
        self.write('\n'.join([
            r'\begin{document}',
            r'\section{S}\label{sec:one}',
            r'\begin{table}\caption{T}\label{tab:one}\end{table}',
            r'\end{document}']))
        numbers = mb.fragment_reference_numbers(self.dir)
        self.assertTrue(numbers)
        for key, value in numbers.items():
            self.assertIsInstance(value, str, key)

    def test_no_temp_dir_gives_an_empty_map(self):
        r"""`expand_raw_latex_tables` is called with `temp_dir=None` by four
        existing tests and by any caller holding only markdown.
        `build_label_index` joins the path without checking, so the guard
        belongs here -- it was missing for one build and took the suite from
        1634 passing to five errors."""
        self.assertEqual(mb.fragment_reference_numbers(None), {})
        self.assertEqual(mb.fragment_reference_numbers(''), {})
        self.assertEqual(
            mb.fragment_reference_numbers(
                os.path.join(self.dir, 'does-not-exist')), {})

    def test_a_temp_dir_with_no_source_is_harmless(self):
        self.assertEqual(mb.fragment_reference_numbers(self.dir), {})


class EndToEndThroughAFloat(unittest.TestCase):
    """The wiring: a caption reaching the expander must come out numbered."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        with io.open(os.path.join(self.dir, 'flat.tex'), 'w',
                     encoding='utf-8') as fh:
            fh.write('\n'.join([
                r'\begin{document}',
                r'\begin{table}\caption{Alpha}\label{TableAlpha}\end{table}',
                r'\begin{table}\caption{Beta}\label{TableBeta}\end{table}',
                r'\end{document}']))

    def test_the_number_reaches_the_caption(self):
        numbers = mb.fragment_reference_numbers(self.dir)
        out, done, missed = mb.resolve_fragment_references(
            r'\caption{표 \ref{TableBeta}와 비교}', numbers)
        self.assertEqual(done, 1)
        self.assertEqual(missed, [])
        self.assertIn('표 2', out)
        self.assertNotIn(r'\ref', out)


if __name__ == '__main__':
    unittest.main()
