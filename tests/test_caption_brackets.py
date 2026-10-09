# -*- coding: utf-8 -*-
r"""Square brackets in a figure caption print as brackets.

A caption is folded into the image's alt text, where a bare `]` would end
it, so its brackets were escaped as `\[ \]`. The HTML reader runs with
tex_math_single_backslash, though, and reads `\[...\]` as display math:
ResNet's caption citation `[41]` printed as a lone centred "41" between two
halves of the caption, and ViT's bracketed translator's note in a caption
reached the page as raw TeX. Inside `$...$` a bracket belongs to the formula
and `\[` would break it.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb  # noqa: E402
import numbering  # noqa: E402


class CaptionBrackets(unittest.TestCase):

    def test_brackets_outside_math_become_entities(self):
        md = numbering._figure_caption_md(
            '그림 3', 'the VGG-19 model [41] on $[0, 1]$ inputs')
        self.assertIn('&#91;41&#93;', md)
        self.assertIn('$[0, 1]$', md)
        self.assertNotIn('\\[', md)

    @unittest.skipUnless(mb.resolve_pandoc(), 'needs pandoc')
    def test_pandoc_prints_them_as_brackets(self):
        alt = numbering._figure_caption_md('그림 3', 'the VGG-19 model [41] here')
        html = subprocess.run(
            [mb.resolve_pandoc(), '--from', mb.pandoc_from('ko'), '--to',
             'html5', '--mathml'],
            input='![%s](images/fig0003_arch.png)\n' % alt,
            capture_output=True, text=True, encoding='utf-8').stdout
        self.assertIn('[41]', html)
        self.assertNotIn('display="block"', html)

    @unittest.skipUnless(mb.resolve_pandoc(), 'needs pandoc')
    def test_a_footnote_reference_stays_a_footnote(self):
        # PaLM's Figure 7 printed `Lite.[^12]PaLM` with the note unlinked.
        alt = numbering._figure_caption_md('그림 7', 'BIG-bench Lite.[^12]PaLM [41]')
        self.assertIn('[^12]', alt)
        html = subprocess.run(
            [mb.resolve_pandoc(), '--from', mb.pandoc_from('ko'), '--to',
             'html5', '--mathml'],
            input='![%s](images/fig0007_lite.png)\n\n[^12]: The tasks.\n' % alt,
            capture_output=True, text=True, encoding='utf-8').stdout
        self.assertIn('footnote-ref', html)
        self.assertNotIn('[^12]', html)
        self.assertIn('[41]', html)


if __name__ == '__main__':
    unittest.main()
