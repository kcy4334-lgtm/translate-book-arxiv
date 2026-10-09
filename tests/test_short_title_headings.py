# -*- coding: utf-8 -*-
r"""`\subsection[Short]{Full title}` is a numbered heading like any other.

DDPM writes three of its four subsections in section 3 with a short title for
the table of contents. Every heading pattern expected the brace right after
the command, so those three were not headings at all: `\cref` to 3.2 printed
"3" and to 3.4 printed "3.1", eleven references in all.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

FLAT = ('\\section{Background}\n'
        '\\section{Diffusion models}\n'
        '\\subsection[Forward process]{Forward process and $L_T$}\n'
        '\\subsection[Reverse process]{Reverse process and $L_{1:T-1}$}'
        ' \\label{sec:revproc}\n'
        '\\subsection[Data scaling]{Data scaling, decoder, and $L_0$}\n'
        '\\subsection{Simplified training objective}\n'
        '\\label{sec:simplified}\n')


class ShortTitles(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix='tb-short-')
        with open(os.path.join(self.temp, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(FLAT)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_labels_take_the_subsection_number(self):
        index = mb.build_label_index(self.temp)
        self.assertEqual(index['sec:revproc'][0], '2.2')
        self.assertEqual(index['sec:simplified'][0], '2.4')

    def test_the_heading_is_read_with_its_full_title(self):
        heads = mb.read_tex_headings(self.temp)
        self.assertEqual(len(heads), 6)
        self.assertIn('Reverse process and $L_{1:T-1}$', heads[3][1])


if __name__ == '__main__':
    unittest.main()
