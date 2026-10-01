# -*- coding: utf-8 -*-
r"""The seam between two chunks must not restyle the line it lands on.

VLA-Adapter's chunk boundary fell inside a Python listing. `chunk0012.md`
begins `            # RoPE`, twelve spaces of indentation putting it inside
the code block that `chunk0011.md` was still in the middle of. The
translator handled it correctly and `output_chunk0012.md` kept every space.

The merge then called `.strip()` on each chunk before joining, which removes
leading whitespace as readily as leading blank lines. The line arrived in
`output.md` at column zero, where `#` means a top-level heading. The book
shipped an H1 reading "RoPE", with its own table-of-contents entry, planted
between two halves of one class definition.

Nothing that reads a single chunk could see this: both the source and the
translation were correct. It exists only at the join, so that is where the
test has to look.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


class TrimmingAChunk(unittest.TestCase):

    def test_the_shipped_line_keeps_its_indentation(self):
        got = mb.trim_chunk_edges('            # RoPE\n            x = 1\n')
        self.assertTrue(got.startswith('            # RoPE'))
        self.assertFalse(got.lstrip('\n').startswith('#'))

    def test_leading_blank_lines_still_go(self):
        self.assertEqual(mb.trim_chunk_edges('\n\n\nHello'), 'Hello')

    def test_blank_lines_that_carry_spaces_go_too(self):
        """A 'blank' line out of a translator often has spaces on it."""
        self.assertEqual(mb.trim_chunk_edges('   \n\t\n    text'),
                         '    text')

    def test_trailing_whitespace_goes(self):
        self.assertEqual(mb.trim_chunk_edges('text\n\n   \n'), 'text')

    def test_crlf_blank_lines(self):
        self.assertEqual(mb.trim_chunk_edges('\r\n\r\n    x'), '    x')

    def test_an_all_whitespace_chunk_still_reads_as_empty(self):
        """The merge tests `if not content` right after this call to refuse a
        blank chunk. That has to keep working."""
        for blank in ('', '   ', '\n\n', '  \n \t \n  '):
            self.assertEqual(mb.trim_chunk_edges(blank), '')

    def test_ordinary_prose_is_untouched(self):
        text = '본 연구는 새로운 방법을 제안한다.'
        self.assertEqual(mb.trim_chunk_edges(text), text)

    def test_a_real_heading_at_column_zero_survives(self):
        self.assertEqual(mb.trim_chunk_edges('\n# 서론\n'), '# 서론')

    def test_indentation_inside_the_chunk_was_never_at_risk(self):
        body = 'def f():\n    return 1\n'
        self.assertEqual(mb.trim_chunk_edges(body), 'def f():\n    return 1')

    def test_a_tab_indent_is_kept(self):
        self.assertEqual(mb.trim_chunk_edges('\n\t# comment'), '\t# comment')

    def test_a_list_item_keeps_its_nesting(self):
        """The same seam under a different hat: a nested bullet unindented
        becomes a top-level one and the list silently reshapes."""
        self.assertEqual(mb.trim_chunk_edges('\n  - nested'), '  - nested')


class TheJoinedDocument(unittest.TestCase):
    """What the two chunks look like once merged, which is the artefact the
    heading was found in."""

    def test_the_listing_stays_one_code_block(self):
        first = '        k_task = reshape_heads(v_task)'
        second = '            # RoPE\n            cos_main = self.rope()'
        merged = (mb.trim_chunk_edges(first) + '\n\n'
                  + mb.trim_chunk_edges(second))
        headings = [l for l in merged.splitlines()
                    if l.startswith('#')]
        self.assertEqual(headings, [])
        for line in merged.splitlines():
            if line.strip():
                self.assertTrue(line.startswith('    '), line)


if __name__ == '__main__':
    unittest.main()
