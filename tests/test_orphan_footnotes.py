# -*- coding: utf-8 -*-
r"""A note nothing references is dropped, and nothing counts it.

An IEEE paper puts its front matter in `\thanks`: submission dates, every
author's affiliation, the equal-contribution and corresponding-author notes,
the funding, the DOI. pandoc reads each as a footnote whose REFERENCE lives in
the title block — which the backend drops on purpose, since the title and
authors come from the metadata. The definitions are left with nothing pointing
at them, and pandoc drops an unreferenced note without a word in the output.

TinyVLA translated 1271 characters of front matter and printed none of it. No
check saw it: the note is absent from every stage at once (K83), so every
count agreed with every other (K57).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class Rescue(unittest.TestCase):

    def test_an_unreferenced_note_is_kept(self):
        md = '# 초록\n\n본문\n\n[^1]: 원고 접수일 2024년 9월 27일.\n'
        out, n = mb.rescue_orphan_footnotes(md)
        self.assertEqual(n, 1)
        self.assertIn('원고 접수일 2024년 9월 27일.', out)
        self.assertIn('::: titlenotes', out)

    def test_it_moves_ahead_of_the_first_heading(self):
        md = '# 초록\n\n본문\n\n[^1]: 소속 정보.\n'
        out, _n = mb.rescue_orphan_footnotes(md)
        self.assertLess(out.index('titlenotes'), out.index('# 초록'))

    def test_the_definition_no_longer_stands_as_a_note(self):
        md = '# 초록\n\n본문\n\n[^1]: 소속 정보.\n'
        out, _n = mb.rescue_orphan_footnotes(md)
        self.assertNotIn('[^1]:', out)

    def test_a_referenced_note_is_left_exactly_where_it_is(self):
        """It is a working footnote and must stay one."""
        md = '# 초록\n\n본문[^a]입니다.\n\n[^a]: 진짜 각주.\n'
        out, n = mb.rescue_orphan_footnotes(md)
        self.assertEqual(n, 0)
        self.assertEqual(out, md)

    def test_only_the_orphan_moves_when_both_kinds_are_present(self):
        md = ('# 초록\n\n본문[^a]입니다.\n\n'
              '[^a]: 진짜 각주.\n\n[^b]: 떠 있는 앞부속.\n')
        out, n = mb.rescue_orphan_footnotes(md)
        self.assertEqual(n, 1)
        self.assertIn('[^a]: 진짜 각주.', out)
        self.assertNotIn('[^b]:', out)
        self.assertIn('떠 있는 앞부속.', out)

    def test_order_is_preserved(self):
        md = '# 초록\n\n[^1]: 첫째.\n\n[^2]: 둘째.\n\n[^3]: 셋째.\n'
        out, n = mb.rescue_orphan_footnotes(md)
        self.assertEqual(n, 3)
        self.assertLess(out.index('첫째'), out.index('둘째'))
        self.assertLess(out.index('둘째'), out.index('셋째'))

    def test_an_indented_continuation_line_comes_along(self):
        md = '# 초록\n\n[^1]: 첫 줄.\n    이어지는 줄.\n\n다음 문단.\n'
        out, _n = mb.rescue_orphan_footnotes(md)
        self.assertIn('이어지는 줄.', out)
        self.assertNotIn('    이어지는', out)
        self.assertIn('다음 문단.', out)

    def test_the_paragraph_after_the_note_is_not_swallowed(self):
        md = '# 초록\n\n[^1]: 각주 본문.\n\n일반 문단입니다.\n'
        out, _n = mb.rescue_orphan_footnotes(md)
        body = out.split(':::')[-1]
        self.assertIn('일반 문단입니다.', body)

    def test_a_document_with_no_notes_is_untouched(self):
        md = '# 초록\n\n본문뿐입니다.\n'
        self.assertEqual(mb.rescue_orphan_footnotes(md), (md, 0))

    def test_with_no_heading_it_still_keeps_the_text(self):
        md = '본문뿐.\n\n[^1]: 떠 있는 note.\n'
        out, n = mb.rescue_orphan_footnotes(md)
        self.assertEqual(n, 1)
        self.assertIn('떠 있는 note.', out)


if __name__ == '__main__':
    unittest.main()
