# -*- coding: utf-8 -*-
r"""Korean is East Asian and still writes spaces between words.

`PANDOC_FROM` carried `east_asian_line_breaks` for every language. The
extension deletes the newline between two East Asian characters, which is
right for Chinese and Japanese -- a line wrapped there has no space to lose.
Pandoc classifies Hangul as East Asian too, so a Korean paragraph wrapped
across two lines came back with the words joined:

    가로지르고 있든\n손잡이를   ->   가로지르고 있든손잡이를

Measured against the installed pandoc, not assumed:

    with the extension    <p>가로지르고 있든손잡이를 ...</p>
    without it            <p>가로지르고 있든 손잡이를 ...</p>

No shipped book has shown it, because translator sub-agents happen to write
each paragraph on one long line. That is luck, not design: the merged
markdown is an ordinary text file, and the damage is silent -- every count
still agrees, and only a reader of the sentence notices.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

EXT = '+east_asian_line_breaks'


class LanguagesThatWriteNoSpaceKeepIt(unittest.TestCase):

    def test_chinese(self):
        self.assertIn(EXT, mb.pandoc_from('zh'))

    def test_chinese_with_a_region(self):
        self.assertIn(EXT, mb.pandoc_from('zh-CN'))

    def test_japanese(self):
        self.assertIn(EXT, mb.pandoc_from('ja'))


class LanguagesThatWriteSpacesDoNot(unittest.TestCase):

    def test_korean(self):
        self.assertNotIn(EXT, mb.pandoc_from('ko'))

    def test_korean_with_a_region(self):
        self.assertNotIn(EXT, mb.pandoc_from('ko-KR'))

    def test_english(self):
        self.assertNotIn(EXT, mb.pandoc_from('en'))

    def test_an_unknown_language_is_treated_as_spacing(self):
        """The safe default: dropping a space nobody wanted dropped is the
        visible defect, keeping one is not."""
        self.assertNotIn(EXT, mb.pandoc_from('xx'))

    def test_no_language_at_all(self):
        self.assertNotIn(EXT, mb.pandoc_from(None))
        self.assertNotIn(EXT, mb.pandoc_from(''))


class EverythingElseSurvives(unittest.TestCase):
    r"""Only that one extension moves. `tex_math_dollars` reading `$...$`,
    `raw_html` letting spliced tables through, and the disabled
    `markdown_in_html_blocks` are all load-bearing elsewhere."""

    def test_the_other_extensions_are_untouched(self):
        for lang in ('ko', 'zh', 'ja', 'en', None):
            got = mb.pandoc_from(lang)
            for ext in ('+tex_math_dollars', '+tex_math_single_backslash',
                        '+pipe_tables', '+grid_tables', '+raw_html',
                        '-markdown_in_html_blocks', '+smart'):
                self.assertIn(ext, got, '%s lost %s' % (lang, ext))

    def test_the_constant_itself_is_unchanged(self):
        """Other code and tests read PANDOC_FROM directly."""
        self.assertIn(EXT, mb.PANDOC_FROM)


if __name__ == '__main__':
    unittest.main()
