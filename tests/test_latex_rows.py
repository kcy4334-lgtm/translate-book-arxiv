# -*- coding: utf-8 -*-
r"""Which `\\` ends a row, and which is just a line break.

Four places counted row breaks by looking for `\\` and nothing else, and
all four were wrong the same way. Two of them were measured wrong rather
than reasoned wrong:

  * `\thead{Total \\ Time}` is one header cell holding a line break.
    `table_cells` read it as two, and put `Total` and `Time` in front of
    the untranslated-header gate as separate findings.
  * an `align` holding a `cases` counted three numbers where LaTeX prints
    two, and a `substack` did the same. Both are ordinary in a machine
    learning paper, and per K175 the error does not stay local: every
    equation after it is off by the difference and every `\ref` into them
    lands on the wrong one.

The third is the one that would have hurt most, and it is a REFUSAL rather
than a miscount. `verify_tables` fails a table whose row count changed. An
agent translating `\thead{Total \\ Time}` into a Korean phrase short enough
for one line takes that count from 2 to 1, and the gate refuses a correct
translation -- with a message about a dropped row, which is not what
happened.

Braces are only half of it. A `cases` is opened by `\begin`, not a brace,
so both depths have to be counted.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import latex_rows as lr

ROW = '\\\\'


class TheFlatCaseIsUnchanged(unittest.TestCase):
    """What `re.split(r'\\\\')` already got right has to keep working, or
    this is a rewrite rather than a repair."""

    def test_an_ordinary_two_row_body(self):
        self.assertEqual(lr.split_rows('a & b %s c & d' % ROW),
                         ['a & b ', ' c & d'])

    def test_a_body_with_no_break_is_one_row(self):
        self.assertEqual(lr.split_rows('a & b'), ['a & b'])

    def test_a_trailing_break_leaves_an_empty_piece(self):
        r"""`re.split` did this too, and `verify_tables` and `table_probe`
        both drop blanks themselves. Changing it would change their counts
        for every table that ends its last row with `\\`."""
        self.assertEqual(lr.split_rows('a %s' % ROW), ['a ', ''])
        self.assertEqual(lr.nonempty_rows('a %s' % ROW), ['a '])

    def test_empty_input(self):
        self.assertEqual(lr.split_rows(''), [''])
        self.assertEqual(lr.split_rows(None), [''])
        self.assertEqual(lr.nonempty_rows(''), [])


class ABreakInsideBracesEndsNothing(unittest.TestCase):

    def test_thead(self):
        r"""The measured one. `makecell`'s multi-line header cell."""
        body = '\\thead{Total %s Time} & \\thead{Method}' % ROW
        self.assertEqual(len(lr.split_rows(body)), 1)

    def test_a_thead_next_to_a_real_row_break(self):
        body = ('\\thead{Total %s Time} & A %s B & C' % (ROW, ROW))
        rows = lr.split_rows(body)
        self.assertEqual(len(rows), 2)
        self.assertIn('Total', rows[0])
        self.assertIn('Time', rows[0])

    def test_nested_braces(self):
        body = '\\thead{\\textbf{Total %s Time}} & A' % ROW
        self.assertEqual(len(lr.split_rows(body)), 1)

    def test_an_escaped_brace_does_not_move_the_depth(self):
        r"""`\{` is a literal brace in the text, not a group. Counting it
        would leave the depth stuck open and swallow every later row."""
        body = 'a \\{ b %s c \\} d %s e' % (ROW, ROW)
        self.assertEqual(len(lr.split_rows(body)), 3)


class ABreakInsideANestedEnvironmentEndsNothing(unittest.TestCase):
    r"""A `cases` is opened by `\begin`, so brace depth alone is blind."""

    def test_cases(self):
        body = ('f &= \\begin{cases} a %s b \\end{cases} %s g &= c'
                % (ROW, ROW))
        self.assertEqual(len(lr.split_rows(body)), 2)

    def test_substack(self):
        body = ('\\sum_{\\substack{i=1 %s j=2}} x &= y %s z &= w'
                % (ROW, ROW))
        self.assertEqual(len(lr.split_rows(body)), 2)

    def test_a_matrix(self):
        body = ('M &= \\begin{pmatrix} a & b %s c & d \\end{pmatrix} %s N &= P'
                % (ROW, ROW))
        self.assertEqual(len(lr.split_rows(body)), 2)

    def test_two_nested_environments_in_a_row(self):
        body = ('\\begin{cases} a %s b \\end{cases} %s '
                '\\begin{cases} c %s d \\end{cases}' % (ROW, ROW, ROW))
        self.assertEqual(len(lr.split_rows(body)), 2)

    def test_an_unclosed_environment_does_not_swallow_the_rest(self):
        """It does swallow it, and that is the honest answer: the text is
        malformed and nothing here can know where the author meant it to
        end. Written down so the behaviour is a decision, not a surprise."""
        body = '\\begin{cases} a %s b %s c' % (ROW, ROW)
        self.assertEqual(len(lr.split_rows(body)), 1)


class EnvBodyFindsItsOwnEnd(unittest.TestCase):

    def test_a_plain_environment(self):
        text = '\\begin{align}a &= b\\end{align}'
        start = text.index('}') + 1
        self.assertEqual(lr.env_body(text, start, 'align'), 'a &= b')

    def test_nesting_closes_on_the_right_one(self):
        text = ('\\begin{align}outer '
                '\\begin{align}inner\\end{align}'
                ' tail\\end{align}')
        start = text.index('}') + 1
        got = lr.env_body(text, start, 'align')
        self.assertTrue(got.startswith('outer '))
        self.assertTrue(got.endswith(' tail'))

    def test_the_starred_form_closes_it_too(self):
        text = '\\begin{align}a\\end{align*}'
        self.assertEqual(lr.env_body(text, text.index('}') + 1, 'align'), 'a')

    def test_nothing_closes_it(self):
        text = '\\begin{align}a &= b'
        self.assertEqual(lr.env_body(text, text.index('}') + 1, 'align'),
                         'a &= b')


if __name__ == '__main__':
    unittest.main()
