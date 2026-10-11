# -*- coding: utf-8 -*-
r"""An EPS figure from arXiv is converted with Ghostscript sandboxed.

An EPS file is a PostScript program. The plugin directory's scan flagged
arxiv_backend.py for running what it downloads; the one place that is true
is epstopdf handing an arXiv EPS to Ghostscript. It now asks for `--safer`
and `--restricted` by name, and the second refuses an absolute output path,
so the output is named relative to the folder epstopdf runs in.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

EPS = ('%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 100 50\n'
       'newpath 10 10 moveto 90 40 lineto stroke\nshowpage\n')
# Writes a file next to itself when Ghostscript is not sandboxed.
EVIL = ('%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n'
        '({target}) (w) file closefile showpage\n')


class EpsCommandTest(unittest.TestCase):
    def test_sandbox_flags_and_relative_output(self):
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        calls = []

        def fake_run(cmd, **kw):
            calls.append((cmd, kw))
            open(os.path.join(kw['cwd'], 'fig_1_b.pdf'), 'wb').close()
            return mock.Mock(returncode=0)

        with mock.patch.object(ab.shutil, 'which', return_value='epstopdf'), \
                mock.patch.object(ab.subprocess, 'run', side_effect=fake_run):
            out = ab._eps_to_pdf(os.path.join('figs', 'fig 1.b.eps'), work)
        cmd, kw = calls[0]
        self.assertEqual(cmd[1:4], ['--safer', '--restricted', '--outfile=fig_1_b.pdf'])
        self.assertTrue(os.path.isabs(cmd[4]))
        self.assertEqual(kw['cwd'], work)
        self.assertEqual(out, os.path.join(work, 'fig_1_b.pdf'))

    def test_no_epstopdf(self):
        with mock.patch.object(ab.shutil, 'which', return_value=None):
            self.assertIsNone(ab._eps_to_pdf('a.eps', tempfile.gettempdir()))


@unittest.skipUnless(shutil.which('epstopdf'), 'epstopdf not installed')
class EpsRealTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.work = os.path.join(self.root, 'work')
        os.mkdir(self.work)

    def test_plain_eps_converts(self):
        src = os.path.join(self.root, 'a.eps')
        with open(src, 'w') as f:
            f.write(EPS)
        out = ab._eps_to_pdf(src, self.work)
        self.assertTrue(out and os.path.getsize(out) > 0)

    def test_eps_cannot_write_files(self):
        target = os.path.join(self.root, 'written.txt').replace('\\', '/')
        src = os.path.join(self.root, 'evil.eps')
        with open(src, 'w') as f:
            f.write(EVIL.format(target=target))
        ab._eps_to_pdf(src, self.work)
        self.assertFalse(os.path.exists(target))


if __name__ == '__main__':
    unittest.main()
