# -*- coding: utf-8 -*-
r"""Captions in minipages of their own split a float at the minipage.

`float_units` cut a float at each later caption's START. ViT's figures 3 and
4 are two minipages in one figure, image then caption in each, so the cut
fell after figure 4's image: figure 3 owned both images, and the book printed
them as one figure with panels (a) and (b).
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import numbering  # noqa: E402

FIG = ("\\begin{figure}\n"
       "\\begin{minipage}[t]{0.47\\textwidth}\n"
       "\\includegraphics{images/first}\n\\caption{First.}\\label{fig:a}\n"
       "\\end{minipage}\\;\\;\n"
       "\\begin{minipage}[t]{0.47\\textwidth}\n"
       "\\includegraphics{images/second}\n\\caption{Second.}\\label{fig:b}\n"
       "\\end{minipage}\n\\end{figure}\n")


class MinipageUnits(unittest.TestCase):

    def test_each_minipage_owns_its_image(self):
        units = numbering.float_units(FIG)
        self.assertEqual([u['number'] for u in units], [1, 2])
        first = FIG[units[0]['start']:units[0]['stop']]
        second = FIG[units[1]['start']:units[1]['stop']]
        self.assertIn('images/first', first)
        self.assertNotIn('images/second', first)
        self.assertIn('images/second', second)
        self.assertEqual(units[1]['labels'], ['fig:b'])

    def test_the_panels_are_two_figures(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, 'images'))
        for name in ('fig0003_first.png', 'fig0004_second.png'):
            open(os.path.join(d, 'images', name), 'wb').close()
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(FIG)
        panels = numbering.figure_panels(d)
        self.assertEqual(panels['fig0003_first.png']['float'], 1)
        self.assertEqual(panels['fig0004_second.png']['float'], 2)
        self.assertIsNone(panels['fig0003_first.png']['letter'])

    def test_caption_first_minipages_still_split(self):
        """AlphaQ: caption, then table, in each minipage."""
        tex = ("\\begin{table*}\\begin{minipage}{.5\\textwidth}\\caption{A.}"
               "\\begin{tabular}{c}1\\end{tabular}\\end{minipage}"
               "\\begin{minipage}{.5\\textwidth}\\caption{B.}"
               "\\begin{tabular}{c}2\\end{tabular}\\end{minipage}\\end{table*}")
        units = numbering.float_units(tex)
        self.assertEqual(len(units), 2)
        self.assertIn('{c}1', tex[units[0]['start']:units[0]['stop']])
        self.assertIn('{c}2', tex[units[1]['start']:units[1]['stop']])


if __name__ == '__main__':
    unittest.main()
