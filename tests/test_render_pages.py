# -*- coding: utf-8 -*-
"""render_pages.py is the page render step 7.5 runs, as the skill's own command.

On an unattended plugin run the reviewing agent wrote a render script of its
own, which the skill does not pre-approve, and it was refused: no page was
read. The step now names this script, and these tests hold both ends.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import render_pages  # noqa: E402


class RenderPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        doc = render_pages.pymupdf.open()
        for n in range(3):
            doc.new_page(width=200, height=200).insert_text((20, 40), 'page %d' % (n + 1))
        self.pdf = os.path.join(self.tmp, 'book.pdf')
        doc.save(self.pdf)

    def test_every_page_by_default(self):
        out = render_pages.render(self.pdf, os.path.join(self.tmp, 'pages'), 'x_ko')
        self.assertEqual([os.path.basename(p) for p in out],
                         ['x_ko_p001.png', 'x_ko_p002.png', 'x_ko_p003.png'])
        for p in out:
            with open(p, 'rb') as f:
                self.assertEqual(f.read(8), b'\x89PNG\r\n\x1a\n')

    def test_a_page_list(self):
        self.assertEqual(render_pages.page_numbers('1,3', 3), [1, 3])
        self.assertEqual(render_pages.page_numbers('2-3', 3), [2, 3])
        with self.assertRaises(SystemExit):
            render_pages.page_numbers('4', 3)


class TheAuditStepsUseIt(unittest.TestCase):
    def test_both_reading_steps_run_the_shipped_script(self):
        with open(os.path.join(ROOT, 'SKILL.md'), encoding='utf-8') as f:
            skill = f.read()
        for step in ('#### 7.5b.', 'Tell it to **render both pages'):
            at = skill.index(step)
            # `{baseDir}` here, `${CLAUDE_PLUGIN_ROOT}` in the plugin's copy.
            self.assertRegex(skill[at:at + 900],
                             r'python (?:\{baseDir\}|\$\{CLAUDE_PLUGIN_ROOT\})'
                             r'/scripts/render_pages\.py', step)
        self.assertNotRegex(skill, r'get_pixmap\(')


if __name__ == '__main__':
    unittest.main()
