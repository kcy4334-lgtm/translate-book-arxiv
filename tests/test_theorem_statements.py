# -*- coding: utf-8 -*-
r"""Every theorem in the book carried a number the paper does not print.

Maynard declares `\newtheorem{thrm}{Theorem}[section]` and shares that counter
with lemma, proposition and corollary. The paper prints Theorem 1.1-1.4,
Proposition 4.1-4.3 and Lemma 5.1-5.3 / 6.1-6.3 / 8.1-8.3 — verified by reading
the source PDF. The book printed 정리 1-4, 명제 5-7, 보조정리 8-16, and
`source_probe` reported 35 references disagreeing and none agreeing.

The concession that let this stand was that pandoc owns those numbers (K113).
It does not: `**정리 1**` is characters in `output.md`, and this build rewrites
that line as a matter of routine. Fixing only the references made the book
worse — prose saying 정리 1.1 over a declaration reading 정리 1 — so the two
halves move together or not at all.

The free catch is the starred declarations. `\newtheorem*{rmk}{Remark}` prints
no number in LaTeX, and pandoc invented 비고 1-5 and 추측 1: six numbers in the
book the paper does not have, which no check could see because nothing `\ref`s
an unnumbered environment.
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

KO = mb.get_lang_config('ko')

PREAMBLE = (r'\newtheorem{thrm}{Theorem}[section]' '\n'
            r'\newtheorem{lmm}[thrm]{Lemma}' '\n'
            r'\newtheorem{prpstn}[thrm]{Proposition}' '\n'
            r'\newtheorem*{rmk}{Remark}' '\n'
            r'\begin{document}' '\n')


def body(*parts):
    return PREAMBLE + '\n'.join(parts) + '\n' + r'\end{document}' + '\n'


class _Temp(unittest.TestCase):
    def make(self, tex):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with io.open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(tex)
        return d


class TheTallyFollowsTheDocument(_Temp):
    def test_a_shared_counter_scoped_to_the_section(self):
        d = self.make(body(r'\section{One}',
                           r'\begin{thrm}a\end{thrm}',
                           r'\begin{lmm}b\end{lmm}',
                           r'\section{Two}',
                           r'\begin{prpstn}c\end{prpstn}'))
        self.assertEqual(mb.theorem_declarations(d),
                         [(1, '1.1'), (2, '1.2'), (3, '2.1')])

    def test_the_flat_number_is_what_pandoc_wrote(self):
        # The first element of each pair is pandoc's running count, which the
        # rewrite checks against before touching anything.
        d = self.make(body(r'\section{One}', r'\begin{thrm}a\end{thrm}',
                           r'\section{Two}', r'\begin{thrm}b\end{thrm}'))
        self.assertEqual([n for n, _ in mb.theorem_declarations(d)], [1, 2])

    def test_a_starred_environment_wants_no_number(self):
        d = self.make(body(r'\section{One}',
                           r'\begin{thrm}a\end{thrm}',
                           r'\begin{rmk}b\end{rmk}'))
        self.assertEqual(mb.theorem_declarations(d), [(1, '1.1'), (1, '')])

    def test_without_a_within_the_numbering_stays_flat(self):
        d = self.make(r'\newtheorem{thrm}{Theorem}' '\n'
                      r'\begin{document}' '\n'
                      r'\section{One}' '\n'
                      r'\begin{thrm}a\end{thrm}' '\n'
                      r'\section{Two}' '\n'
                      r'\begin{thrm}b\end{thrm}' '\n'
                      r'\end{document}' '\n')
        self.assertEqual(mb.theorem_declarations(d), [(1, '1'), (2, '2')])

    def test_a_starred_section_does_not_advance_the_prefix(self):
        d = self.make(body(r'\section*{Abstract}',
                           r'\section{One}',
                           r'\begin{thrm}a\end{thrm}'))
        self.assertEqual(mb.theorem_declarations(d), [(1, '1.1')])


class TheStatementsAreRewritten(_Temp):
    def setUp(self):
        self.dir = self.make(body(r'\section{One}',
                                  r'\begin{thrm}a\end{thrm}',
                                  r'\begin{lmm}b\end{lmm}',
                                  r'\begin{rmk}c\end{rmk}',
                                  r'\section{Two}',
                                  r'\begin{prpstn}d\end{prpstn}'))

    def test_the_numbers_become_the_paper_s(self):
        md = ('**정리 1**. 첫째.\n\n**보조정리 2**. 둘째.\n\n'
              '**비고 1**. 셋째.\n\n**명제 3**. 넷째.\n')
        got, stats = mb.number_theorem_statements(md, self.dir, KO)
        self.assertIsNone(stats['skipped_reason'])
        self.assertIn('**정리 1.1**', got)
        self.assertIn('**보조정리 1.2**', got)
        self.assertIn('**명제 2.1**', got)
        self.assertEqual(stats['numbered'], 3)

    def test_a_starred_statement_loses_its_invented_number(self):
        md = ('**정리 1**. 첫째.\n\n**보조정리 2**. 둘째.\n\n'
              '**비고 1**. 셋째.\n\n**명제 3**. 넷째.\n')
        got, stats = mb.number_theorem_statements(md, self.dir, KO)
        self.assertIn('**비고**.', got)
        self.assertNotIn('**비고 1**', got)
        self.assertEqual(stats['unnumbered'], 1)

    def test_the_surrounding_prose_is_untouched(self):
        md = '**정리 1**. 첫째.\n\n**보조정리 2**. 둘째.\n\n**비고 1**. 셋째.\n\n**명제 3**. 넷째.\n'
        got, _ = mb.number_theorem_statements(md, self.dir, KO)
        for word in ('첫째', '둘째', '셋째', '넷째'):
            self.assertIn(word, got)


class ItRefusesRatherThanGuess(_Temp):
    def setUp(self):
        self.dir = self.make(body(r'\section{One}',
                                  r'\begin{thrm}a\end{thrm}',
                                  r'\begin{lmm}b\end{lmm}'))

    def test_a_missing_statement_stops_the_whole_pass(self):
        md = '**정리 1**. 하나뿐이다.\n'
        got, stats = mb.number_theorem_statements(md, self.dir, KO)
        self.assertEqual(got, md)
        self.assertIn('refusing to guess', stats['skipped_reason'])

    def test_a_number_that_does_not_match_the_tally_stops_it(self):
        # If pandoc numbered differently from the way this models it, the
        # model is wrong and nothing should be rewritten on the strength of it.
        md = '**정리 1**. 하나.\n\n**보조정리 7**. 둘.\n'
        got, stats = mb.number_theorem_statements(md, self.dir, KO)
        self.assertEqual(got, md)
        self.assertIn('refusing to guess', stats['skipped_reason'])

    def test_a_paper_with_no_declarations_is_left_alone(self):
        d = self.make('\\begin{document}\nplain\n\\end{document}\n')
        md = '**정리 1**. 하나.\n'
        got, stats = mb.number_theorem_statements(md, d, KO)
        self.assertEqual(got, md)
        self.assertIsNotNone(stats['skipped_reason'])

    def test_a_language_with_no_theorem_words_is_left_alone(self):
        md = '**정리 1**. 하나.\n\n**보조정리 2**. 둘.\n'
        got, stats = mb.number_theorem_statements(md, self.dir, {})
        self.assertEqual(got, md)
        self.assertIsNotNone(stats['skipped_reason'])

    def test_the_longest_label_word_wins(self):
        # `보조정리` must not be read as `정리` with stray text in front, or the
        # site count goes wrong before anything is rewritten.
        md = '**정리 1**. 하나.\n\n**보조정리 2**. 둘.\n'
        got, stats = mb.number_theorem_statements(md, self.dir, KO)
        self.assertIsNone(stats['skipped_reason'])
        self.assertIn('**보조정리 1.2**', got)


if __name__ == '__main__':
    unittest.main()
