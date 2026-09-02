# -*- coding: utf-8 -*-
r"""A caption the author commented out is not a caption.

`float_units` takes comment-stripped text, so the side that COUNTS tables was
never fooled. The side that NUMBERS them reads the merged markdown, where the
raw floats must survive byte for byte and so still carry their comments.

DeeR-VLA keeps an older caption commented out above the live one. Both were
counted: its first table was numbered twice, every later table moved one on,
and the eleventh ran off the end of the number list with no badge at all --
while the count of tables and the count of numbers agreed at eleven the whole
time (K57).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class InLatexComment(unittest.TestCase):

    def at(self, text, needle):
        return mb._in_latex_comment(text, text.index(needle))

    def test_after_a_percent_on_the_same_line(self):
        self.assertTrue(self.at('% \\caption{old}\n', '\\caption'))

    def test_before_the_percent_is_not(self):
        self.assertFalse(self.at('\\caption{live} % note\n', '\\caption'))

    def test_a_percent_on_an_earlier_line_does_not_reach(self):
        self.assertFalse(self.at('% dead\n\\caption{live}\n', '\\caption'))

    def test_an_escaped_percent_opens_nothing(self):
        self.assertFalse(self.at('50\\% \\caption{live}\n', '\\caption'))

    def test_an_escaped_backslash_before_a_percent_still_opens(self):
        self.assertTrue(self.at('a\\\\% \\caption{dead}\n', '\\caption'))

    def test_the_first_line_of_the_text_works(self):
        self.assertTrue(mb._in_latex_comment('%x', 1))


class CaptionNumbering(unittest.TestCase):
    """Two captions in one float, one of them dead."""

    def float_with(self, body):
        return ('\\begin{table}\n' + body +
                '\\begin{tabular}{cc}\na & b \\\\\n\\end{tabular}\n'
                '\\end{table}\n')

    def test_the_dead_caption_is_not_extracted(self):
        text = self.float_with('% \\caption{Old wording}\n'
                               '\\caption{Live wording}\n')
        found = mb.find_raw_latex_tables(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['caption'], 'Live wording')

    def test_a_float_whose_only_caption_is_dead_has_none(self):
        text = self.float_with('% \\caption{Old wording}\n')
        self.assertIsNone(mb.find_raw_latex_tables(text)[0]['caption'])

    def test_a_live_caption_is_still_found(self):
        text = self.float_with('\\caption{Live wording}\n')
        self.assertEqual(
            mb.find_raw_latex_tables(text)[0]['caption'], 'Live wording')


class Numbering(unittest.TestCase):
    """The layer the defect actually showed up in."""

    KO = {'table_label': '표'}
    FLAT = ('\\begin{table}\n\\caption{One}\n\\end{table}\n'
            '\\begin{table}\n\\caption{Two}\n\\end{table}\n')

    def temp(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(self.FLAT)
        return d

    def table(self, captions):
        return ('\\begin{table}\n' + captions +
                '\\begin{tabular}{c}\nx \\\\\n\\end{tabular}\n'
                '\\end{table}\n\n')

    def test_a_dead_caption_does_not_take_a_number(self):
        md = (self.table('% \\caption{Old wording}\n\\caption{One}\n')
              + self.table('\\caption{Two}\n'))
        out, n = mb.number_table_captions(md, self.temp(), self.KO)
        self.assertEqual(n, 2)
        self.assertIn('\\caption{\\textbf{표 1 (Table 1)} One', out)
        self.assertIn('\\caption{\\textbf{표 2 (Table 2)} Two', out)

    def test_the_dead_caption_is_left_exactly_as_written(self):
        md = (self.table('% \\caption{Old wording}\n\\caption{One}\n')
              + self.table('\\caption{Two}\n'))
        out, _n = mb.number_table_captions(md, self.temp(), self.KO)
        self.assertIn('% \\caption{Old wording}', out)

    def test_the_last_table_still_gets_its_badge(self):
        """It was the one that ran off the end of the number list."""
        md = (self.table('% \\caption{Old}\n\\caption{One}\n')
              + self.table('\\caption{Two}\n'))
        out, _n = mb.number_table_captions(md, self.temp(), self.KO)
        self.assertIn('표 2', out)


if __name__ == '__main__':
    unittest.main()
