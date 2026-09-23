# -*- coding: utf-8 -*-
r"""Tests for the passes a raw table float never otherwise receives.

A protected float is carried verbatim from flat.tex to the renderer, so the
citation resolver and the leftover-command pass never see inside it. Three
things were being deleted there, each of them content a reader needs and
each of them invisible to every count:

- `\citep{key}` — pandoc has no bibliography here and drops the call with
  its key. CafeQ's table 6 exists to say which benchmark came from which
  paper; all sixteen sources were removed from it.
- `\text{PQE}` — amsmath's, and outside math pandoc drops it with its body.
  CafeQ's table 7 printed no header at all over the column it is sorted by.
- `{\color{red} 17.14}` — the declaration form, which pandoc drops. SINQ's
  captions tell the reader that results beating the baselines are marked in
  red; twelve such values printed black, and the word `빨간색` in the caption
  was the only red left on the page.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

BIB = (r'\bibitem[Hendrycks et~al.(2021{a})Hendrycks, Burns]{hendrycks-2021}'
       ' Dan Hendrycks and Collin Burns.\n'
       r'\bibitem[Clark et~al.(2018)Clark]{clark-2018} Peter Clark.' '\n')


class Citations(unittest.TestCase):

    def test_labels_come_from_the_inlined_bibliography(self):
        labels = mb.build_citation_labels(BIB)
        self.assertEqual(labels['hendrycks-2021'], 'Hendrycks et al. 2021a')
        self.assertEqual(labels['clark-2018'], 'Clark et al. 2018')

    def test_citep_renders_in_parentheses(self):
        labels = mb.build_citation_labels(BIB)
        got, n = mb.resolve_fragment_citations(
            r'MMLU \citep{hendrycks-2021} & x', labels)
        self.assertEqual(got, 'MMLU (Hendrycks et al. 2021a) & x')
        self.assertEqual(n, 1)

    def test_citet_puts_the_year_in_parentheses(self):
        labels = mb.build_citation_labels(BIB)
        got, _n = mb.resolve_fragment_citations(r'\citet{clark-2018}', labels)
        self.assertEqual(got, 'Clark et al. (2018)')

    def test_two_keys_in_one_call(self):
        labels = mb.build_citation_labels(BIB)
        got, _n = mb.resolve_fragment_citations(
            r'\citep{hendrycks-2021,clark-2018}', labels)
        self.assertEqual(got, '(Hendrycks et al. 2021a; Clark et al. 2018)')

    def test_an_unknown_key_is_left_visible(self):
        # Visibly unresolved can be fixed; silently attributed to the wrong
        # paper cannot even be noticed.
        text = r'\citep{zheng2025dynamo}'
        self.assertEqual(mb.resolve_fragment_citations(text, {'a': 'b'}),
                         (text, 0))

    def test_a_partly_known_call_is_left_alone(self):
        labels = mb.build_citation_labels(BIB)
        text = r'\citep{clark-2018,unknown-key}'
        self.assertEqual(mb.resolve_fragment_citations(text, labels)[0], text)


class TextMacro(unittest.TestCase):

    def test_text_becomes_textrm(self):
        self.assertEqual(mb._TEXT_MACRO_RE.sub(r'\\textrm', r'\text{PQE}'),
                         r'\textrm{PQE}')

    def test_it_says_the_same_thing_inside_math(self):
        self.assertEqual(
            mb._TEXT_MACRO_RE.sub(r'\\textrm', r'$\lambda_{\text{orth}}$'),
            r'$\lambda_{\textrm{orth}}$')

    def test_other_text_commands_are_untouched(self):
        for cmd in (r'\textbf{x}', r'\textsc{y}', r'\textsuperscript{z}'):
            self.assertEqual(mb._TEXT_MACRO_RE.sub(r'\\textrm', cmd), cmd)


class ColourDeclarations(unittest.TestCase):

    def test_a_braced_declaration_keeps_its_braces(self):
        got, n = mb.rewrite_color_declarations(r'a & {\color{red}17.14} & b')
        self.assertEqual(got, r'a & {\textcolor{red}{17.14}} & b')
        self.assertEqual(n, 1)

    def test_a_bare_declaration_stops_at_the_cell(self):
        got, n = mb.rewrite_color_declarations(
            r'a &\color{red} 22.39 & 9.25 \\')
        self.assertEqual(got, r'a &\textcolor{red}{22.39}& 9.25 \\')
        self.assertEqual(n, 1)

    def test_a_declaration_inside_textbf_keeps_the_argument(self):
        # Dropping the outer brace here would leave `\textbf` holding
        # nothing, and the value would lose its bold as well as its colour.
        got, n = mb.rewrite_color_declarations(r'\textbf{\color{red}7.74}')
        self.assertEqual(got, r'\textbf{\textcolor{red}{7.74}}')
        self.assertEqual(n, 1)

    def test_a_row_with_no_colour_is_untouched(self):
        row = r'RTN & 1.28 & 32.43 \\'
        self.assertEqual(mb.rewrite_color_declarations(row), (row, 0))

    def test_several_in_one_row(self):
        got, n = mb.rewrite_color_declarations(
            r'a & \color{red}1.1 & \color{red}2.2 & 3.3 \\')
        self.assertEqual(n, 2)
        self.assertIn(r'\textcolor{red}{1.1}', got)
        self.assertIn(r'\textcolor{red}{2.2}', got)
        self.assertIn('3.3', got)


class AColourDeclarationInsideMaths(unittest.TestCase):
    r"""The colour rewriter deleted a whole table by moving one `$`.

    `{\color{red} X}` scopes to its brace, and a bare `\color{red} X` in a
    cell scopes to the `&`, which is what `_cell_end` finds. Inside maths
    that is too far: the `&` sits past the closing `$`, so the rewrite pulled
    that `$` into `\textcolor{red}{...}` and left the maths unbalanced. The
    brace count still balanced, so nothing caught it; pandoc abandoned the
    tabular, emitted no `<table>`, and a 24-row notation table was absent
    from the book. The report was "1 FAILED" with no name and no reason.
    """

    def test_the_closing_dollar_is_not_swallowed(self):
        tex = r'$\color{quantgreen}{\widehat{F}}$ & hidden error \\'
        got, n = mb.rewrite_color_declarations(tex)
        self.assertEqual(n, 1)
        self.assertEqual(got.count('$'), 2, got)
        self.assertTrue(got.startswith('$'), got)
        self.assertIn(r'\textcolor{quantgreen}{{\widehat{F}}}', got)

    def test_the_cell_after_it_is_untouched(self):
        tex = r'$\color{red} x$ & second column \\'
        got, _n = mb.rewrite_color_declarations(tex)
        self.assertIn('& second column', got)
        self.assertEqual(got.count('$'), 2, got)

    def test_a_declaration_outside_maths_still_reaches_the_cell_end(self):
        """The behaviour the clamp must not take away."""
        tex = r'\color{red} 17.14 & 3.2 \\'
        got, n = mb.rewrite_color_declarations(tex)
        self.assertEqual(n, 1)
        self.assertIn(r'\textcolor{red}{17.14}', got)
        self.assertIn('& 3.2', got)

    def test_a_braced_declaration_is_unaffected(self):
        tex = r'{\color{red} 17.14}'
        got, n = mb.rewrite_color_declarations(tex)
        self.assertEqual(n, 1)
        self.assertIn(r'\textcolor{red}{17.14}', got)

    def test_two_maths_spans_in_one_cell_stay_balanced(self):
        tex = r'$a$ and $\color{red} b$ & next \\'
        got, _n = mb.rewrite_color_declarations(tex)
        self.assertEqual(got.count('$'), 4, got)


class ColumnSpecsPandocCannotRead(unittest.TestCase):
    r"""A notation table went missing from a book, and the report was a count.

    pandoc 3.10.2 reads `\begin{tabular}{ll}` happily and
    `\multicolumn{2}{@{}l@{}}{...}` not at all: it abandons the whole tabular
    at the span it cannot parse and falls back to the unknown-environment
    rendering, a `<div class="tabular">` with the column letters printed as
    prose. `expand_raw_latex_tables` then sees no `<table>` and counts a
    failure, so the build said "1 FAILED (they will be missing)" and named
    nothing.

    Width and inter-column spacing are presentation; an HTML table uses
    neither. Alignment is the part that carries meaning, so that is what
    survives normalisation.
    """

    def test_spacing_and_width_leave_the_alignment_behind(self):
        self.assertEqual(
            mb._clean_colspec(r'@{}p{0.30\textwidth}p{0.64\textwidth}@{}'),
            'll')

    def test_a_plain_spec_is_untouched(self):
        for spec in ('lcccc', 'lccc', 'l|c|r'):
            self.assertEqual(mb._clean_colspec(spec), spec)

    def test_array_package_cell_prefixes_go(self):
        self.assertEqual(mb._clean_colspec(r'>{\bfseries}l<{\quad}c'), 'lc')

    def test_tabularx_stretch_columns_read_left(self):
        self.assertEqual(mb._clean_colspec('lXX'), 'lll')

    def test_the_tabular_preamble_is_rewritten(self):
        latex = (r'\begin{tabular}{@{}p{0.30\textwidth}p{0.64\textwidth}@{}}'
                 '\n' r'a & b \\' '\n' r'\end{tabular}')
        got, n = mb.normalise_tabular_preambles(latex)
        self.assertEqual(n, 1)
        self.assertIn(r'\begin{tabular}{ll}', got)

    def test_the_multicolumn_span_is_rewritten(self):
        """The one that actually mattered. Fixing only the preamble left the
        table just as absent."""
        latex = (r'\begin{tabular}{ll}' '\n'
                 r'\multicolumn{2}{@{}l@{}}{\emph{Group}} \\' '\n'
                 r'a & b \\' '\n' r'\end{tabular}')
        got, n = mb.normalise_tabular_preambles(latex)
        self.assertEqual(n, 1)
        self.assertIn(r'\multicolumn{2}{l}{\emph{Group}}', got)

    def test_a_width_argument_is_not_mistaken_for_a_spec(self):
        r"""`\multirow` and `tabularx` take a WIDTH where multicolumn takes a
        spec. Cleaning a width would delete it."""
        latex = (r'\begin{tabularx}{\textwidth}{@{}lX@{}}' '\n'
                 r'\multirow{2}{4em}{tall} & b \\' '\n' r'\end{tabularx}')
        got, _n = mb.normalise_tabular_preambles(latex)
        self.assertIn(r'\begin{tabularx}{\textwidth}{ll}', got)
        self.assertIn(r'\multirow{2}{4em}{tall}', got)

    def test_an_optional_position_argument_survives(self):
        latex = r'\begin{tabular}[t]{@{}ll@{}}' '\n' r'\end{tabular}'
        got, _n = mb.normalise_tabular_preambles(latex)
        self.assertIn(r'\begin{tabular}[t]{ll}', got)

    def test_nothing_to_do_reports_nothing(self):
        latex = r'\begin{tabular}{lcr}' '\n' r'a & b & c \\' '\n' r'\end{tabular}'
        got, n = mb.normalise_tabular_preambles(latex)
        self.assertEqual(n, 0)
        self.assertEqual(got, latex)


if __name__ == '__main__':
    unittest.main()
