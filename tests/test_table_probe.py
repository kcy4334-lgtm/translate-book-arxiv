# -*- coding: utf-8 -*-
r"""Tests for the built-table-vs-source-LaTeX probe.

The probe exists to find table content that never reached the page. It only
works if it is quiet about tables that are fine: it reported 34 findings
against SINQ and 10 against AlphaQ, nearly all of them its own rules being
wrong, and a check with that much noise is one nobody reads. The real defect
this session -- a footnote asterisk spliced out of CafeQ's table 3 -- was
found by hand, not by the probe, while 34 false alarms stood.

So these run in both directions: the probe must stay silent on a faithful
table and still speak up on one that lost a row.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import table_probe as tp


class ResNetNesting(unittest.TestCase):
    r"""ResNet defines `\tabincell` as a tabular and puts one in each of four
    header cells. The template counted as table 1, the inner ones ended their
    table early, and a correct book drew 40 findings."""

    TEX = (r'\newcommand{\tabincell}[2]{\begin{tabular}{@{}#1@{}}#2\end{tabular}}'
           '\n' r'\begin{tabular}{l|c}' '\n'
           r'\begin{tabular}{@{}c@{}}LOC \\ method\end{tabular} & err \\' '\n'
           r'\hline' '\n' r'A & 1.5 \\' '\n' r'B & 2.5 \\' '\n'
           r'\end{tabular}' '\n')

    def test_the_template_and_the_inner_tabular_are_not_tables(self):
        units = tp.tabular_units(self.TEX)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0][0], 2)

    def test_a_printed_hash_is_not_a_template(self):
        # BERT: `\#1 Ensemble - nlnet`.
        tex = r'\begin{tabular}{ll}\#1 Ensemble & 86.0 \\\end{tabular}'
        self.assertEqual(len(tp.tabular_units(tex)), 1)

    def test_blank_spacing_rows_are_not_counted_on_either_side(self):
        # GPT-3's poem table: `\\ \\` and `& \\` between stanzas.
        body = 'a & b \\\\\n \\\\ \\\\\n & \\\\\nc & d \\\\'
        page = ('<table><tr><td>a</td><td>b</td></tr><tr><td></td><td></td>'
                '</tr><tr><td></td><td></td></tr><tr><td></td><td></td></tr>'
                '<tr><td>c</td><td>d</td></tr></table>')
        self.assertEqual(tp.check_table(1, 2, body, page), [])

    def test_a_table_inside_a_cell_is_that_cells_text(self):
        html = ('<table><tr><td><table><tr><td>LOC</td></tr><tr><td>method'
                '</td></tr></table></td><td>err</td></tr>'
                '<tr><td>A</td><td>1.5</td></tr></table><table><tr><td>x'
                '</td></tr></table>')
        blocks = tp.outer_tables(html)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(tp.html_rows(blocks[0])[0],
                         [('LOC method', 1), ('err', 1)])
        self.assertEqual(len(tp.html_rows(blocks[0])), 2)

    def test_a_cline_is_not_a_row_label(self):
        body = (r'\multirow{2}{*}{method} & \multicolumn{2}{c}{err} \\'
                r'\cline{2-3}' '\n' r'& val & test \\')
        rows = tp.source_rows(body)
        self.assertTrue(tp._blank_first_cell(rows[1]))


class SpanAndBreakArguments(unittest.TestCase):
    def test_a_doubly_nested_multicolumn_format_is_not_a_value(self):
        # Shor's truth table.
        body = (r'\multicolumn{3}{|c|@{\hspace{1em}}}{INPUT}&'
                r'\multicolumn{3}{@{\hspace{-1em}}c@{\hspace{0em}}|}{OUTPUT}\\')
        self.assertEqual(tp.printed_numbers(body), tp.Counter())

    def test_a_row_break_length_is_not_a_value(self):
        # U-Net's `\bottomrule\\[-0.8cm]`.
        self.assertEqual(tp.printed_numbers(r'a & 1 \\ \bottomrule\\[-0.8cm]'),
                         tp.Counter({'1': 1}))


class MoreLengthsAndRowEnds(unittest.TestCase):
    def test_rules_and_struts_are_lengths(self):
        # attention's tables.
        self.assertEqual(tp.printed_numbers(
            r'\rule{0pt}{2.0ex}A & 1 \\ \specialrule{1pt}{-1pt}{0pt}'),
            tp.Counter({'1': 1}))

    def test_graphic_options_are_not_values(self):
        # Neural ODE's figure laid out as a tabular.
        self.assertEqual(tp.printed_numbers(
            r'\includegraphics[width=0.2\textwidth, trim=4mm 4mm 4mm 4mm]'
            r'{imgs/resnet_0_viz.pdf} & B'), tp.Counter())

    def test_tabularnewline_ends_a_row(self):
        # GAN's table 4.
        rows = tp.source_rows(r'a & b \tabularnewline \hline c & d \tabularnewline')
        self.assertEqual(len(rows), 2)

    def test_a_defined_column_type_with_a_width_is_one_column(self):
        self.assertEqual(tp.colspec_columns(r'c|L{1in}|L{1in}|L{1in}|L{1in}'), 5)


class NeverTypeset(unittest.TestCase):
    def test_comment_environment_and_iffalse_are_skipped(self):
        # 2609.11867 keeps an older table inside \begin{comment}.
        tex = (r'\begin{comment}\begin{tabular}{lcc}a&b&c\\\end{tabular}'
               r'\end{comment}\iffalse\begin{tabular}{l}x\\\end{tabular}\fi'
               r'\begin{tabular}{lcccc}a&b&c&d&e\\\end{tabular}')
        units = tp.tabular_units(tp._SKIPPED_RE.sub('', tex))
        self.assertEqual([c for c, _b in units], [5])


class ViTTableNine(unittest.TestCase):
    """ViT's VTAB table: grey rules in the colspec, TikZ dots in the header."""

    def test_nested_braces_in_a_rule_spec_are_not_columns(self):
        spec = ('p{10pt}p{1.6cm}!{\\color{lightgray}\\vline} ccccccc'
                '!{\\color{lightgray}\\vline}cccc')
        self.assertEqual(tp.colspec_columns(spec), 13)

    def test_tikz_coordinates_are_not_values(self):
        body = ('& \\rotatebox{90}{\\raisebox{0.5pt}{\\tikz\\fill[natural] '
                '(0,0) circle (.5ex);} Caltech101} \\\\ ViT & 95.3 \\\\')
        # "Caltech101" is printed; the coordinates are not.
        self.assertEqual(sorted(tp.printed_numbers(body)), ['101', '95.3'])


