# -*- coding: utf-8 -*-
r"""A CLI prints, and what it prints carries the book's text.

On a Windows console under a Korean locale stdout encodes as cp949. Ten
scripts here already reconfigured stdout to UTF-8; nine with a `__main__`
block did not, and six of those nine are commands SKILL.md tells the agent to
run and capture for every chunk. Measured before the fix:

    glossary.py print-terms-for-chunk    UnicodeEncodeError
    chunk_context.py                     UnicodeEncodeError

The whole translation step fails there, at the point where the agent asks for
the term table. It stayed hidden because the guard was being supplied from
outside: every invocation that worked had PYTHONIOENCODING set in its
environment, so the suite went green from one shell and red from another with
no code in between.

The first rule tried for finding them was "which sources contain non-ASCII",
and it was wrong. `chunk_context.py` contains none of its own and crashed
anyway, because what it prints comes from the file it reads. The rule that
needs no judgement is the one below: if it has a CLI, it prints.
"""
from __future__ import unicode_literals

import io
import os
import subprocess
import sys
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), 'scripts')
GUARD = "reconfigure(encoding='utf-8'"


def cli_scripts():
    out = []
    for name in sorted(os.listdir(SCRIPTS)):
        if not name.endswith('.py'):
            continue
        with io.open(os.path.join(SCRIPTS, name), encoding='utf-8') as fh:
            text = fh.read()
        if "__name__ == '__main__'" in text or '__name__ == "__main__"' in text:
            out.append((name, text))
    return out


class EveryCommandCanPrintTheBook(unittest.TestCase):

    def test_each_cli_script_reconfigures_stdout(self):
        missing = [n for n, text in cli_scripts() if GUARD not in text]
        self.assertEqual(missing, [],
                         'these print without a UTF-8 stdout guard: %s'
                         % ', '.join(missing))

    def test_there_are_scripts_to_check(self):
        """A rule that silently matches nothing is not a rule."""
        self.assertGreater(len(cli_scripts()), 10)


class ItActuallySurvivesTheConsole(unittest.TestCase):
    r"""The lint above checks for a line; this checks the behaviour it buys.

    `chunk_context.py` is the honest case: its own source is pure ASCII, so no
    amount of scanning the file would have found it. What it prints is the
    chunk, and the chunk is the book.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='console-')
        for n, body in ((1, '앞 청크의 마지막 문장이다.'),
                        (2, '이 청크가 번역 대상이다.'),
                        (3, '다음 청크의 첫 문장이다.')):
            path = os.path.join(self.dir, 'chunk%04d.md' % n)
            with io.open(path, 'w', encoding='utf-8') as fh:
                fh.write(body + '\n')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_chunk_context_survives_an_ascii_console(self):
        env = dict(os.environ, PYTHONIOENCODING='ascii')
        out = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, 'chunk_context.py'),
             self.dir, 'chunk0002.md'],
            capture_output=True, env=env)
        self.assertEqual(out.returncode, 0,
                         out.stderr.decode('utf-8', 'replace'))

    def test_the_same_call_still_carries_the_text_when_utf8_is_available(self):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        out = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, 'chunk_context.py'),
             self.dir, 'chunk0002.md'],
            capture_output=True, env=env)
        self.assertEqual(out.returncode, 0,
                         out.stderr.decode('utf-8', 'replace'))
        self.assertIn('청크', out.stdout.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main()
