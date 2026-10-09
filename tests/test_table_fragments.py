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

    def test_each_natbib_form_prints_as_natbib_prints_it(self):
        labels = mb.build_citation_labels(BIB)
        cases = {r'\citeauthor{clark-2018}': 'Clark et al.',
                 r'\citealt{clark-2018}': 'Clark et al. 2018',
                 r'\citealp{clark-2018}': 'Clark et al., 2018',
                 r'\citeyear{clark-2018}': '2018',
                 r'\citeyearpar{clark-2018}': '(2018)',
                 r'\citet*{clark-2018}': 'Clark et al. (2018)',
                 r'\Citet{clark-2018}': 'Clark et al. (2018)'}
        for tex, want in cases.items():
            self.assertEqual(mb.resolve_fragment_citations(tex, labels)[0],
                             want, tex)

    def test_citet_of_two_keys_gives_each_its_year(self):
        labels = mb.build_citation_labels(BIB)
        got, _n = mb.resolve_fragment_citations(
            r'\citet{hendrycks-2021,clark-2018}', labels)
        self.assertEqual(got,
                         'Hendrycks et al. (2021a); Clark et al. (2018)')

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

    def test_a_numbered_list_gives_the_number_the_body_prints(self):
        # ResNet: `VGG \cite{Simonyan2015} (ILSVRC'14)` lost its citation.
        bib = ('\\begin{thebibliography}{10}\n\\bibitem{Bengio1994} A.\n'
               '\\bibitem{Simonyan2015} B.\n\\end{thebibliography}\n')
        labels = mb.build_citation_labels(bib)
        self.assertEqual(labels, {'Bengio1994': '1', 'Simonyan2015': '2'})
        self.assertEqual(mb.resolve_fragment_citations(
            r'VGG \cite{Simonyan2015} x', labels)[0], 'VGG [2] x')
        self.assertEqual(mb.resolve_fragment_citations(
            r'\cite{Bengio1994,Simonyan2015}', labels)[0], '[1, 2]')


class ColouredMarks(unittest.TestCase):
    """ViT's Table 9 tags each VTAB task with a TikZ dot in its group colour."""

    def test_a_tikz_dot_becomes_a_coloured_glyph(self):
        import latex_tables as lt
        out, n = lt.tikz_marks_to_glyphs(
            r'& \rotatebox{90}{\raisebox{0.5pt}{\tikz\fill[natural] (0,0) '
            r'circle (.5ex);} Caltech101}')
        self.assertEqual(out, r'& \rotatebox{90}{\textcolor{natural}{●} Caltech101}')
        self.assertEqual(n, 1)

    def test_a_defined_colour_is_written_as_its_value(self):
        import tempfile
        import shutil
        import latex_tables as lt
        temp = tempfile.mkdtemp(prefix='tb-colour-')
        try:
            with open(os.path.join(temp, 'flat.tex'), 'w', encoding='utf-8') as fh:
                fh.write('\\definecolor{natural}{rgb}{0.7137,0.3333,0.3333}\n'
                         '\\definecolor{pale}{HTML}{ABCDEF}\n'
                         '\\definecolor{mid}{gray}{0.5}\n')
            colours = lt.defined_colours(temp)
        finally:
            shutil.rmtree(temp, ignore_errors=True)
        self.assertEqual(colours, {'natural': '#b65555', 'pale': '#abcdef',
                                   'mid': '#808080'})
        self.assertEqual(lt.colours_by_value(
            r'\textcolor{natural}{●} \textcolor{red}{x}', colours),
            r'\textcolor{#b65555}{●} \textcolor{red}{x}')


