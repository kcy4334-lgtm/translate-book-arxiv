# -*- coding: utf-8 -*-
r"""Three TOC rows printed with no page number, and no check said so.

A heading with inline maths is set by MathML from the Mathematical
Alphanumeric Symbols block. Maynard's `# Smooth choice of $y$` reaches the page
as U+1D466 MATHEMATICAL ITALIC SMALL Y; the same heading read back out of the
HTML is an ASCII `y` from `<mi>y</mi>`. They never compared equal, so
`y의 매끄러운 선택`, `큰 k에 대한 매끄러운 가중치의 선택` and
`작은 k에 대한 가중치의 선택` came back unresolved — printed in the contents
with a blank where the page number goes, and absent from the PDF outline.

Shortening the probe could not rescue it: every prefix begins with the one
character that differs. NFKC folds the block back to plain letters.

The build reported it as `Print TOC: 8/11 page number(s) resolved` — a line
that reads like a statistic rather than a defect, which is why it stood.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import chromium_pdf as cp  # noqa: E402

ITALIC_Y = '\U0001d466'          # 𝑦, what Chromium puts on the page
ITALIC_K = '\U0001d458'          # 𝑘
BOLD_A = '\U0001d400'            # 𝐀, the same trap in a different alphabet


class TheMathAlphabetFoldsToPlainLetters(unittest.TestCase):
    def test_italic_y(self):
        self.assertEqual(cp._fold_for_match(ITALIC_Y), 'y')

    def test_italic_k_inside_a_korean_heading(self):
        self.assertEqual(
            cp._fold_for_match('큰 %s에 대한 선택' % ITALIC_K),
            '큰 k에 대한 선택')

    def test_other_math_alphabets_fold_too(self):
        self.assertEqual(cp._fold_for_match(BOLD_A), 'A')

    def test_a_ligature_the_pdf_carries_folds(self):
        self.assertEqual(cp._fold_for_match('diﬀerent'), 'different')

    def test_plain_text_is_unchanged(self):
        for s in ('Selberg 체 조작', '감사의 글', 'Introduction'):
            self.assertEqual(cp._fold_for_match(s), s)

    def test_the_two_forms_of_the_failing_heading_now_agree(self):
        from_html = 'y의 매끄러운 선택'
        from_pdf = '%s의 매끄러운 선택' % ITALIC_Y
        self.assertNotEqual(from_html, from_pdf)
        self.assertEqual(cp._fold_for_match(from_html),
                         cp._fold_for_match(from_pdf))


class _FakePage(object):
    def __init__(self, hits):
        self._hits = hits

    def search_for(self, probe, quads=False):
        return [1] if probe in self._hits else []


class _FakeDoc(object):
    def __init__(self, pages):
        self._pages = pages
        self.page_count = len(pages)

    def __getitem__(self, i):
        return _FakePage(self._pages[i])


class TheLookupFindsAMathHeading(unittest.TestCase):
    def setUp(self):
        self.doc = _FakeDoc([[], [], []])
        self.index = {0: [], 1: ['%s의 매끄러운 선택' % ITALIC_Y], 2: []}

    def test_the_page_is_found(self):
        self.assertEqual(
            cp._find_text_page(self.doc, 'y의 매끄러운 선택', 0, self.index), 2)

    def test_a_plain_heading_still_resolves(self):
        index = {0: [], 1: ['Selberg 체 조작'], 2: []}
        self.assertEqual(
            cp._find_text_page(self.doc, 'Selberg 체 조작', 0, index), 2)

    def test_a_heading_that_is_absent_still_returns_none(self):
        # The fold must not turn a miss into a match; a wrong page number is
        # worse than a blank one.
        self.assertIsNone(
            cp._find_text_page(self.doc, '존재하지 않는 절', 0, self.index))

    def test_the_search_starts_from_the_cursor(self):
        index = {0: ['같은 제목'], 1: [], 2: ['같은 제목']}
        self.assertEqual(cp._find_text_page(self.doc, '같은 제목', 1, index), 3)


if __name__ == '__main__':
    unittest.main()
