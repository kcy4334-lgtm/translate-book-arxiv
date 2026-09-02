"""Regression tests for calibre bracket-span unwrapping.

The original implementation stripped only the `{.calibreN}` attribute half of a
pandoc bracketed span and left the `[`/`]` behind, which fragmented converted
output with stray brackets. It also carried an unanchored `[**text**]` rule that
silently destroyed legitimate links such as `[**bold**](https://example.com)`.

Every case below is anchored on that history: the calibre-specific forms must be
unwrapped, and every look-alike markdown construct must survive untouched.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from convert import (
    _mask_code,
    _unmask_code,
    _unwrap_calibre_spans,
    clean_calibre_markers,
)


def unwrap(text):
    """Full pipeline: mask code, unwrap, restore code."""
    masked, store = _mask_code(text)
    return _unmask_code(_unwrap_calibre_spans(masked), store)


class UnwrapCalibreSpansTests(unittest.TestCase):
    def test_unwraps_calibre_span(self):
        self.assertEqual(unwrap(r'[Hello]{.calibre12}'), 'Hello')

    def test_unwraps_internal_calibre_link(self):
        self.assertEqual(unwrap(r'[a](#calibre_link-3)'), 'a')

    def test_unwraps_nested_spans_to_fixpoint(self):
        self.assertEqual(unwrap(r'[[in]{.calibre1} out]{.calibre2}'), 'in out')

    def test_strips_heading_attribute_block(self):
        self.assertEqual(unwrap(r'## Title {#calibre_link-7 .calibre3}'), '## Title')

    def test_removes_empty_link_shell(self):
        self.assertEqual(unwrap(r'text []() more'), 'text  more')

    # --- constructs that must NOT be touched -----------------------------

    def test_preserves_bold_link(self):
        """The old `[\\*\\*text\\*\\*]` rule rewrote this to `**Bold**(https://x)`."""
        src = r'[**Bold**](https://x)'
        self.assertEqual(unwrap(src), src)

    def test_preserves_image(self):
        src = r'![alt](images/a.png)'
        self.assertEqual(unwrap(src), src)

    def test_preserves_reference_link(self):
        src = r'See [note][ref]'
        self.assertEqual(unwrap(src), src)

    def test_preserves_footnote_ref(self):
        src = r'foot[^1]'
        self.assertEqual(unwrap(src), src)

    def test_preserves_link_definition(self):
        src = r'[ref]: https://x'
        self.assertEqual(unwrap(src), src)

    def test_preserves_external_url_containing_calibre_fragment(self):
        src = r'[x](http://a.com/#calibre_link-1)'
        self.assertEqual(unwrap(src), src)

    def test_preserves_inline_code(self):
        src = r'`[code]{.calibre1}`'
        self.assertEqual(unwrap(src), src)

    def test_preserves_fenced_code(self):
        src = '```\n[code]{.calibre1}\n```'
        self.assertEqual(unwrap(src), src)

    def test_idempotent(self):
        once = unwrap(r'[Hello]{.calibre12} and [a](#calibre_link-3)')
        self.assertEqual(unwrap(once), once)


class ArxivStampTests(unittest.TestCase):
    """The arXiv page-1 margin stamp must go; real arXiv citations must stay."""

    def test_removes_stamp_but_keeps_following_body_text(self):
        # pdftohtml concatenates real body text after the stamp, so deleting the
        # whole line would silently delete a sentence.
        src = (r'arXiv:2606.04980v1 \[cs.LG\] 3 Jun 2026 '
               r'Mixture-of-Experts (MoE) (Fedus et al., 2022)')
        cleaned = clean_calibre_markers(src).strip()
        self.assertEqual(cleaned, 'Mixture-of-Experts (MoE) (Fedus et al., 2022)')

    def test_preserves_bibliography_arxiv_id(self):
        src = 'arXiv:1803.05457, 2018.'
        self.assertEqual(clean_calibre_markers(src).strip(), src)

    def test_preserves_arxiv_preprint_citation(self):
        src = 'arXiv preprint arXiv:2505.05799, 2025.'
        self.assertEqual(clean_calibre_markers(src).strip(), src)

    def test_handles_unescaped_bracket_form(self):
        src = 'arXiv:2509.22944v4 [cs.LG] 15 Jan 2026 Body starts here.'
        self.assertEqual(clean_calibre_markers(src).strip(), 'Body starts here.')


if __name__ == '__main__':
    unittest.main()