class ColumnRules(unittest.TestCase):
    """pandoc drops every `|`; no table in a book had a vertical rule."""

    def test_vit_grey_rules_are_soft(self):
        import latex_tables as lt
        spec = (r'p{10pt}p{1.6cm}!{\color{lightgray}\vline} CCCCCCC'
                r'!{\color{lightgray}\vline}CCCC!{\color{lightgray}\vline}C')
        self.assertEqual(lt.column_rules(spec),
                         ({2: 'soft', 9: 'soft', 13: 'soft'}, 14))

    def test_bars_and_repeats(self):
        import latex_tables as lt
        self.assertEqual(lt.column_rules('|l|*{3}{c|}'),
                         ({0: 'dark', 1: 'dark', 2: 'dark', 3: 'dark', 4: 'dark'}, 4))

    def test_cells_beside_a_rule_are_marked_across_a_span(self):
        import latex_tables as lt
        html = ('<table><tr><th>a</th><th colspan="2">b</th></tr>'
                '<tr><td>1</td><td>2</td><td class="x">3</td></tr></table>')
        out = lt.mark_column_rules(html, r'\begin{tabular}{l|c|c|}x\end{tabular}')
        self.assertIn('<th colspan="2" class="vrule-left vrule-right">b</th>', out)
        self.assertIn('<td class="vrule-left">2</td>', out)
        self.assertIn('<td class="x vrule-left vrule-right">3</td>', out)

    def test_no_rule_no_change(self):
        import latex_tables as lt
        html = '<table><tr><td>1</td></tr></table>'
        self.assertEqual(lt.mark_column_rules(html, r'\begin{tabular}{l}1\end{tabular}'),
                         html)


class CellFootnotes(unittest.TestCase):
    def test_a_tablefootnote_becomes_a_mark_and_a_note(self):
        # PaLM's FLOP-count row lost its explanation.
        tex = (r'Training FLOP Count\tablefootnote{This uses $2 \times 3$ '
               r'per {token}.} & 37.4 \\ Other\footnote{Second.} & 1 \\')
        body, notes = mb.footnotes_to_notes(tex)
        self.assertEqual(body, r'Training FLOP Count\textsuperscript{a} & 37.4 '
                               r'\\ Other\textsuperscript{b} & 1 \\')
        self.assertEqual(notes, [r'\textsuperscript{a} This uses $2 \times 3$ '
                                 r'per {token}.', r'\textsuperscript{b} Second.'])

    def test_no_footnote_no_change(self):
        self.assertEqual(mb.footnotes_to_notes('a & b'), ('a & b', []))


class ClosingBreak(unittest.TestCase):
    def test_a_break_after_the_last_rule_goes(self):
        # U-Net: a blank row under its results table.
        tex = 'a & 1 \\\\\n\\bottomrule\\\\[-0.8cm]\n  \\end{tabular}'
        self.assertEqual(mb.drop_closing_break(tex),
                         ('a & 1 \\\\\n\\bottomrule\n  \\end{tabular}', 1))

    def test_a_break_between_rows_stays(self):
        tex = 'a & 1 \\\\\n\\hline\nb & 2 \\\\\n\\end{tabular}'
        self.assertEqual(mb.drop_closing_break(tex), (tex, 0))


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

    def test_siunitx_columns_are_columns(self):
        """PaLM's `ll SS|SSSS` came out `ll|`, and pandoc gave the table up."""
        self.assertEqual(mb._clean_colspec('ll SS|SSSS'), 'llrr|rrrr')
        self.assertEqual(mb._clean_colspec('lS[table-format=2.1]'), 'lr')

    def test_a_repeated_group_counts_every_column(self):
        self.assertEqual(mb._clean_colspec('l*{3}{c}r'), 'lcccr')
        self.assertEqual(mb._clean_colspec('l|*{2}{c|}'), 'l|c|c|')

    def test_a_papers_own_column_type_is_a_column(self):
        """ViT declares `\\newcolumntype{C}`."""
        self.assertEqual(mb._clean_colspec('p{10pt}CCC|L'), 'lccc|l')

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



@unittest.skipUnless(mb.resolve_pandoc(), 'needs pandoc')
class DocxCaption(unittest.TestCase):
    """23 of 25 corpus DOCX files printed `****표 32 (Table 32)** ...**`."""

    def test_a_numbered_caption_is_bold_once(self):
        md = ('\\begin{table}\\caption{\\textbf{표 1 (Table 1)} Results.}\n'
              '\\begin{tabular}{cc}\na & b \\\\\n1 & 2 \\\\\n\\end{tabular}\n'
              '\\end{table}\n')
        out, ok, _bad = mb.expand_raw_latex_tables(md, output='markdown')
        self.assertEqual(ok, 1)
        self.assertIn('**표 1 (Table 1)** Results.', out)
        self.assertNotIn('***', out)


if __name__ == '__main__':
    unittest.main()