class BoldMathDigits(unittest.TestCase):
    """ViT's best results are `$\\mathbf{88.55}$`; pandoc prints them in
    mathematical bold digits, and the probe called them missing."""

    def test_bold_math_digits_are_the_same_number(self):
        self.assertEqual(tp.numbers_of('\U0001D7D6\U0001D7D6.\U0001D7D3\U0001D7D3'),
                         tp.numbers_of('88.55'))


class CommentedOutTables(unittest.TestCase):
    """Sentence-BERT comments a whole table out; it is not missing."""

    def test_a_commented_out_tabular_is_not_counted(self):
        import contextlib
        import io
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        flat = ('% \\begin{tabular}{|l|c|}\n%  A & 1 \\\\\n% \\end{tabular}\n'
                '\\begin{tabular}{lc}\nA & 1 \\\\\n\\end{tabular}\n')
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(flat)
        with open(os.path.join(d, 'book_doc.html'), 'w', encoding='utf-8') as fh:
            fh.write('<table><tr><td>A</td><td>1</td></tr></table>')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tp.probe(d)
        self.assertIn('source tabulars: 1', out.getvalue())
        self.assertNotIn('tabular(s) in the source', out.getvalue())


class Colspec(unittest.TestCase):

    def test_star_repeat_is_expanded(self):
        self.assertEqual(tp.colspec_columns('l*{11}{c}'), 12)

    def test_colspec_is_read_to_its_matching_brace(self):
        # `{l*{11}{c}}` stops at the `}` of `{11}` if the brace is not
        # matched, and the probe then claims three columns for twelve.
        tex = ('\\begin{tabular}{l*{11}{c}}\n'
               'a & 1 & 2 & 3 & 4 & 5 & 6 & 7 & 8 & 9 & 10 & 11 \\\\\n'
               '\\end{tabular}')
        units = tp.tabular_units(tex)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0][0], 12)

    def test_tabularx_width_argument_is_not_the_colspec(self):
        tex = ('\\begin{tabularx}{\\textwidth}{lXX}\n'
               'a & b & c \\\\\n'
               '\\end{tabularx}')
        self.assertEqual(tp.tabular_units(tex)[0][0], 3)

    def test_p_columns_still_count(self):
        self.assertEqual(tp.colspec_columns('l p{2cm} c'), 3)


