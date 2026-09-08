# -*- coding: utf-8 -*-
r"""The words below a table's caption, which nothing used to check.

`untranslated_captions` stopped a build whose table CAPTIONS were still in
English. Step 4.6 asks for three more things -- column headers, rotated
row-group labels, and the prose under `\begin{tablenotes}` -- and no check
anywhere looked at them, so the gate stopped on the caption and the header
shipped. Measured on the five papers on this machine: TinyVLA's Korean
edition carries `Avg`, `Params` and `Total` across the top of a results
table, and AlphaQ's carries `Acc`.

The check that decides this stops builds, so the number that matters is not
what it catches but what it wrongly catches. These tests are weighted
accordingly: the names must survive. `Method` and `PIQA` are both
capitalised English words of one token, and only a vocabulary separates
them.

The vocabulary was read off the corpus rather than invented -- every cell
between `\toprule` and `\midrule` in five papers -- and validated against
both the sources and the finished books: zero name-shaped hits, silent on
the two books whose headers were translated, firing on the two whose were
not.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb
import table_language as tl


def tabular(*cells):
    r"""A one-row tabular holding these cells."""
    return ('\\begin{tabular}{lcc}\n\\toprule\n%s \\\\\n\\bottomrule\n'
            '\\end{tabular}' % ' & '.join(cells))


class TheNamesSurvive(unittest.TestCase):
    """The half that decides whether this can gate a build at all."""

    def test_benchmark_and_model_names_are_not_words(self):
        for name in ('PIQA', 'MMLU', 'C4', 'HellaSwag', 'WinoGrande',
                     'Qwen3-14B', 'Qwen3-1.7B', 'OpenVLA', 'WikiText2',
                     'BoolQ', 'ARC-c', 'StackCubes', 'LIBERO-Long',
                     'DeepSeek-V2-Lite', 'CALVIN', 'ImageNet'):
            self.assertIsNone(tl.header_word(name), name)

    def test_a_row_of_names_reports_nothing(self):
        self.assertEqual(
            tl.untranslated_header_cells(
                tabular('PIQA', 'MMLU', 'HellaSwag', 'WinoGrande')), [])

    def test_the_vocabulary_holds_no_name_shaped_entry(self):
        """Guards the list against a later addition, not the code.

        A name carries a digit, an inner capital or a hyphen, and every
        entry here is a plain lowercase word.
        """
        for word in tl.HEADER_WORDS:
            self.assertEqual(word, word.lower(), word)
            self.assertTrue(word.isalpha(), word)

    def test_ambiguous_words_are_deliberately_absent(self):
        r"""`Ours` and `Top-1` are routinely kept as they are in a correct
        translation, so a gate firing on them would be wrong. Recorded as a
        test because the reason lives in the module docstring and a reader
        adding words will not necessarily read it."""
        for word in ('ours', 'top-1', 'top-5', 'sota', 'gpu', 'cpu'):
            self.assertNotIn(word, tl.HEADER_WORDS)


class TheCommonWordsAreCaught(unittest.TestCase):

    def test_the_words_the_corpus_actually_carries(self):
        for word in ('Method', 'Model', 'Avg', 'Params', 'Bits', 'Mem',
                     'Tok', 'Prefill', 'Decode', 'Total', 'Baseline',
                     'Latency', 'Layer', 'Setting', 'Average', 'Task'):
            self.assertEqual(tl.header_word(word), word.lower(), word)

    def test_case_does_not_matter(self):
        for spelling in ('method', 'Method', 'METHOD', 'MeThOd'):
            self.assertEqual(tl.header_word(spelling), 'method', spelling)


class LatexComesOffBeforeTheComparison(unittest.TestCase):
    r"""Every one of these was seen in a real paper's header row."""

    def test_a_rule_rides_along_at_the_front_of_the_row(self):
        """`\\toprule \\textbf{Bits}` is one cell, not two."""
        self.assertEqual(tl.header_word('\\toprule \\textbf{Bits}'), 'bits')
        self.assertEqual(tl.header_word('\\midrule Average'), 'average')
        self.assertEqual(tl.header_word('\\hline Method'), 'method')

    def test_a_wrapped_header(self):
        for cell in ('\\multirow{2}{*}{Avg.}', '\\multicolumn{1}{c}{Avg.}',
                     '\\rotatebox{90}{Avg.}'):
            self.assertEqual(tl.header_word(cell), 'avg', cell)

    def test_a_rotated_row_group_label(self):
        """Step 4.6 asks for these by name."""
        self.assertEqual(tl.header_word('\\rotatebox{90}{Method}'), 'method')

    def test_units_and_direction_markers_are_not_part_of_the_word(self):
        r"""A per-cent sign is `\%` in LaTeX; SINQ spells it that way."""
        for cell in ('Acc. (\\%)', 'Params (GB) $\\downarrow$',
                     'Latency (Sec) $\\downarrow$', 'Avg. $\\uparrow$',
                     'Time (s)'):
            self.assertIsNotNone(tl.header_word(cell), cell)

    def test_a_bare_per_cent_sign_opens_a_comment(self):
        r"""Not a quirk to work around: an unescaped `%` IS a comment in
        LaTeX, so everything after it is invisible to the reader and must
        be invisible here. Written down because `Acc. (%)` looks like a
        header cell and is not one."""
        self.assertEqual(tl.cell_surface('Method % old name was Approach'),
                         'Method')
        self.assertIsNone(tl.header_word('Acc. (%)'))

    def test_an_arrow_glued_to_a_name_still_leaves_a_name(self):
        for cell in ('HellaSwag$\\uparrow$', 'WikiText2$\\downarrow$',
                     'BoolQ$\\uparrow$'):
            self.assertIsNone(tl.header_word(cell), cell)


