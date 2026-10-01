# -*- coding: utf-8 -*-
r"""The rows a paper shades to mark as its own.

A results table with twenty baselines shades the authors' two lines with
`\rowcolor[rgb]{ .900, .900, .900}`. pandoc drops the command, and
VLA-Adapter's five such rows arrived in the book looking like everyone
else's -- the one visual cue that says which numbers are the paper's,
absent, with every value present and every check passing.

The band has to land on the right row or it says something false about whose
result is whose, so the mapping refuses when the source and the rendered
table disagree about how many body rows there are. Not shading is a small
loss; shading a competitor's line is a wrong claim.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

LATEX = r'''\begin{tabular}{lcc}
\toprule
Method & Params & Score \\
\midrule
Baseline A & 7 & 41.3 \\
Baseline B & 3 & 46.6 \\
\rowcolor[rgb]{ .900,  .900,  .900} Ours & 0.5 & 79.6 \\
\bottomrule
\end{tabular}'''

HTML = ('<table><thead><tr><th>Method</th><th>Params</th><th>Score</th></tr>'
        '</thead><tbody>'
        '<tr><td>Baseline A</td><td>7</td><td>41.3</td></tr>'
        '<tr><td>Baseline B</td><td>3</td><td>46.6</td></tr>'
        '<tr><td>Ours</td><td>0.5</td><td>79.6</td></tr>'
        '</tbody></table>')


class FindingTheShadedRows(unittest.TestCase):

    def test_the_last_row_is_the_shaded_one(self):
        marked, total = mb.shaded_body_rows(LATEX)
        self.assertEqual(total, 3)
        self.assertEqual(marked, {2})

    def test_a_table_with_no_colour_marks_nothing(self):
        plain = LATEX.replace(
            r'\rowcolor[rgb]{ .900,  .900,  .900} ', '')
        marked, total = mb.shaded_body_rows(plain)
        self.assertEqual(marked, set())
        self.assertEqual(total, 3)

    def test_several_shaded_rows_are_all_found(self):
        two = LATEX.replace(
            r'Baseline B & 3 & 46.6 \\',
            r'\rowcolor[rgb]{ .9, .9, .9} Ours-Pro & 3 & 46.6 \\')
        marked, _total = mb.shaded_body_rows(two)
        self.assertEqual(marked, {1, 2})


class MarkingThem(unittest.TestCase):

    def test_the_class_lands_on_the_right_row(self):
        out, n = mb.mark_shaded_rows(HTML, LATEX)
        self.assertEqual(n, 1)
        self.assertIn('<tr class="row-shaded"><td>Ours</td>', out)
        self.assertIn('<tr><td>Baseline A</td>', out)

    def test_a_row_that_already_has_a_class_keeps_it(self):
        r"""`mark_body_rules` runs first and may already have put
        `rule-above` on the same row. Two `class=` attributes on one tag is
        not a row with two classes, it is a broken tag."""
        html = HTML.replace('<tr><td>Ours</td>',
                            '<tr class="rule-above"><td>Ours</td>')
        out, n = mb.mark_shaded_rows(html, LATEX)
        self.assertEqual(n, 1)
        self.assertIn('class="rule-above row-shaded"', out)
        self.assertEqual(out.count('class='), 1)

    def test_nothing_to_shade_leaves_the_html_alone(self):
        plain = LATEX.replace(
            r'\rowcolor[rgb]{ .900,  .900,  .900} ', '')
        self.assertEqual(mb.mark_shaded_rows(HTML, plain), (HTML, 0))

    def test_a_row_count_mismatch_refuses(self):
        """Shading the wrong line credits a competitor's numbers to the
        authors. On a count already known to be wrong, do nothing."""
        short = HTML.replace(
            '<tr><td>Baseline B</td><td>3</td><td>46.6</td></tr>', '')
        out, n = mb.mark_shaded_rows(short, LATEX)
        self.assertEqual(n, 0)
        self.assertNotIn('row-shaded', out)

    def test_html_with_no_tbody_is_left_alone(self):
        out, n = mb.mark_shaded_rows('<table><tr><td>x</td></tr></table>',
                                     LATEX)
        self.assertEqual(n, 0)
        self.assertNotIn('row-shaded', out)


class TheCommandHasToSurviveConversion(unittest.TestCase):
    r"""None of the above matters if the command is gone before the table
    expansion runs, which is where it was.

    `sanitize_tex` stripped `\cellcolor`, `\rowcolor` and `\columncolor`
    together as presentation-only. The damage that rule was written for is
    `\cellcolor`'s alone: it sits inside a row, between two `&`, where it
    overruns a simple table's ruler and the markdown reader tears it in half
    on the way back. `\rowcolor` sits in front of the first cell, and pandoc
    3.10.2 drops it silently on both the html and the markdown path, so
    nothing of it reaches a reader whether it is stripped or not.

    Five of them were removed from VLA-Adapter here, and the expansion --
    which reads the float verbatim and could have marked every one -- never
    saw a single one.
    """

    def sanitize(self, tex):
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.abspath(__file__))), 'scripts'))
        import arxiv_backend
        return arxiv_backend.sanitize_tex(tex)

    def test_a_row_colour_survives(self):
        tex = (r'\begin{document}' + '\n' + LATEX + '\n'
               + r'\end{document}')
        self.assertIn(r'\rowcolor', self.sanitize(tex))

    def test_a_cell_colour_still_goes(self):
        tex = (r'\begin{document}' + '\n'
               + r'a & \cellcolor{customblue!30} b \\' + '\n'
               + r'\end{document}')
        self.assertNotIn(r'\cellcolor', self.sanitize(tex))

    def test_a_column_colour_still_goes(self):
        tex = (r'\begin{document}' + '\n'
               + r'\columncolor{gray} a \\' + '\n' + r'\end{document}')
        self.assertNotIn(r'\columncolor', self.sanitize(tex))


class TheStylesheetPaintsIt(unittest.TestCase):
    """A class nothing styles is a class that does nothing."""

    def sheet(self):
        import io
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / 'scripts'
                / 'template_ebook.html')
        return io.open(path, encoding='utf-8').read()

    def test_both_sheets_style_the_shaded_row(self):
        import re
        rules = re.findall(r'tbody tr\.row-shaded[^{]*\{[^}]*\}', self.sheet())
        self.assertEqual(len(rules), 2, 'screen and print sheets')
        for rule in rules:
            self.assertIn('background', rule)

    def test_the_print_rule_sets_a_text_colour_too(self):
        """The fill is light. Without a colour beside it a dark-mode reader
        puts light type on it and the rows meant to stand out are the only
        ones that cannot be read."""
        import re
        for rule in re.findall(r'tbody tr\.row-shaded[^{]*\{[^}]*\}',
                               self.sheet()):
            self.assertIn('color:', rule.split('background')[1])


if __name__ == '__main__':
    unittest.main()
