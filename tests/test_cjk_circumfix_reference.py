# -*- coding: utf-8 -*-
r"""A Chinese section reference is written around the number, not before it.

`ref_formats` for zh is `第{number}{label}` with `section_label` 节, so the
book prints `第3.2节`. A translator writes the same words around the
placeholder -- `第 (sec:adaptive_infer) 节` -- and both halves doubled:

    第 第3.2节 节在任意指定的平均计算开销...

Neither existing rule could reach it. The opening 第 is not a label word, so
`_xref_regex` never absorbed it. The closing 节 was left to
`drop_doubled_labels`, whose suffix rule ends in `(?!\w)`: in Chinese the next
character is another ideograph, which IS a word character, so that rule could
not fire at all.

Cleaning up after the substitution would mean guessing, because 节 also opens
节点. Before it, the placeholder's own `)` bounds the word and there is
nothing to guess -- so the reference pattern takes the closing word, and the
substitution puts it back unless the reference it emits already ends in it.

The probe that should have caught this was reading the book as Korean; see
`TheProbeAsksTheBookWhatLanguageItIs` below.
"""
from __future__ import unicode_literals

import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

import consistency_probe as cp
import merge_and_build as mb

ZH_FORMATS = {'section': '第{number}{label}'}
ZH_WORDS = {'section': '节', 'figure': '图', 'table': '表',
            'equation': '式'}


class TemplateAffixes(unittest.TestCase):

    def test_the_circumfix_is_read_off_the_template(self):
        lead, trail = mb.template_affixes(ZH_FORMATS, ZH_WORDS)
        self.assertEqual(lead, ['第'])
        self.assertEqual(trail, ['节'])

    def test_a_bracket_is_not_a_word_a_translator_repeats(self):
        r"""The equation template is `{label} ({number})`. Its literal head is
        ` (`, and absorbing a bracket would eat the reference's own."""
        lead, trail = mb.template_affixes(
            {'equation': '{label} ({number})'}, {'equation': '式'})
        self.assertEqual(lead, [])
        self.assertEqual(trail, [])

    def test_no_formats_yields_nothing(self):
        self.assertEqual(mb.template_affixes({}, ZH_WORDS), ([], []))
        self.assertEqual(mb.template_affixes(None, None), ([], []))


class TheReferencePatternTakesTheClosingWord(unittest.TestCase):

    def pattern(self):
        lead, trail = mb.template_affixes(ZH_FORMATS, ZH_WORDS)
        return mb._xref_regex(list(ZH_WORDS.values()) + lead, trail)

    def test_both_halves_of_the_circumfix_are_consumed(self):
        m = self.pattern().search('随后, 第 (sec:adaptive_infer) 节在任意')
        self.assertIsNotNone(m)
        self.assertTrue(m.group(0).startswith('第'))
        self.assertEqual(m.group(1).lower(), 'sec')
        self.assertEqual(m.group(2), 'adaptive_infer')
        self.assertEqual(m.group(3), '节')

    def test_the_closing_word_is_optional(self):
        """`按照 (sec:x) 中的说明` has no duplicate to take."""
        m = self.pattern().search('按照 (sec:adaptive_infer) 中的说明')
        self.assertIsNotNone(m)
        self.assertIsNone(m.group(3))

    def test_a_word_merely_starting_with_the_label_is_left_alone(self):
        r"""节点 is `node`. The pattern may take a bare 节 after the
        placeholder, but must not take the 节 of 节点 and orphan its 点."""
        m = self.pattern().search('见 (sec:arch) 节点数量')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(3), '节')
        # Whatever it took, the rest of the word is still in the text.
        self.assertTrue('点数量' in '见 (sec:arch) 节点数量'[m.end():])

    def test_a_language_with_no_circumfix_is_unchanged(self):
        """Korean passes no trailing words, and keeps the two-group shape."""
        plain = mb._xref_regex(['그림', '표', '식', '절'])
        m = plain.search('그림 (fig:teaser)에서')
        self.assertIsNotNone(m)
        self.assertEqual(plain.groups, 2)


class TheProbeAsksTheBookWhatLanguageItIs(unittest.TestCase):
    r"""`--lang` defaulted to `ko` while the answer sat in the directory the
    command was already pointed at. `verify_chunk` was fixed for exactly this
    and left a note; this probe was not. Judging the Chinese book by the
    Hangul range reported three Chinese headings as untranslated and compared
    its renderings against a Korean doublet list."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='conprobe-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_config(self, lang):
        with io.open(os.path.join(self.dir, 'config.txt'), 'w',
                     encoding='utf-8') as fh:
            fh.write('# Translation Configuration\noutput_lang=%s\n' % lang)

    def test_the_config_decides_when_no_flag_is_given(self):
        self.write_config('zh')
        self.assertEqual(cp.resolve_lang(self.dir, None), 'zh')

    def test_an_explicit_flag_still_wins(self):
        self.write_config('zh')
        self.assertEqual(cp.resolve_lang(self.dir, 'ja'), 'ja')

    def test_korean_remains_the_fallback_when_nothing_says(self):
        self.assertEqual(cp.resolve_lang(self.dir, None), 'ko')

    def test_a_missing_directory_does_not_raise(self):
        self.assertEqual(
            cp.resolve_lang(os.path.join(self.dir, 'nope'), None), 'ko')


if __name__ == '__main__':
    unittest.main()
