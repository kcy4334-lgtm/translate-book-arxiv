# -*- coding: utf-8 -*-
r"""A figure whose line ends with a spacing directive is still a figure.

CafeQ's figure 1 arrived as

    ![image](images/fig0001_ff_qerr_vs_dperf_p5.png) `{-2em}`{=latex}

and the image pattern required the line to end at the closing parenthesis.
So the figure was not recognised as a figure at all: no number, no printed
label, no anchor — while three cross-references in the text went on saying
"그림 1", pointing at a target that did not exist. Every probe passed. The
previous build of the same paper kept all three, because there the directive
happened to land on the next line instead.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb


KO = {'figure_label': '그림'}


class ImagePatternTests(unittest.TestCase):
    def test_a_plain_image_line_still_matches(self):
        line = '![image](images/fig0001_x.png)'
        self.assertTrue(mb._FIG_IMAGE_RE.match(line))

    def test_a_trailing_spacing_span_does_not_hide_the_figure(self):
        line = '![image](images/fig0001_x.png) `{-2em}`{=latex}'
        m = mb._FIG_IMAGE_RE.match(line)
        self.assertTrue(m, 'the figure was invisible to the formatter')
        self.assertEqual(m.group(2), 'images/fig0001_x.png')
        self.assertEqual(m.group(3), '0001')

    def test_a_trailing_attribute_block_still_matches(self):
        line = '![image](images/fig0002_x.png){width="60%"}'
        self.assertTrue(mb._FIG_IMAGE_RE.match(line))

    def test_a_raw_span_with_real_content_is_not_swallowed(self):
        # Only a brace-wrapped span is allowed to trail the image, so a raw
        # span carrying text cannot be absorbed and lost.
        line = '![image](images/fig0001_x.png) `\\textbf{caption}`{=latex}'
        self.assertIsNone(mb._FIG_IMAGE_RE.match(line))

    def test_prose_after_the_image_still_ends_the_match(self):
        line = '![image](images/fig0001_x.png) and then some prose'
        self.assertIsNone(mb._FIG_IMAGE_RE.match(line))


class SpacingPrefixTests(unittest.TestCase):
    """The other shape: the directive on its own line before the caption."""

    def test_a_raw_spacing_span_is_recognised(self):
        self.assertEqual(mb._spacing_only_prefix('`{-2em}`{=latex}\n\nCap'),
                         '`{-2em}`{=latex}')

    def test_a_bare_brace_directive_is_recognised(self):
        self.assertEqual(mb._spacing_only_prefix('{-2em}\n캡션'), '{-2em}')

    def test_a_caption_is_not_mistaken_for_spacing(self):
        self.assertEqual(mb._spacing_only_prefix('**그림.** 캡션 본문\n'), '')

    def test_an_anchor_is_not_mistaken_for_spacing(self):
        self.assertEqual(mb._spacing_only_prefix('{#fig:alpha}\n'), '')

    def test_a_vspace_command_is_recognised(self):
        self.assertEqual(mb._spacing_only_prefix('`{\\vspace{-1em}}`{=latex}\n'),
                         '')  # nested braces are not spacing-only here


class FormatFigureBlockTests(unittest.TestCase):
    def test_the_caption_survives_a_spacing_span_on_the_image_line(self):
        md = ('앞 문장이다.\n\n'
              '![image](images/fig0001_x.png) `{-2em}`{=latex}\n\n\n'
              '피드포워드 가중치의 양자화 오차에 따른 성능.\n\n'
              '다음 문단.\n')
        out, count = mb.format_figure_blocks(md, KO, None)
        self.assertEqual(count, 1)
        self.assertIn('**그림 1 (Fig. 1)**', out)
        self.assertIn('피드포워드 가중치의 양자화 오차에 따른 성능.', out)
        self.assertIn('다음 문단.', out)

    def test_the_spacing_directive_itself_is_not_printed(self):
        md = ('![image](images/fig0001_x.png) `{-2em}`{=latex}\n\n\n'
              '**캡션.** 본문.\n')
        out, _count = mb.format_figure_blocks(md, KO, None)
        self.assertNotIn('-2em', out)

    def test_an_uncaptioned_figure_does_not_eat_the_next_section(self):
        md = ('![image](images/fig0001_x.png) `{-2em}`{=latex}\n\n\n\n\n\n'
              '# 다음 절\n\n본문.\n')
        out, _count = mb.format_figure_blocks(md, KO, None)
        self.assertIn('# 다음 절', out)


if __name__ == '__main__':
    unittest.main()
