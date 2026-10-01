# -*- coding: utf-8 -*-
r"""Three `\subref` printed as LaTeX beside the plots they pointed at.

Two faults in one caption, both in Neural ODE's figure 8.

1. The panels live inside a `wrapfigure`, and the scanner looked only for
   `figure` — so it found no panels at all and every `\subref` in the caption
   survived into the book as `\subref{subfig:RNN}`. `_label_token_re` in the
   same file already accepts `SC|wrap|sideways|long|floating`; this one did
   not.

2. Lettering by panel position gave the last panel `d`. `subcaption` steps the
   sub-counter on `\caption`, not on the environment, and the third of the four
   panels is a legend with no caption. The paper prints (a) (b) (c) — read out
   of the source PDF, not assumed.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


def panel(label=None, caption=True, env='subfigure'):
    body = '\\includegraphics{x}\n'
    if caption:
        body += '\\caption{A panel}\n'
    if label:
        body += '\\label{%s}\n' % label
    return '\\begin{%s}[b]{0.3\\linewidth}\n%s\\end{%s}\n' % (env, body, env)


class _Flat(unittest.TestCase):
    def make(self, body):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with io.open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(body)
        return d


class PanelsInsideAnyFloatAreFound(_Flat):
    def test_a_plain_figure(self):
        d = self.make('\\begin{figure}\n' + panel('a1') + panel('b1') +
                      '\\end{figure}\n')
        self.assertEqual(mb.build_subfigure_letters(d),
                         {'a1': 'a', 'b1': 'b'})

    def test_a_wrapfigure(self):
        d = self.make('\\begin{wrapfigure}[28]{r}{0.5\\textwidth}\n'
                      + panel('a1') + panel('b1') + '\\end{wrapfigure}\n')
        self.assertEqual(mb.build_subfigure_letters(d),
                         {'a1': 'a', 'b1': 'b'})

    def test_an_scfigure_and_a_sidewaysfigure(self):
        for env in ('SCfigure', 'sidewaysfigure', 'floatingfigure'):
            d = self.make('\\begin{%s}\n%s\\end{%s}\n'
                          % (env, panel('a1'), env))
            self.assertEqual(mb.build_subfigure_letters(d), {'a1': 'a'},
                             '%s was not scanned' % env)

    def test_a_starred_figure(self):
        d = self.make('\\begin{figure*}\n' + panel('a1') + '\\end{figure*}\n')
        self.assertEqual(mb.build_subfigure_letters(d), {'a1': 'a'})


class OnlyCaptionedPanelsAreLettered(_Flat):
    def test_an_uncaptioned_panel_takes_no_letter_and_does_not_advance(self):
        # Neural ODE's figure 8, in miniature: the legend sits third.
        d = self.make('\\begin{wrapfigure}[28]{r}{0.5\\textwidth}\n'
                      + panel('RNN') + panel('method')
                      + panel(None, caption=False)
                      + panel('Latent-traj') + '\\end{wrapfigure}\n')
        self.assertEqual(mb.build_subfigure_letters(d),
                         {'RNN': 'a', 'method': 'b', 'Latent-traj': 'c'})

    def test_an_uncaptioned_panel_with_a_label_gets_nothing(self):
        d = self.make('\\begin{figure}\n' + panel('a1')
                      + panel('legend', caption=False) + '\\end{figure}\n')
        got = mb.build_subfigure_letters(d)
        self.assertEqual(got.get('a1'), 'a')
        self.assertNotIn('legend', got)

    def test_a_captioned_subfloat_is_lettered(self):
        d = self.make('\\begin{figure}\n'
                      '\\subfloat[First]{\\includegraphics{x}\\label{s1}}\n'
                      '\\subfloat[Second]{\\includegraphics{y}\\label{s2}}\n'
                      '\\end{figure}\n')
        self.assertEqual(mb.build_subfigure_letters(d),
                         {'s1': 'a', 's2': 'b'})

    def test_an_uncaptioned_subfloat_does_not_advance(self):
        d = self.make('\\begin{figure}\n'
                      '\\subfloat[First]{\\includegraphics{x}\\label{s1}}\n'
                      '\\subfloat{\\includegraphics{leg}}\n'
                      '\\subfloat[Third]{\\includegraphics{z}\\label{s3}}\n'
                      '\\end{figure}\n')
        self.assertEqual(mb.build_subfigure_letters(d),
                         {'s1': 'a', 's3': 'b'})

    def test_a_figure_with_no_panels_yields_nothing(self):
        d = self.make('\\begin{figure}\n\\includegraphics{x}\n'
                      '\\caption{Whole}\\label{f1}\n\\end{figure}\n')
        self.assertEqual(mb.build_subfigure_letters(d), {})


if __name__ == '__main__':
    unittest.main()
