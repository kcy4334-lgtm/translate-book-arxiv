# -*- coding: utf-8 -*-
r"""Tests for pandoc's raw-inline marker, `{=latex}` / `{=html}`.

Two shapes that look alike and must be treated oppositely.

An ORPHANED marker is markup with nothing left to mark: SINQ page 8 printed
`\end{equation}$$ {=latex}여기서 …` because the backticks that owned it had
already gone. That one has to be dropped.

A LIVE one is load-bearing. pandoc writes `` `<!-- -->`{=html} `` between
`$\times$` and `7B` so a closing `$` followed by a digit still reads as
maths. Strip the marker and the comment becomes an ordinary code span, which
pandoc escapes and prints: `Mixtral-8×<!-- -->7B`, twenty-one times over.

The trap is that the two are told apart by the character in front, and the
pass that removes empty spans runs on the slices BETWEEN code regions -- so a
slice can begin at `{=html}` with its backtick in the previous slice, and a
lookbehind there sees the start of a string. The orphan rule therefore has to
run on the whole text, before any slicing.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class RawInlineMarkers(unittest.TestCase):

    def clean(self, text):
        return mb.normalize_latex_leftovers(text)[0]

    def test_a_marker_with_nothing_in_front_is_dropped(self):
        self.assertEqual(self.clean('$$ {=latex}여기서'), '$$ 여기서')

    def test_a_marker_a_backtick_owns_is_kept(self):
        text = 'Mixtral-8$\\times$`<!-- -->`{=html}7B'
        self.assertEqual(self.clean(text), text)

    def test_kept_even_when_a_code_region_precedes_it(self):
        # The slicing that protects code regions must not cost the marker
        # its context.
        text = 'see `code` then A$\\times$`<!-- -->`{=html}7B'
        self.assertEqual(self.clean(text), text)

    def test_an_empty_span_carrying_a_marker_still_goes(self):
        self.assertEqual(self.clean('text ``{=latex} more'), 'text  more')

    def test_a_spacing_span_still_goes(self):
        self.assertEqual(self.clean('![i](a.png) `{-2em}`{=latex}'),
                         '![i](a.png)')

    def test_several_live_markers_survive_together(self):
        text = ('A$\\times$`<!-- -->`{=html}7B and '
                'B$\\times$`<!-- -->`{=html}2B')
        self.assertEqual(self.clean(text), text)
        self.assertEqual(self.clean(text).count('{=html}'), 2)


if __name__ == '__main__':
    unittest.main()
