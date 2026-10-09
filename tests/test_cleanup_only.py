# -*- coding: utf-8 -*-
"""Intermediates are removed at the end of a run, not during the build.

The review after the build reads and repairs the chunks. Cleaned up during
the build, they were gone before it began: an unattended run on 2026-10-09
found two defects on its pages and could fix them only in output.md, where
the next re-merge would overwrite them. The build step now leaves them, and
`--cleanup-only` removes them once the review is done.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'merge_and_build.py')


class CleanupOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_it(self):
        return subprocess.run([sys.executable, SCRIPT, '--temp-dir', self.tmp,
                               '--cleanup-only'], capture_output=True, text=True,
                              encoding='utf-8', errors='replace')

    def touch(self, *names):
        for name in names:
            with open(os.path.join(self.tmp, name), 'w', encoding='utf-8') as f:
                f.write('x')

    def test_it_removes_the_intermediates_and_keeps_the_book(self):
        self.touch('output.md', 'chunk0001.md', 'output_chunk0001.md',
                   'chunk0001.math.json', 'input.md', 'book.pdf')
        result = self.run_it()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sorted(os.listdir(self.tmp)),
                         ['book.pdf', 'chunk0001.math.json', 'output.md'])

    def test_it_refuses_a_folder_with_no_book(self):
        self.touch('chunk0001.md')
        self.assertNotEqual(self.run_it().returncode, 0)
        self.assertIn('chunk0001.md', os.listdir(self.tmp))


class TheRunBookCleansUpLast(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, 'SKILL.md'), encoding='utf-8') as f:
            self.skill = f.read()

    def test_the_build_command_does_not_clean_up(self):
        builds = re.findall(r'(?m)^python \{baseDir\}/scripts/merge_and_build\.py .*$',
                            self.skill)
        self.assertTrue(builds)
        for line in builds:
            self.assertNotRegex(line, r'--cleanup(?!-only)')

    def test_cleanup_comes_after_the_review(self):
        self.assertLess(self.skill.index('### 7.5.'),
                        self.skill.index('--cleanup-only'))


if __name__ == '__main__':
    unittest.main()