class PrintedNumbers(unittest.TestCase):

    def test_citation_year_is_not_a_table_value(self):
        nums = tp.printed_numbers(r'method \cite{adepu2024framequant} & 46.6')
        self.assertNotIn('2024', nums)
        self.assertIn('46.6', nums)

    def test_citep_with_optional_arguments(self):
        self.assertNotIn('2022', tp.printed_numbers(
            r'x \citep[see][p.~3]{frantar2022gptq} & 1.5'))

    def test_multicolumn_span_is_not_a_value(self):
        nums = tp.printed_numbers(r'\multicolumn{3}{c}{48.0}')
        self.assertNotIn('3', nums)
        self.assertIn('48.0', nums)

    def test_a_span_whose_format_holds_braces_is_not_a_value(self):
        r"""2609.11801's table 6 writes `\multicolumn{7}{@{}l}{\emph{Training}}`;
        the flat pattern missed the `@{}` and the 7 was reported missing on
        every run."""
        nums = tp.printed_numbers(r'\multicolumn{7}{@{}l}{\emph{Training}}\\ x & 0.5')
        self.assertNotIn('7', nums)
        self.assertIn('0.5', nums)
        self.assertNotIn('2', tp.printed_numbers(
            r'\begin{tabular}{@{}l p{2cm}@{}} a & 9'))

    def test_a_real_value_survives(self):
        self.assertEqual(tp.printed_numbers('a & 46.6 & 47.6')['46.6'], 1)

    def test_a_row_colour_is_not_a_value(self):
        r"""`\rowcolor[rgb]{ .900, .900, .900}` shades the paper's own rows.
        Its three `.900`s read as a value `900` the page had lost -- six of
        them across VLA-Adapter's tables 5, 6 and 7, on a book whose fifteen
        tables were every one correct."""
        nums = tp.printed_numbers(
            r'\rowcolor[rgb]{ .900,  .900,  .900} Ours & 79.6')
        self.assertNotIn('900', nums)
        self.assertIn('79.6', nums)

    def test_cell_and_column_colours_too(self):
        for cmd in (r'\cellcolor[rgb]{ .900, .900, .900}',
                    r'\columncolor{gray}'):
            self.assertNotIn('900', tp.printed_numbers(cmd + ' x & 1.0'))

    def test_a_dingbat_argument_is_not_a_value(self):
        r"""`\ding{51}` prints a tick and `\ding{55}` a cross. Counted as
        values they were two more numbers nobody had lost."""
        nums = tp.printed_numbers(r'\ding{51} & \ding{55} & 88.2')
        self.assertNotIn('51', nums)
        self.assertNotIn('55', nums)
        self.assertIn('88.2', nums)


class BlankFirstCell(unittest.TestCase):

    def test_multirow_continuation_is_blank(self):
        self.assertTrue(tp._blank_first_cell(r' & 3 bits & 4 bits'))

    def test_a_labelled_row_is_not_blank(self):
        self.assertFalse(tp._blank_first_cell(r'CafeQ & 46.6 & 47.6'))

    def test_a_cell_holding_only_spacing_is_blank(self):
        self.assertTrue(tp._blank_first_cell(r'\addlinespace & 1 & 2'))

    def test_an_empty_spanning_cell_is_blank(self):
        r"""`\multicolumn{3}{c|}{}` is an empty header continuation. Stripping
        the command and then unwrapping every brace left `3 c|`, so the row
        read as labelled, the source total came out one short, and a page row
        that was correctly blank was reported as a stranded label."""
        self.assertTrue(tp._blank_first_cell(r'\multicolumn{3}{c|}{} & 1'))

    def test_a_spanning_cell_with_text_is_not_blank(self):
        self.assertFalse(tp._blank_first_cell(r'\multicolumn{2}{c}{Method} & 1'))

    def test_a_multirow_label_is_not_blank(self):
        self.assertFalse(
            tp._blank_first_cell(r'\multirow{8}{*}{\textit{Large}} & 1'))

    def test_a_nested_span_keeps_its_text(self):
        self.assertFalse(tp._blank_first_cell(
            r'\multicolumn{2}{c}{\multirow{2}{*}{CALVIN}} & 1'))

    def test_a_coloured_continuation_row_is_still_blank(self):
        r"""The colour carries no text but plenty of characters, and left
        `.900, .900, .900` behind for the generic rule to read as a label."""
        self.assertTrue(tp._blank_first_cell(
            r'\rowcolor[rgb]{ .900,  .900,  .900} & 79.6 & 80.1'))


