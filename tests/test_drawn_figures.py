# -*- coding: utf-8 -*-
r"""A figure drawn in TikZ/PGF is cropped from the original PDF.

VAE's graphical model, BERT's pre-training plot and two of DDPM's figures
(five pgfplots between them) are drawn in the source, have no image file,
and were left out of their books with caption and number.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import drawn_figures as dfig

try:
    import pymupdf
except ImportError:                     # pragma: no cover - optional
    pymupdf = None

FLAT = ('\\begin{document}\n'
        '\\begin{figure}\\includegraphics{a.png}\\caption{First.}\\label{fig:a}'
        '\\end{figure}\n'
        '\\begin{figure}\\centering\n\\begin{tikzpicture}\\draw (0,0)--(1,1);'
        '\\end{tikzpicture}\\hfill\\begin{tikzpicture}\\draw (0,0)--(1,0);'
        '\\end{tikzpicture}\n\\caption{Drawn.}\\label{fig:drawn}\\end{figure}\n'
        '%\\begin{figure}\\begin{tikzpicture}\\end{tikzpicture}\\end{figure}\n'
        '\\end{document}\n')


class FindingThem(unittest.TestCase):

    def test_only_the_drawn_numbered_figure(self):
        found = dfig.drawn_figures(FLAT)
        self.assertEqual([n for n, _s, _e in found], [2])
        _n, start, stop = found[0]
        self.assertIn('Drawn.', FLAT[start:stop])

    def test_the_drawing_becomes_one_image(self):
        _n, start, stop = dfig.drawn_figures(FLAT)[0]
        out = dfig._swap_drawing(FLAT[start:stop], 'tb_drawn_figure_2.png')
        self.assertEqual(out.count('\\includegraphics'), 1)
        self.assertNotIn('tikzpicture', out)
        self.assertIn('\\caption{Drawn.}\\label{fig:drawn}', out)

    def test_gnuplot_setup_goes_with_the_drawing(self):
        # Shor's Figure 5.1, as gnuplot's LaTeX terminal writes it.
        figure = ('\\begin{figure}\n\\begin{center}\n'
                  '\\setlength{\\unitlength}{0.240900pt}\n'
                  '\\ifx\\plotpoint\\undefined\\newsavebox{\\plotpoint}\\fi\n'
                  '\\sbox{\\plotpoint}{\\rule[-0.175pt]{0.350pt}{0.350pt}}%\n'
                  '\\begin{picture}(1500,900)(0,0)\n'
                  '\\sbox{\\plotpoint}{\\rule[-0.175pt]{0.350pt}{0.350pt}}%\n'
                  '\\put(242,158){\\makebox(0,0)[r]{0.00}}\n\\end{picture}\n'
                  '\\end{center}\n\\caption{Plot.}\\label{p}\n\\end{figure}')
        out = dfig._swap_drawing(figure, 'tb_drawn_figure_5_1.png')
        self.assertEqual(out, '\\begin{figure}\n\\begin{center}\n\n\n\n'
                         '\\includegraphics[width=\\linewidth]'
                         '{tb_drawn_figure_5_1.png}\n\\end{center}\n'
                         '\\caption{Plot.}\\label{p}\n\\end{figure}')


@unittest.skipUnless(pymupdf, 'pymupdf is not installed')
class CroppingThem(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='tb-drawn-')
        self.pdf = os.path.join(self.dir, 'paper.pdf')
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), 'Body text above the figure, a full line '
                         'of prose that runs across the column.', fontsize=10)
        shape = page.new_shape()
        shape.draw_rect(pymupdf.Rect(200, 150, 400, 300))
        shape.draw_line((200, 300), (400, 150))
        shape.finish(color=(0, 0, 0))
        shape.commit()
        page.insert_text((290, 315), 'x axis', fontsize=8)
        page.insert_text((72, 340), 'Figure 2: Drawn.', fontsize=10)
        doc.save(self.pdf)
        doc.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_drawing_above_its_caption_is_cropped(self):
        doc = pymupdf.open(self.pdf)
        try:
            pno, clip = dfig.locate(doc, 2)
        finally:
            doc.close()
        self.assertEqual(pno, 0)
        self.assertLess(clip.y0, 150)
        self.assertGreater(clip.y1, 300)          # the axis label too
        self.assertGreater(clip.y0, 100)          # not the prose above

    def test_the_source_points_at_the_crop(self):
        out, done = dfig.crop_drawn_figures(FLAT, self.pdf, self.dir)
        self.assertEqual(done, [(2, 'tb_drawn_figure_2.png')])
        self.assertTrue(os.path.isfile(os.path.join(self.dir,
                                                    'tb_drawn_figure_2.png')))
        self.assertIn('\\includegraphics[width=\\linewidth]'
                      '{tb_drawn_figure_2.png}', out)

    def test_a_figure_not_in_the_pdf_is_left(self):
        flat = FLAT.replace('Drawn.', 'Elsewhere.').replace('fig:drawn', 'fig:x')
        doc = pymupdf.open(self.pdf)
        doc.close()
        missing = flat.replace('\\begin{figure}\\includegraphics{a.png}'
                               '\\caption{First.}\\label{fig:a}\\end{figure}\n', '')
        out, done = dfig.crop_drawn_figures(missing, self.pdf, self.dir)
        self.assertEqual((out, done), (missing, []))


@unittest.skipUnless(pymupdf, 'pymupdf is not installed')
class RulesPaintedAsImages(unittest.TestCase):
    """Shor's Figure 5.1: a gnuplot `picture` that Ghostscript painted as
    one-pixel images stretched over each \\rule, with no vector drawing."""

    def test_the_rules_are_the_drawing_and_the_axis_title_comes_along(self):
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        dot = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 1, 1), False)
        dot.clear_with(0)
        for rect in [(190, 150, 470, 151), (190, 300, 470, 301),
                     (190, 150, 191, 300), (469, 150, 470, 300),
                     (300, 200, 301, 300)]:
            page.insert_image(pymupdf.Rect(rect), pixmap=dot)
        page.insert_text((170, 305), '0.0', fontsize=8)
        page.insert_text((138, 230), 'P', fontsize=9)
        page.insert_text((118, 380), 'Figure 5.1: The probability.', fontsize=10)
        try:
            self.assertEqual(page.get_drawings(), [])
            pno, clip = dfig.locate(doc, '5.1')
        finally:
            doc.close()
        self.assertEqual(pno, 0)
        self.assertLess(clip.y0, 150)
        self.assertLess(clip.x0, 138)              # the "P" beside the axis
        self.assertLess(clip.y1, 370)              # not the caption


if __name__ == '__main__':
    unittest.main()
