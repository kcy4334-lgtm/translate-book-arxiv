# -*- coding: utf-8 -*-
r"""A `\label` in an align names its row, and each row takes a number.

The label index counted an align once. ViT's four-row align carries a label
on every row, and all four resolved to "식 (1)"; the next align's label read
(2) where the paper prints (5). `_numbers_for_block` already counted rows, so
the printed numbers and the references disagreed from the first align on.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import numbering  # noqa: E402

BS = '\\'
NL = '\n'


def _align(rows, star=''):
    return (BS + 'begin{align%s}' % star + NL
            + (' ' + BS + BS + NL).join(rows) + NL
            + BS + 'end{align%s}' % star + NL)


class AlignRows(unittest.TestCase):

    def _index(self, tex):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(tex)
        return numbering.build_label_index(d)

    def test_each_row_label_takes_its_own_number(self):
        tex = (_align(['a &= b ' + BS + 'label{eq:one}',
                       'c &= d ' + BS + 'label{eq:two}',
                       'e &= f ' + BS + 'label{eq:three}'])
               + _align(['g &= h ' + BS + 'label{eq:four}']))
        index = self._index(tex)
        self.assertEqual([index[k][0] for k in
                          ('eq:one', 'eq:two', 'eq:three', 'eq:four')],
                         ['1', '2', '3', '4'])

    def test_a_nonumber_row_takes_none(self):
        tex = (_align(['a &= b ' + BS + 'nonumber',
                       'c &= d ' + BS + 'label{eq:x}'])
               + BS + 'begin{equation}y' + BS + 'label{eq:y}'
               + BS + 'end{equation}' + NL)
        index = self._index(tex)
        self.assertEqual(index['eq:x'][0], '1')
        self.assertEqual(index['eq:y'][0], '2')

    def test_a_label_on_an_unnumbered_row_names_the_next_numbered_one(self):
        """GAN labels its `\\nonumber` first row and cites the (1) below."""
        tex = _align([BS + 'label{eq:G} C &= a ' + BS + 'nonumber',
                      '&= b', '&= c'])
        index = self._index(tex)
        self.assertEqual(index['eq:G'][0], '1')

    def test_a_starred_align_takes_none(self):
        tex = (_align(['a &= b', 'c &= d'], '*')
               + BS + 'begin{equation}y' + BS + 'label{eq:y}'
               + BS + 'end{equation}' + NL)
        self.assertEqual(self._index(tex)['eq:y'][0], '1')

    def test_the_index_agrees_with_the_printed_count(self):
        tex = (_align(['a &= b', 'c &= d ' + BS + 'label{eq:second}'])
               + _align(['e &= f ' + BS + 'label{eq:third}']))
        md = '$$' + _align(['a &= b', 'c &= d']) + '$$\n\n$$' + _align(['e &= f']) + '$$'
        printed = [n for _s, _e, n in numbering.equation_numbers(md)]
        self.assertEqual(printed, [None, 3])
        self.assertEqual(self._index(tex)['eq:third'][0], '3')
        self.assertEqual(self._index(tex)['eq:second'][0], '2')


if __name__ == '__main__':
    unittest.main()
