# -*- coding: utf-8 -*-
r"""pifont's tick and cross, which pandoc drops without a word.

VLA-Adapter's table 7 says which condition each method uses, in a column of
`\ding{51}` and `\ding{55}`. pandoc has no reader for pifont, so it emitted
nothing at all and both columns came out blank. The six success rates were
left attached to nothing, and the two rows the paper's argument turns on
became indistinguishable.

Nothing caught it. The column count was right, the row count was right, all
861 numeric values were present, and `table_probe` reported the glyph CODES
as missing values, which read as noise and was dismissed. A mark is not a
value, and no check was counting marks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class DingSubstitution(unittest.TestCase):

    def test_the_tick_and_the_cross(self):
        out, n, unknown = mb.substitute_dings(r'a \ding{51} b \ding{55} c')
        self.assertEqual(out, 'a ✓ b ✗ c')
        self.assertEqual((n, unknown), (2, []))

    def test_the_heavy_pair(self):
        out, n, _ = mb.substitute_dings(r'\ding{52}\ding{56}')
        self.assertEqual(out, '✔✘')
        self.assertEqual(n, 2)

    def test_whitespace_inside_the_call(self):
        out, n, _ = mb.substitute_dings(r'\ding { 51 }')
        self.assertEqual(out, '✓')
        self.assertEqual(n, 1)

    def test_an_unknown_code_is_left_alone_and_named(self):
        """Refuse rather than guess: an unmapped glyph prints and can be seen,
        where a guessed one silently becomes the wrong symbol."""
        out, n, unknown = mb.substitute_dings(r'\ding{51} \ding{234}')
        self.assertEqual(out, '✓ \\ding{234}')
        self.assertEqual((n, unknown), (1, ['234']))

    def test_text_with_no_dings_is_untouched(self):
        text = r'\textbf{Avg.} & 90.6 \\'
        self.assertEqual(mb.substitute_dings(text)[0], text)

    def test_a_whole_table_row_keeps_its_structure(self):
        row = r'\ding{51} & \ding{55} & RoboVLMs & 85.8 \\'
        out, n, _ = mb.substitute_dings(row)
        self.assertEqual(n, 2)
        self.assertEqual(out.count('&'), row.count('&'),
                         'the cell separators must not move')
        self.assertEqual(out.count('\\\\'), row.count('\\\\'))


if __name__ == '__main__':
    unittest.main()
