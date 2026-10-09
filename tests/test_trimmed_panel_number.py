# -*- coding: utf-8 -*-
r"""A cropped panel keeps the number of the figure it belongs to.

`apply_graphics_trim` writes a cropped copy next to the extracted image and
points the manuscript at it: `fig0011_attn_a.png` becomes
`fig0011_attn_a_trim.png`. The panel map is keyed on the extracted names, so
the cropped one was not found, and its number came from the digits in its
file name -- the extraction order. ViT's figure 10, three cropped panels,
printed as figures 11, 12 and 13, two of them with empty captions, and each
of those numbers then appeared twice in the book.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402

KO = {'figure_label': '그림'}
BS = '\\'
OPTS = '[width=0.3' + BS + 'linewidth,trim=0 0 0 10,clip]'
FLAT = ''.join(
    [BS + 'begin{figure}' + BS + 'includegraphics{figs/one.pdf}'
     + BS + 'caption{First.}' + BS + 'end{figure}' + '\n']
    + [BS + 'begin{figure}']
    + [BS + 'includegraphics' + OPTS + '{figs/attn_%s.pdf}' % c for c in 'abc']
    + [BS + 'caption{Attention maps.}' + BS + 'end{figure}' + '\n'])


class TrimmedPanels(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        images = os.path.join(self.dir, 'images')
        os.makedirs(images)
        names = ['fig0001_one.png'] + ['fig%04d_attn_%s.png' % (i, c)
                                       for i, c in ((11, 'a'), (12, 'b'), (13, 'c'))]
        names += [n.replace('.png', '_trim.png') for n in names[1:]]
        for name in names:
            open(os.path.join(images, name), 'wb').close()
        with open(os.path.join(self.dir, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(FLAT)

    def test_panels_on_one_line_are_still_one_numbered_figure(self):
        """ViT's figure 13: two panels with an `\\hspace` between them
        arrived on one line and printed with no number or caption."""
        md = ('![](images/fig0001_one.png)\n\n첫 그림.\n\n'
              '![](images/fig0011_attn_a_trim.png)  ![](images/fig0012_attn_b_trim.png)'
              '  ![](images/fig0013_attn_c_trim.png)\n\n'
              '어텐션 지도.\n\n다음 문단.\n')
        out, _count = mb.format_figure_blocks(md, KO, self.dir)
        self.assertIn('**그림 2 (Fig. 2)** 어텐션 지도.', out)

    def test_cropped_panels_print_as_one_figure_with_its_number(self):
        md = ('![](images/fig0001_one.png)\n\n첫 그림.\n\n'
              + ''.join('![](images/fig%04d_attn_%s_trim.png)\n\n' % (i, c)
                        for i, c in ((11, 'a'), (12, 'b'), (13, 'c')))
              + '어텐션 지도.\n\n다음 문단.\n')
        out, _count = mb.format_figure_blocks(md, KO, self.dir)
        self.assertIn('**그림 2 (Fig. 2)**', out)
        for wrong in ('그림 11', '그림 12', '그림 13'):
            self.assertNotIn(wrong, out)


if __name__ == '__main__':
    unittest.main()
