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
    """planck centres 18 figures in a `center`; pandoc wrote each as a bare
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


class BoxesAndTextFigures(unittest.TestCase):
    """gpt3's generated articles sit in `\\fbox{\\parbox{..}{..}}` inside a
    figure; its dataset examples are figures holding a table."""

    def test_boxes_are_unwrapped(self):
        tex = ('\\centering\\noindent\\fbox{ \\tt \\parbox{0.9\\linewidth}{'
               'Title: Split \\\\ Article: text} } and \\setlength{\\fboxsep}{2pt}')
        out, n = arxiv_backend.unwrap_boxes(tex)
        self.assertEqual(n, 2)
        self.assertIn('\\noindent \\tt Title: Split \\\\ Article: text ', out)
        self.assertIn('\\setlength{\\fboxsep}{2pt}', out)

    def test_a_group_colour_becomes_textcolor_outside_maths_only(self):
        tex = ('\\tt{\\color{gray}Poor input.\\\\ Good.} \\textbf{Fixed} '
               '$a + {\\color{red} b}$ % {\\color{x} $\n'
               'and {\\color{blue} c} done')
        out, n = arxiv_backend.scoped_color_declarations(tex)
        self.assertEqual(n, 2)
        self.assertIn('\\tt{\\textcolor{gray}{Poor input.\\\\ Good.}}', out)
        self.assertIn('$a + {\\color{red} b}$', out)
        self.assertIn('{\\textcolor{blue}{ c}}', out)

    def test_a_colour_in_an_algorithm_is_left_to_the_algorithm_reader(self):
        tex = ('\\begin{algorithmic}\n{\\color{red}\\STATE $x$}\n'
               '\\end{algorithmic} {\\color{red} text}')
        out, n = arxiv_backend.scoped_color_declarations(tex)
        self.assertEqual(n, 1)
        self.assertIn('{\\color{red}\\STATE $x$}', out)
        self.assertIn('{\\textcolor{red}{ text}}', out)

    def test_a_text_figure_caption_gets_its_number(self):
        import tempfile, shutil
        temp = tempfile.mkdtemp(prefix='tb-textfig-')
        self.addCleanup(shutil.rmtree, temp, True)
        with open(os.path.join(temp, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write('\\begin{figure}\\includegraphics{a}\\caption{A.}'
                     '\\label{fig:a}\\end{figure}\n'
                     '\\begin{figure}\\begin{tabular}{l}x\\end{tabular}'
                     '\\caption{Example.}\\label{eval:ANLI R2}\\end{figure}\n')
        md = (':::: {#fig:a .figure}\n![](a)\n\n::: caption\nA.\n:::\n::::\n\n'
              ':::: {#eval:ANLI R2 .figure latex-placement="!h"}\n'
              '| x |\n|---|\n\n::: caption\nExample.\n:::\n::::\n')
        out, n = arxiv_backend.badge_imageless_figures(md, temp, 'ko')
        self.assertEqual(n, 1)
        self.assertIn('::: caption\n**그림 2 (Fig. 2)** Example.', out)
        self.assertIn('::: caption\nA.', out)          # the image figure: build's job


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
