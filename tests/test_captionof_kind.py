# -*- coding: utf-8 -*-
r"""`\captionof{table}` steps the table counter, whatever float it sits in.

DDPM sets its first two tables side by side, each in a minipage inside one
`figure`, captioned with `\captionof{table}`. Counted as figures, the book
printed them as figures 3 and 4 and every later figure two too high, so the
LSUN samples the paper prints as Figure 3 read Figure 5.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import numbering

DDPM = (r'\begin{figure}\includegraphics{a}\caption{Samples.}\label{fig:a}\end{figure}'
        '\n' r'\begin{figure}' '\n'
        r'\begin{minipage}{0.55\textwidth}\captionof{table}{CIFAR10 results.}'
        r'\label{table:cifar}\begin{tabular}{l}x\end{tabular}\end{minipage}\hfill'
        '\n' r'\begin{minipage}{0.4\textwidth}\captionof{table}{Ablation.}'
        r'\label{table:ablation}\begin{tabular}{l}y\end{tabular}\end{minipage}'
        '\n' r'\end{figure}' '\n'
        r'\begin{figure}\includegraphics{b}\caption{LSUN Church.}'
        r'\label{fig:church}\end{figure}' '\n'
        r'\begin{table}\caption{FID.}\label{table:fid}\end{table}')


class CaptionofKind(unittest.TestCase):

    def test_ddpm_numbers(self):
        got = [(u['kind'], u['number'], u['labels'])
               for u in numbering.float_units(DDPM)]
        self.assertEqual(got, [
            ('figure', 1, ['fig:a']),
            ('table', 1, ['table:cifar']),
            ('table', 2, ['table:ablation']),
            ('figure', 2, ['fig:church']),
            ('table', 3, ['table:fid']),
        ])

    def test_captionof_figure_inside_a_table_is_a_figure(self):
        tex = (r'\begin{table}\captionof{figure}{A plot.}\end{table}'
               r'\begin{table}\caption{A table.}\end{table}')
        self.assertEqual([(u['kind'], u['number'])
                          for u in numbering.float_units(tex)],
                         [('figure', 1), ('table', 1)])


if __name__ == '__main__':
    unittest.main()