SOURCE = ('\\begin{tabular}{lcc}\n'
          '\\toprule\n'
          '\\multirow{2}{*}{Method} & \\multicolumn{2}{c}{Gemma} \\\\\n'
          ' & 3 bits & 4 bits \\\\\n'
          '\\midrule\n'
          'Uniform & 23.3 & 41.3 \\\\\n'
          'CafeQ & 46.6 & 47.6 \\\\\n'
          '\\bottomrule\n'
          '\\end{tabular}')

FAITHFUL = ('<table><tr><th>Method</th><th colspan="2">Gemma</th></tr>'
            '<tr><td></td><td>3 bits</td><td>4 bits</td></tr>'
            '<tr><td>Uniform</td><td>23.3</td><td>41.3</td></tr>'
            '<tr><td>CafeQ</td><td>46.6</td><td>47.6</td></tr></table>')


class SpacingArguments(unittest.TestCase):
    r"""`\addlinespace[2pt]` is glue, and its `2` is not a table value."""

    def test_bracket_length_is_not_a_value(self):
        nums = tp.printed_numbers(r'\addlinespace[2pt] CafeQ & 46.6')
        self.assertNotIn('2', nums)
        self.assertIn('46.6', nums)

    def test_the_optional_argument_leaves_with_its_command(self):
        # Left behind, `[2pt]` lands in the next row's first cell and a
        # `\multirow` continuation reads as a labelled row.
        rows = tp.source_rows('\\addlinespace[2pt]\n'
                              '& \\multirow{6}{*}{2.5} & Uniform & 6.16 \\\\\n')
        self.assertTrue(rows)
        self.assertTrue(tp._blank_first_cell(rows[0]), rows[0])

    def test_a_length_in_braces_still_goes(self):
        self.assertNotIn('6', tp.printed_numbers(r'\vspace{6pt} a & 1.5'))


class PageMarkup(unittest.TestCase):

    def test_a_table_named_in_a_style_comment_is_not_a_table(self):
        html = ('<style>/* no break-inside on <table> — Chromium ignores'
                ' it */</style>\n<p>text</p>\n<table><tr><td>a</td></tr>'
                '</table>')
        self.assertEqual(len(tp.TABLE_EL_RE.findall(tp._page_markup(html))), 1)

    def test_a_real_table_survives(self):
        html = '<table><tr><td>a</td></tr></table>'
        self.assertEqual(tp._page_markup(html), html)


class Annotations(unittest.TestCase):

    def test_tex_annotation_is_not_page_text(self):
        cell = ('<math><mo>↓</mo><annotation encoding="application/x-tex">'
                '&#92;downarrow</annotation></math>')
        self.assertNotIn('92', tp.strip_tags(cell))

    def test_the_rendered_part_is_kept(self):
        cell = ('46.6<annotation encoding="application/x-tex">x^{*}'
                '</annotation>')
        self.assertIn('46.6', tp.strip_tags(cell))


class CheckTable(unittest.TestCase):

    def units(self):
        return tp.tabular_units(SOURCE)[0]

    def test_faithful_table_produces_no_finding(self):
        columns, body = self.units()
        self.assertEqual(tp.check_table(1, columns, body, FAITHFUL), [])

    def test_a_dropped_row_is_found(self):
        # This is the CafeQ table 4 defect in miniature: the label reaches
        # the page and the three numbers behind it do not.
        columns, body = self.units()
        broken = FAITHFUL.replace('<td>46.6</td><td>47.6</td>', '')
        findings = tp.check_table(1, columns, body, broken)
        self.assertTrue(any('not on the page' in f for f in findings),
                        findings)

    def test_a_stranded_label_is_found(self):
        columns, body = self.units()
        broken = FAITHFUL.replace('<td>Uniform</td>', '<td></td>')
        findings = tp.check_table(1, columns, body, broken)
        self.assertTrue(any('no row label' in f for f in findings), findings)

    def test_a_lost_column_span_is_found(self):
        columns, body = self.units()
        broken = FAITHFUL.replace('<th colspan="2">Gemma</th>',
                                  '<th>Gemma</th>')
        findings = tp.check_table(1, columns, body, broken)
        self.assertTrue(any('span' in f for f in findings), findings)


if __name__ == '__main__':
    unittest.main()
