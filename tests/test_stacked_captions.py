# -*- coding: utf-8 -*-
r"""A float that stacks image, caption, image, caption is two figures.

PaLM sets Figures 13 and 14 in one `figure*`, divided by `\bigskip`. The
book printed both images as panels (a) and (b) of Figure 13, and Figure 14
was missing.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend
import numbering

PALM = ('\\begin{figure*}[ht]\n\\centering\n'
        '\\includegraphics[width=.9\\linewidth]{figs/a.png}\n'
        '\\caption{First {example}.}\n\\label{fig:one}\n\\bigskip\n'
        '\\includegraphics[width=.9\\linewidth]{figs/b.png}\n'
        '\\caption{Second.}\n\\label{fig:two}\n\\end{figure*}\n')


class Split(unittest.TestCase):

    def test_each_caption_takes_the_image_above_it(self):
        out, n = arxiv_backend.split_stacked_captions(PALM)
        self.assertEqual(n, 1)
        self.assertEqual(out.count('\\begin{figure*}'), 2)
        first, second = out.split('\\end{figure*}')[:2]
        self.assertIn('a.png', first)
        self.assertIn('\\label{fig:one}', first)
        self.assertNotIn('b.png', first)
        self.assertIn('b.png', second)
        self.assertIn('\\label{fig:two}', second)

    def test_caption_above_content_is_left(self):
        tex = ('\\begin{figure}\\caption{One.}\\includegraphics{a}'
               '\\caption{Two.}\\includegraphics{b}\\end{figure}')
        self.assertEqual(arxiv_backend.split_stacked_captions(tex), (tex, 0))

    def test_captioned_minipages_are_left_to_their_own_split(self):
        tex = ('\\begin{figure}\\begin{minipage}{.5\\linewidth}\\includegraphics{a}'
               '\\caption{One.}\\end{minipage}\\begin{minipage}{.5\\linewidth}'
               '\\includegraphics{b}\\caption{Two.}\\end{minipage}\\end{figure}')
        self.assertEqual(arxiv_backend.split_stacked_captions(tex), (tex, 0))

    def test_one_caption_is_left(self):
        tex = ('\\begin{figure}\\includegraphics{a}\\includegraphics{b}'
               '\\caption{Both.}\\end{figure}')
        self.assertEqual(arxiv_backend.split_stacked_captions(tex), (tex, 0))


class CentredFigures(unittest.TestCase):
    """planck centres 35 figures in a `center`; pandoc wrote each as a bare
    image and a caption paragraph, and the book numbered none of them."""

    def test_center_becomes_centering(self):
        tex = ('\\begin{figure}\n\\begin{center}\n\\includegraphics{a}\n'
               '\\end{center}\n\\caption{A.}\n\\end{figure}\n'
               'text \\begin{center}kept\\end{center}')
        out, n = arxiv_backend.unwrap_centered_figures(tex)
        self.assertEqual(n, 1)
        self.assertIn('\\begin{figure}\n\\centering\n\\includegraphics{a}\n\n'
                      '\\caption{A.}', out)
        self.assertIn('text \\begin{center}kept\\end{center}', out)


class Units(unittest.TestCase):

    def test_the_second_image_belongs_to_the_second_figure(self):
        units = numbering.float_units(PALM)
        self.assertEqual([u['number'] for u in units], [1, 2])
        first = PALM[units[0]['start']:units[0]['stop']]
        second = PALM[units[1]['start']:units[1]['stop']]
        self.assertNotIn('b.png', first)
        self.assertIn('b.png', second)
        self.assertEqual(units[0]['labels'], ['fig:one'])
        self.assertEqual(units[1]['labels'], ['fig:two'])

    def test_a_label_after_a_vspace_stays_with_its_caption(self):
        # ResNet's Tables 7 and 8 share a float; `\vspace` stands between
        # each caption and its label.
        tex = ('\\begin{table}\\begin{tabular}{c}a\\end{tabular}\n'
               '\\caption{VOC.}\n\\vspace{-.5em}\n\\label{tab:voc}\n'
               '\\begin{tabular}{c}b\\end{tabular}\n'
               '\\caption{COCO.}\n\\vspace{-.5em}\n\\label{tab:coco}\n'
               '\\end{table}')
        units = numbering.float_units(tex)
        self.assertEqual([u['labels'] for u in units],
                         [['tab:voc'], ['tab:coco']])

    def test_a_split_figure_keeps_a_label_after_spacing(self):
        tex = PALM.replace('\\caption{First {example}.}\n',
                           '\\caption{First {example}.}\n\\vspace{-1em}\n')
        out, n = arxiv_backend.split_stacked_captions(tex)
        self.assertEqual(n, 1)
        first = out.split('\\end{figure*}')[0]
        self.assertIn('\\label{fig:one}', first)

    def test_a_center_around_both_images_is_left(self):
        tex = PALM.replace('\\centering\n', '\\begin{center}\n').replace(
            '\\label{fig:two}\n', '\\label{fig:two}\n\\end{center}\n')
        self.assertEqual(arxiv_backend.split_stacked_captions(tex), (tex, 0))

    def test_caption_above_content_still_cuts_at_the_caption(self):
        tex = ('\\begin{figure}\\caption{One.}\\includegraphics{a}'
               '\\caption{Two.}\\includegraphics{b}\\end{figure}')
        units = numbering.float_units(tex)
        self.assertIn('{a}', tex[units[0]['start']:units[0]['stop']])
        self.assertIn('{b}', tex[units[1]['start']:units[1]['stop']])


if __name__ == '__main__':
    unittest.main()
