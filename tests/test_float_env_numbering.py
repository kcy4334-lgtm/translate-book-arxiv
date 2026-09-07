# -*- coding: utf-8 -*-
r"""An unusual float environment still takes its number.

LaTeX counts a `sidewaysfigure` as a figure and a `floatingtable` as a table,
so missing one does not lose a single number: every float after it is off by
one and every `\ref` into them points at the wrong picture. That happened
once already, with `SCfigure` in CafeQ.

`corpus_census digest` listed `sidewaysfigure` and `floatingtable` under
NEVER SEEN, so this was checked the same way the equation environments were:
put one between two ordinary floats and see whether the ordinary one after it
still gets 3. Nothing was wrong -- `float_units` counts `\caption` CALLS
rather than `\begin{figure}`, so the environment's name never mattered.

The test exists because that is a property worth keeping, not because it was
broken. A counter rewritten to key on the environment would pass every
existing test and fail this one.

Both halves are covered: the raw source, which is what a skipped or late
normalising pass would leave, and the normalised source the pipeline intends.
"""
from __future__ import unicode_literals

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab
import merge_and_build as mb


def float_block(env, label, arg=''):
    return ('\\begin{%s}%s\n\\includegraphics{x}\n'
            '\\caption{Caption for %s.}\n\\label{%s}\n\\end{%s}\n'
            % (env, arg, label, label, env))


TEX = (float_block('figure', 'fig:one')
       + float_block('sidewaysfigure', 'fig:two')
       + float_block('figure', 'fig:three')
       + float_block('table', 'tab:one')
       + float_block('floatingtable', 'tab:two', '{0.4\\textwidth}')
       + float_block('table', 'tab:three'))

WANT = {'fig:one': ('figure', 1), 'fig:two': ('figure', 2),
        'fig:three': ('figure', 3), 'tab:one': ('table', 1),
        'tab:two': ('table', 2), 'tab:three': ('table', 3)}

_LABEL_RE = re.compile(r'\\label\s*\{([^{}]*)\}')


def numbering(tex):
    """{label: (kind, number)} as `float_units` sees it."""
    out = {}
    for unit in mb.float_units(tex):
        if unit['number'] is None:
            continue
        m = _LABEL_RE.search(tex[unit['start']:unit['stop']])
        if m:
            out[m.group(1)] = (unit['kind'], unit['number'])
    return out


class TheOrdinaryFloatAfterAnUnusualOneKeepsItsNumber(unittest.TestCase):

    def test_on_the_raw_source(self):
        self.assertEqual(numbering(TEX), WANT)

    def test_after_the_aliases_are_normalised(self):
        normalised, n = ab.normalize_float_envs(TEX)
        self.assertEqual(n, 2, 'both aliases should be rewritten')
        self.assertEqual(numbering(normalised), WANT)

    def test_the_unusual_float_is_not_silently_dropped(self):
        """The failure that would hurt: counted as nothing, so the float
        after it inherits its number."""
        got = numbering(TEX)
        self.assertIn('fig:two', got)
        self.assertIn('tab:two', got)
        self.assertNotEqual(got.get('fig:three'), ('figure', 2))
        self.assertNotEqual(got.get('tab:three'), ('table', 2))


class TheAliasTableCoversWhatLatexCounts(unittest.TestCase):
    """Each of these is a float LaTeX numbers with the ordinary counter."""

    def test_the_known_aliases_map_to_a_real_float(self):
        for alias in ('SCfigure', 'wrapfigure', 'sidewaysfigure',
                      'floatingfigure'):
            self.assertEqual(ab._FLOAT_ALIASES.get(alias), 'figure', alias)
        for alias in ('SCtable', 'wraptable', 'sidewaystable',
                      'floatingtable'):
            self.assertEqual(ab._FLOAT_ALIASES.get(alias), 'table', alias)


if __name__ == '__main__':
    unittest.main()
