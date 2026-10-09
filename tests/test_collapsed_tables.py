# -*- coding: utf-8 -*-
"""The collapsed-table check reads the page, not its stylesheet.

A stylesheet comment naming `<table>` opened a match that ran on to the first
real table, and a comment naming `<th>` then read as a header cell holding
markup: 2609.11801 failed "1 table(s) collapsed" with every table correct.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import format_probe as fp  # noqa: E402

PAGE = ('<html><head><style>\n/* break-inside on <table> is ignored; making\n'
        'every <th> bold printed it heavier */\n</style></head><body>\n'
        '<p>one-hot over the vocabulary, x in R|V|, with Delta|V|-1 the '
        'simplex |</p>\n<table><thead><tr><th>Method</th><th>Score</th></tr></thead>'
        '<tbody><tr><td>A</td><td>1.0</td></tr></tbody></table>\n%s</body></html>')


class CollapsedTables(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def check(self, extra=''):
        with open(os.path.join(self.dir, 'book_doc.html'), 'w', encoding='utf-8') as f:
            f.write(PAGE % extra)
        return fp.check_collapsed_tables(self.dir)[0]

    def test_a_stylesheet_comment_is_not_a_table(self):
        self.assertEqual(self.check(), 0)

    def test_a_real_collapsed_table_is_still_found(self):
        self.assertEqual(self.check(
            '<table><tr><td>방법 | UNIFORM | RANDOM |</td></tr></table>'), 1)


if __name__ == '__main__':
    unittest.main()
