# -*- coding: utf-8 -*-
r"""Which display a `\label` belongs to, and what number it takes.

Two faults, both found by running 2609.05354 rather than reading the code,
and both of the same shape: an environment the label index could not see,
so a label inside it kept whatever the PREVIOUS display had set.

  * `alignat`, `flalign` and `IEEEeqnarray` were missing from the counted
    environments. Eight of that paper's labels sit inside `alignat` blocks,
    and each silently named an earlier formula.
  * `subequations` was missing too, and a label on the WRAPPER therefore
    kept the SECTION's number. One reference pointed the reader at a
    section instead of a group of formulas.

The wrapper is the interesting one. LaTeX advances the parent counter once
for the whole group and letters the rows under it, so the wrapper's number
is the same number its first inner display takes. Naming it WITHOUT
consuming it makes both spell the same string and changes no arithmetic --
which is why no suppression flag is needed, and why a fix that incremented
at the wrapper would have been wrong.
"""
from __future__ import unicode_literals

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb  # noqa: E402


class TheCountedEnvironmentsCoverTheDisplays(unittest.TestCase):

    def test_every_numbered_display_is_counted(self):
        for env in ('equation', 'align', 'gather', 'multline', 'eqnarray',
                    'alignat', 'flalign', 'IEEEeqnarray'):
            self.assertIn(env, mb._NUMBERED_MATH_ENVS, env)
            self.assertIn(env, mb._COUNTED_STRUCTURAL_ENVS, env)

    def test_the_scanner_matches_the_longer_name_first(self):
        r"""`alignat` must not be read as `align` followed by stray text."""
        pattern = mb._label_token_re(mb._DEFAULT_THEOREM_ENVS)
        m = pattern.search('\\begin{alignat}')
        self.assertEqual(m.group(4), 'alignat')

    def test_subequations_is_seen_but_is_not_a_numbered_display(self):
        """It numbers nothing itself. What it holds does."""
        self.assertIn('subequations', mb._COUNTED_STRUCTURAL_ENVS)
        self.assertNotIn('subequations', mb._NUMBERED_MATH_ENVS)


class ALabelTakesItsOwnDisplaysNumber(unittest.TestCase):

    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.work, True)

    def numbers(self, body, cls='article'):
        path = os.path.join(self.work, 'flat.tex')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\\documentclass{%s}\n\\begin{document}\n%s\n'
                     '\\end{document}\n' % (cls, body))
        return mb.build_label_numbers(self.work)

    def test_a_label_inside_alignat(self):
        body = ('\\begin{equation}\\label{eq:one}a=b\\end{equation}\n'
                '\\begin{alignat}{2}\\label{eq:two}c &= d\\end{alignat}\n')
        got = self.numbers(body)
        self.assertEqual(got.get('eq:one'), '1')
        self.assertEqual(got.get('eq:two'), '2')

    def test_a_label_inside_flalign_and_ieeeeqnarray(self):
        body = ('\\begin{flalign}\\label{eq:one}a &= b\\end{flalign}\n'
                '\\begin{IEEEeqnarray}{rCl}\\label{eq:two}c &=& d'
                '\\end{IEEEeqnarray}\n')
        got = self.numbers(body)
        self.assertEqual(got.get('eq:one'), '1')
        self.assertEqual(got.get('eq:two'), '2')

    def test_a_label_on_a_subequations_wrapper(self):
        """It named the section before this. The reader was sent to prose."""
        body = ('\\section{First}\\label{sec:one}\n'
                '\\begin{subequations}\\label{eq:group}\n'
                '\\begin{align}a &= b\\end{align}\n'
                '\\end{subequations}\n')
        got = self.numbers(body)
        self.assertEqual(got.get('sec:one'), '1')
        self.assertEqual(got.get('eq:group'), '1')

    def test_the_wrapper_and_its_inner_display_share_one_number(self):
        r"""LaTeX advances the parent counter once for the group."""
        body = ('\\begin{subequations}\\label{eq:group}\n'
                '\\begin{align}\\label{eq:inner}a &= b\\end{align}\n'
                '\\end{subequations}\n')
        got = self.numbers(body)
        self.assertEqual(got.get('eq:group'), got.get('eq:inner'))

    def test_the_group_consumes_exactly_one_number(self):
        """The equation after a subequations block must not skip. A fix
        that incremented at the wrapper would have made it 3."""
        body = ('\\begin{subequations}\\label{eq:group}\n'
                '\\begin{align}a &= b\\end{align}\n'
                '\\end{subequations}\n'
                '\\begin{equation}\\label{eq:after}c=d\\end{equation}\n')
        got = self.numbers(body)
        self.assertEqual(got.get('eq:group'), '1')
        self.assertEqual(got.get('eq:after'), '2')

    def test_a_wrapper_label_carries_its_section_when_the_class_scopes_it(self):
        body = ('\\section{First}\n\\section{Second}\n'
                '\\begin{subequations}\\label{eq:group}\n'
                '\\begin{align}a &= b\\end{align}\n'
                '\\end{subequations}\n')
        self.assertEqual(self.numbers(body, 'amsart').get('eq:group'), '2.1')


if __name__ == '__main__':
    unittest.main()