class OnlyAWholeCellCounts(unittest.TestCase):
    """A cell that merely CONTAINS a word is prose, and prose belongs to
    the caption test. Matching inside cells is how a gate gets noisy."""

    def test_two_words_are_not_one_vocabulary_entry(self):
        for cell in ('Total Time (s)', 'Model Tasks', 'Method Avg'):
            self.assertIsNone(tl.header_word(cell), cell)

    def test_a_sentence_is_not_a_header(self):
        self.assertIsNone(tl.header_word(
            'The method used for each model in this table'))

    def test_empty_and_missing(self):
        for cell in ('', None, '   ', '&', '\\\\', '---', '$x$'):
            self.assertIsNone(tl.header_word(cell), repr(cell))


class WhatTheReaderIsTold(unittest.TestCase):

    def test_the_reported_string_carries_no_latex(self):
        r"""Printing `\multirow{2}{*}{Avg.}` at somebody whose build just
        stopped tells them about LaTeX when the answer is the word."""
        got = tl.untranslated_header_cells(
            tabular('\\multirow{2}{*}{Avg.}', 'PIQA'))
        self.assertEqual(got, ['Avg'])

    def test_a_header_repeated_down_a_table_is_one_finding(self):
        rows = tabular('Method', 'PIQA') + tabular('Method', 'MMLU')
        self.assertEqual(tl.untranslated_header_cells(rows), ['Method'])


class ATranslatedTableIsSilent(unittest.TestCase):
    """The property the whole gate rests on. Measured on two finished
    books: VLA-Adapter's fifteen floats and SINQ's fourteen report
    nothing."""

    def test_korean_headers_report_nothing(self):
        self.assertEqual(
            tl.untranslated_header_cells(
                tabular('\uBC29\uBC95', '\uD3C9\uAD70', 'PIQA', 'MMLU')), [])

    def test_a_table_with_no_tabular_reports_nothing(self):
        self.assertEqual(tl.untranslated_header_cells(
            '\\begin{table}\\caption{No tabular here}\\end{table}'), [])


class TheGateAbstainsWhenItCannotKnow(unittest.TestCase):
    r"""Both abstentions are about not answering a question the artefact
    was never asked."""

    MD = ('\\begin{table}\n\\caption{\uD45C 1: \uACB0\uACFC}\n'
          + tabular('Method', 'PIQA') + '\n\\end{table}\n')

    def test_it_fires_for_a_korean_book(self):
        got = mb.untranslated_table_words(self.MD, 'ko', None)
        self.assertTrue(got)
        self.assertIn('Method', got[0])

    def test_an_english_target_abstains(self):
        r"""The vocabulary is English, so a header still in English is only
        evidence of a skipped step when the book was not meant to be
        English. Nothing else here can tell those apart."""
        self.assertEqual(mb.untranslated_table_words(self.MD, 'en', None), [])
        self.assertEqual(mb.untranslated_table_words(self.MD, 'en-US', None),
                         [])

    def test_the_language_subtag_is_ignored(self):
        self.assertTrue(mb.untranslated_table_words(self.MD, 'zh-CN', None))


class ANoteIsProseAndTakesTheScriptTest(unittest.TestCase):

    def note_table(self, body):
        return ('\\begin{table}\n\\caption{\uD45C 1}\n'
                + tabular('\uBC29\uBC95', 'PIQA')
                + '\n\\begin{tablenotes}\n\\item[$\\dagger$] %s\n'
                  '\\end{tablenotes}\n\\end{table}\n' % body)

    def test_an_english_note_under_a_korean_table(self):
        md = self.note_table('Baselines marked with a dagger were re-run '
                             'by us rather than quoted.')
        got = mb.untranslated_table_words(md, 'ko', None)
        self.assertTrue(any('table note' in line for line in got), got)

    def test_a_translated_note_is_silent(self):
        md = self.note_table('\uB2E8\uAC80\uC73C\uB85C \uD45C\uC2DC\uB41C '
                             '\uAE30\uC900\uC120\uC740 \uC778\uC6A9\uC774 '
                             '\uC544\uB2C8\uB77C \uC9C1\uC811 \uC7AC\uD604'
                             '\uD55C \uACB0\uACFC\uC785\uB2C8\uB2E4.')
        got = mb.untranslated_table_words(md, 'ko', None)
        self.assertEqual([l for l in got if 'table note' in l], [])


if __name__ == '__main__':
    unittest.main()
