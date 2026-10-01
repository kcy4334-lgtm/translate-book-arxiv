# -*- coding: utf-8 -*-
r"""The alias rule deleted the definitions it exists to protect.

`read_math_macros` drops a macro whose body is a single command that is not
itself defined in the document. It was written for `\let\gev\GeV`, where the
target was a paper-local name nobody collected — following it swaps one
unreadable token for another.

`\def \< {\langle}` has exactly that shape and points at a command texmath
knows. Dropped, randmat printed 48 formulas as source over `\<` and `\>`. Nine
papers lose macros to this rule and 17 of the 22 distinct targets across the
corpus render.

Shape cannot tell the two cases apart; only the target can. So the question is
put to pandoc, once per command and cached — and when pandoc cannot be reached
every answer is False, which is exactly the conservative behaviour this
replaces. CI has no pandoc, so these tests drive the decision through a stub.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class TheReaderCacheAnswers(unittest.TestCase):
    def setUp(self):
        self.saved = dict(mb._TEXMATH_READS)
        mb._TEXMATH_READS.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        mb._TEXMATH_READS.clear()
        mb._TEXMATH_READS.update(self.saved)

    def test_a_cached_answer_is_used_without_asking(self):
        mb._TEXMATH_READS[r'\langle'] = True
        self.assertEqual(mb._texmath_reads([r'\langle']), {r'\langle': True})

    def test_a_cached_negative_is_used_too(self):
        mb._TEXMATH_READS[r'\ZZ'] = False
        self.assertEqual(mb._texmath_reads([r'\ZZ']), {r'\ZZ': False})

    def test_no_pandoc_means_no(self):
        # The fallback has to reproduce the old behaviour exactly, or a build
        # without pandoc starts keeping aliases it cannot check.
        saved = list(mb._PANDOC_PATH)
        mb._PANDOC_PATH[:] = [None]
        try:
            self.assertEqual(mb._texmath_reads([r'\qqq']), {r'\qqq': False})
        finally:
            mb._PANDOC_PATH[:] = saved

    def test_an_empty_batch_asks_nothing(self):
        self.assertEqual(mb._texmath_reads([]), {})


class TheDropFollowsTheAnswer(unittest.TestCase):
    def setUp(self):
        self.saved = dict(mb._TEXMATH_READS)
        self.addCleanup(self._restore)

    def _restore(self):
        mb._TEXMATH_READS.clear()
        mb._TEXMATH_READS.update(self.saved)

    def write(self, text):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'math_macros.tex'), 'w',
                  encoding='utf-8') as fh:
            fh.write(text)
        return d

    def test_an_alias_to_a_readable_command_is_kept(self):
        mb._TEXMATH_READS[r'\langle'] = True
        d = self.write(r'\def \< {\langle}' '\n')
        self.assertEqual(mb.read_math_macros(d), {'\\<': r'\langle'})

    def test_an_alias_to_an_unreadable_name_is_dropped(self):
        mb._TEXMATH_READS[r'\GeV'] = False
        d = self.write(r'\let\gev\GeV' '\n' r'\def\other{x}' '\n')
        self.assertNotIn(r'\gev', mb.read_math_macros(d))

    def test_an_alias_to_another_defined_macro_is_kept_without_asking(self):
        d = self.write(r'\def\aaa{\mathbb{Z}}' '\n' r'\def\bbb{\aaa}' '\n')
        macros = mb.read_math_macros(d)
        self.assertIn(r'\bbb', macros)

    def test_a_body_that_is_not_a_bare_command_is_never_dropped(self):
        d = self.write(r'\def\E{\mathbb{E}}' '\n')
        self.assertIn(r'\E', mb.read_math_macros(d))

    def test_a_macro_taking_an_argument_is_still_skipped(self):
        d = self.write(r'\newcommand{\norm}[1]{\|#1\|}' '\n')
        self.assertNotIn(r'\norm', mb.read_math_macros(d))


if __name__ == '__main__':
    unittest.main()
