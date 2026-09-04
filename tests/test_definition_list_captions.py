# -*- coding: utf-8 -*-
r"""A definition list opens with `: ` and so does a table caption.

`number_table_captions` treated every `^: ` line as a pandoc table caption.
It is also pandoc's DEFINITION LIST syntax, and VLA-Adapter carries fourteen
of those, holding its Question, Key Finding and Conclusion items, with no
markdown table anywhere in the book.

Ten of its fifteen table numbers landed on that prose and ten real tables
were left with none, so the page printed a table number over a question and
nothing over the table a reader had been sent to. Every count agreed the
whole time: fifteen numbers issued, fifteen badges written, fifteen tables
present.

What separates them is what they touch. A caption abuts its table; a
definition abuts its term.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


def offsets(md):
    return [at for _start, at in mb.markdown_table_captions(md)]


class DefinitionListsAreNotCaptions(unittest.TestCase):

    def test_a_definition_list_is_not_a_caption(self):
        md = ('Question 1.1\n\n'
              ': the layer whose features serve the policy best\n\n'
              'and the text carries on.\n')
        self.assertEqual(offsets(md), [])

    def test_the_shape_this_paper_ships(self):
        md = (': `\\thinspace `{=latex}***Question 1.1.** which layer?*\n\n'
              ': `\\thinspace `{=latex}***Key Finding 1.** the deep ones.*\n')
        self.assertEqual(offsets(md), [])

    def test_a_caption_under_its_table_is_one(self):
        md = ('| a | b |\n|---|---|\n| 1 | 2 |\n\n'
              ': Results on the benchmark\n')
        self.assertEqual(len(offsets(md)), 1)

    def test_a_caption_above_its_table_is_one(self):
        md = (': Results on the benchmark\n\n'
              '| a | b |\n|---|---|\n| 1 | 2 |\n')
        self.assertEqual(len(offsets(md)), 1)

    def test_a_grid_table_counts_as_a_table(self):
        md = ('+---+---+\n| a | b |\n+===+===+\n| 1 | 2 |\n+---+---+\n\n'
              ': Results\n')
        self.assertEqual(len(offsets(md)), 1)

    def test_a_blank_line_between_them_is_allowed(self):
        md = ('| a | b |\n|---|---|\n\n\n\n: Results\n')
        self.assertEqual(len(offsets(md)), 1)

    def test_a_definition_list_beside_a_table_elsewhere_is_still_prose(self):
        """A table in the document does not make every `: ` line a caption."""
        md = ('| a | b |\n|---|---|\n| 1 | 2 |\n\n'
              ': Results\n\n'
              'Question 1.1\n\n'
              ': not a caption, a definition\n')
        self.assertEqual(len(offsets(md)), 1)


class TheBadgesLandOnTables(unittest.TestCase):
    """End to end through `number_table_captions`, with a fake temp dir."""

    def setUp(self):
        import shutil
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def flat(self, text):
        with open(os.path.join(self.dir, 'flat.tex'), 'w',
                  encoding='utf-8') as fh:
            fh.write(text)

    def test_prose_takes_no_number_and_the_table_does(self):
        self.flat('\\begin{table}\\begin{tabular}{c}a\\end{tabular}'
                  '\\caption{Real}\\end{table}\n')
        md = ('Question 1.1\n\n'
              ': a definition, not a caption\n\n'
              '\\begin{table}\\begin{tabular}{c}a\\end{tabular}'
              '\\caption{Real}\\end{table}\n')
        out, used = mb.number_table_captions(md, self.dir, {})
        self.assertEqual(used, 1)
        self.assertIn('Table 1', out)
        head = out[:out.index('\\begin{table}')]
        self.assertNotIn('Table 1', head,
                         'the badge must not sit on the definition list')


class BadgePlacementIsChecked(unittest.TestCase):
    r"""The count agreed while ten of fifteen badges sat on prose.

    `number_table_captions` reported 15 numbers written and 15 were written.
    Ten were on Question and Key Finding items. So the build now asks where
    each badge IS, and refuses rather than reporting a number.
    """

    KO = {'table_label': '표'}

    def test_a_badge_inside_a_float_is_fine(self):
        md = ('\\begin{table}\\begin{tabular}{c}a\\end{tabular}'
              '\\caption{\\textbf{표 1 (Table 1)} Real}\\end{table}\n')
        ok, detail = mb.check_badge_placement(md, self.KO)
        self.assertTrue(ok, detail)

    def test_a_badge_on_a_markdown_table_caption_is_fine(self):
        md = ('| a | b |\n|---|---|\n| 1 | 2 |\n\n'
              ': **표 1 (Table 1)** Results\n')
        ok, detail = mb.check_badge_placement(md, self.KO)
        self.assertTrue(ok, detail)

    def test_a_badge_on_prose_is_caught(self):
        """The shape that shipped: a definition list wearing a table number."""
        md = ('Question 1.1\n\n'
              ': **표 1 (Table 1)** which layer serves the policy best?\n')
        ok, detail = mb.check_badge_placement(md, self.KO)
        self.assertFalse(ok)
        self.assertIn('prose', detail)

    def test_a_badge_in_an_ordinary_paragraph_is_caught(self):
        md = 'The results are summarised. **표 3 (Table 3)** and so on.\n'
        ok, _detail = mb.check_badge_placement(md, self.KO)
        self.assertFalse(ok)

    def test_a_book_with_no_tables_passes(self):
        ok, detail = mb.check_badge_placement('Just prose.\n', self.KO)
        self.assertTrue(ok, detail)


if __name__ == '__main__':
    unittest.main()
