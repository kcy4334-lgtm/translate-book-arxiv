# -*- coding: utf-8 -*-
r"""A figure caption the formatter could not reach still gets its number.

GAN lays its Figure 1 panels out in a `tabular`, which reaches the markdown
as a table; attention sets each of its Figure 2 panels under a title line in
a minipage. In both books the caption was an ordinary paragraph with no
"그림 N" while the text said "see 그림 N".
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

KO = {'figure_label': '그림'}


class Stranded(unittest.TestCase):

    def make(self, flat, images):
        self.temp = tempfile.mkdtemp(prefix='tb-strand-')
        with open(os.path.join(self.temp, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(flat)
        os.makedirs(os.path.join(self.temp, 'images'))
        for name in images:
            open(os.path.join(self.temp, 'images', name), 'wb').close()

    def tearDown(self):
        if hasattr(self, 'temp'):
            shutil.rmtree(self.temp, ignore_errors=True)

    def test_a_caption_after_a_panel_table(self):
        self.make('\\begin{figure}\\begin{tabular}{cc}\\includegraphics{fig1.pdf} &'
                  ' \\includegraphics{fig2.pdf} \\\\ (a) & (b)\\end{tabular}'
                  '\\caption{Two panels.}\\label{fig:x}\\end{figure}\n',
                  ['fig0001_fig1.png', 'fig0002_fig2.png'])
        md = ('Before.\n\n| ![image](images/fig0001_fig1.png) | '
              '![image](images/fig0002_fig2.png) |\n|:---|:---|\n| (a) | (b) |\n\n'
              ' 두 개의 패널.\n\nAfter.\n')
        out, n = mb.badge_stranded_captions(md, self.temp, KO)
        self.assertEqual(n, 1)
        self.assertIn('\n\n **그림 1 (Fig. 1)** 두 개의 패널.\n\nAfter.', out)

    def test_a_caption_after_titled_panels(self):
        self.make('\\begin{figure}\\begin{minipage}{.5\\textwidth}Left \\\\'
                  '\\includegraphics{a.png}\\end{minipage}\\begin{minipage}'
                  '{.5\\textwidth}Right \\\\\\includegraphics{b.png}\\end{minipage}'
                  '\\caption{Both.}\\end{figure}\n',
                  ['fig0001_a.png', 'fig0002_b.png'])
        md = ('Left\\\n ![image](images/fig0001_a.png)\n\n\n\nRight\\\n'
              ' ![image](images/fig0002_b.png)\n\n\n(left) and (right).\n\nNext.\n')
        out, n = mb.badge_stranded_captions(md, self.temp, KO)
        self.assertEqual(n, 1)
        self.assertIn('**그림 1 (Fig. 1)** (left) and (right).', out)

    def test_a_badged_figure_is_left(self):
        self.make('\\begin{figure}\\includegraphics{a.png}\\caption{One.}'
                  '\\end{figure}\n', ['fig0001_a.png'])
        md = '![**그림 1 (Fig. 1)** One.](images/fig0001_a.png)\n\nText.\n'
        self.assertEqual(mb.badge_stranded_captions(md, self.temp, KO), (md, 0))

    def test_a_file_shown_in_two_figures_belongs_to_each_in_turn(self):
        # DDPM: Figure 1's panel (b) is the sample grid Figure 13 shows whole.
        self.make('\\begin{figure}\\includegraphics{a.png}\\includegraphics{grid.png}'
                  '\\caption{Header.}\\end{figure}\n'
                  '\\begin{figure}\\includegraphics{other.png}\\caption{Middle.}'
                  '\\end{figure}\n'
                  '\\begin{figure}\\includegraphics{grid.png}\\caption{Whole.}'
                  '\\end{figure}\n',
                  ['fig0001_a.png', 'fig0002_grid.png', 'fig0003_other.png'])
        import numbering
        occ = numbering.figure_panel_occurrences(self.temp)
        got = numbering.assign_panels(
            ['images/fig0001_a.png', 'images/fig0002_grid.png',
             'images/fig0003_other.png', 'images/fig0002_grid.png'], occ)
        self.assertEqual([(g['float'], g['letter']) for g in got],
                         [(1, 'a'), (1, 'b'), (2, None), (3, None)])

    def test_stacked_panels_with_a_line_break_are_figures(self):
        # Neural ODE's Figure 10: `\includegraphics{a}\\ \includegraphics{b}`.
        self.make('\\begin{figure}\\includegraphics{a.png}\\\\'
                  '\\includegraphics{b.png}\\caption{Spirals.}\\end{figure}\n',
                  ['fig0001_a.png', 'fig0002_b.png'])
        md = ('![image](images/fig0001_a.png)\\\n\n![image](images/fig0002_b.png)'
              '\n\n나선.\n\nNext.\n')
        out, n = mb.format_figure_blocks(md, KO, self.temp)
        self.assertEqual(n, 2)
        self.assertIn('**그림 1 (Fig. 1)**', out)
        self.assertNotIn('.png)\\', out)

    def test_a_panel_of_two_images_takes_one_letter(self):
        # Neural ODE's Figure 10: three subfigures of two plots, (a)-(c).
        import numbering
        region = ('\\begin{subfigure}{.3\\linewidth}\\includegraphics{a1}\\\\'
                  '\\includegraphics{a2}\\caption{30 points}\\end{subfigure}'
                  '\\begin{subfigure}{.3\\linewidth}\\includegraphics{b1}'
                  '\\includegraphics{b2}\\caption{50 points}\\end{subfigure}'
                  '\\includegraphics{legend}\\caption{Spirals.}')
        resolved = ['a1', 'a2', 'b1', 'b2', 'legend']
        where = {s: region.index('{%s}' % s) for s in resolved}
        self.assertEqual(numbering._panel_letters(region, resolved, where),
                         [None, 'a', None, 'b', None])

    def test_without_subfigures_every_image_is_lettered(self):
        import numbering
        region = '\\includegraphics{x}\\includegraphics{y}\\caption{Two.}'
        where = {'x': region.index('{x}'), 'y': region.index('{y}')}
        self.assertEqual(numbering._panel_letters(region, ['x', 'y'], where),
                         ['a', 'b'])

    def test_a_caption_on_top(self):
        self.make('\\begin{figure}\\caption{Above.}\\begin{tabular}{c}'
                  '\\includegraphics{a.png}\\end{tabular}\\end{figure}\n',
                  ['fig0001_a.png'])
        md = 'Prose.\n\n위의 캡션.\n\n| ![image](images/fig0001_a.png) |\n|:---|\n\nNext.\n'
        out, n = mb.badge_stranded_captions(md, self.temp, KO)
        self.assertEqual(n, 1)
        self.assertIn('**그림 1 (Fig. 1)** 위의 캡션.', out)


if __name__ == '__main__':
    unittest.main()
