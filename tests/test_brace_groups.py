# -*- coding: utf-8 -*-
r"""A group closes where TeX closes it: an escaped brace is a character.

Three helpers counted `\{` and `\}` as group braces. A paired `\{...\}`
came out right by luck; `\left\{ ... \right.`, the usual way to open a
`cases`-like formula, opens nothing in TeX and opened a level here, so the
group ran on past its own end. The probes that read the same source count
the same way, or they would disagree with the build about where a cell or
a caption ends.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import arxiv_backend  # noqa: E402
import build_common  # noqa: E402
import format_probe  # noqa: E402
import table_probe  # noqa: E402

BS = chr(92)
TEXT = ('{f(x) = ' + BS + 'left' + BS + '{ x ' + BS + 'right. ' + BS + BS
        + '{b}} tail}')
INNER = TEXT[1:TEXT.index(' tail')]
END = TEXT.index(' tail')


class EscapedBraces(unittest.TestCase):

    def test_build_common_group(self):
        self.assertEqual(build_common._balanced_group(TEXT, 0), END)
        self.assertEqual(build_common._brace_group(TEXT, 0), (INNER[:-1], END))

    def test_arxiv_backend_argument(self):
        self.assertEqual(arxiv_backend._balanced_arg(TEXT, 0), INNER[:-1])

    def test_the_probes_agree(self):
        self.assertEqual(format_probe._balanced(TEXT, 0), END)
        self.assertEqual(table_probe._matching_brace(TEXT, 0), END - 1)

    def test_an_unclosed_group_is_still_reported(self):
        self.assertEqual(build_common._balanced_group('{a ' + BS + '}', 0), -1)
        self.assertIsNone(arxiv_backend._balanced_arg('{a', 0))


if __name__ == '__main__':
    unittest.main()
