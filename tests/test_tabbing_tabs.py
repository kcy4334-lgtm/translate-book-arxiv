# -*- coding: utf-8 -*-
r"""Shor's algorithm listing printed `\right\rangle` where it means a tab stop.

Inside `tabbing`, LaTeX rebinds `\>`, `\=`, `\<`, `` \` `` and `\'` to tab
commands for the length of the environment. pandoc expands the document's own
macros without knowing that, and Shor wrote the two definitions that turn the
gap into damage:

    \newcommand{\tab}{\>}              % to keep tabbing usable ...
    \renewcommand{\>}{\right\rangle}   % ... despite ket notation

His own comment says why. All 29 `\tab`s in his three listings arrived as
`\right\rangle`, so the pseudocode — the centre of that paper — read
`\right\rangle for {\it i} = 0 to {\it l}`, and it shipped that way.

Only a tab command REDEFINED in the preamble can be damaged, so a paper that
redefines none must come through untouched: that is the guard, and the whole
corpus has exactly one paper that trips it.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402
import merge_and_build as mb  # noqa: E402

SHOR = (r'\newcommand{\tab}{\>}' '\n'
        r'\renewcommand{\>}{\right\rangle}' '\n'
        r'\newcommand{\mod}[1]{{\rm \ (mod\ }#1)}' '\n'
        r'\begin{document}' '\n'
        r'\begin{tabbing}' '\n'
        r'\ \ \= \ \ \= \kill' '\n'
        r'\tab {\it power} := 1 \\' '\n'
        r'\tab \tab {\it power} := {\it power} $*$ 2 $\mod{n}$ \\' '\n'
        r'\end{tabbing}' '\n'
        r'\end{document}' '\n')


class TabsStopBeingMaths(unittest.TestCase):
    def test_the_alias_becomes_indentation(self):
        got, n = ab.neutralize_tabbing_tabs(SHOR)
        self.assertEqual(n, 3)
        block = ab._TABBING_BLOCK_RE.search(got).group(0)
        self.assertNotIn(r'\tab', block)
        self.assertIn('    {\\it power} := 1', block)

    def test_the_definition_itself_is_left_alone(self):
        # Outside tabbing `\>` really is ket notation; only the environment
        # rebinds it.
        got, _ = ab.neutralize_tabbing_tabs(SHOR)
        self.assertIn(r'\newcommand{\tab}{\>}', got)
        self.assertIn(r'\renewcommand{\>}{\right\rangle}', got)

    def test_a_paper_that_redefines_nothing_is_untouched(self):
        plain = ('\\begin{document}\n\\begin{tabbing}\n'
                 'a \\= b \\\\\n\\> c \\\\\n\\end{tabbing}\n')
        self.assertEqual(ab.neutralize_tabbing_tabs(plain), (plain, 0))

    def test_text_outside_a_tabbing_block_is_untouched(self):
        tex = (r'\renewcommand{\>}{\right\rangle}' '\n'
               r'\begin{document}' '\n' r'$\|\psi\>$' '\n')
        self.assertEqual(ab.neutralize_tabbing_tabs(tex), (tex, 0))


class TheListingReadsAsPseudocode(unittest.TestCase):
    def build(self):
        fixed, _ = ab.neutralize_tabbing_tabs(SHOR)
        block = ab._TABBING_BLOCK_RE.search(fixed).group(0)
        macros = {'mod': r'{\rm \ (mod\ }#1)'}
        out, n = mb.unwrap_tabbing(block, macros)
        return out, n

    def test_a_fence_is_produced(self):
        out, n = self.build()
        self.assertEqual(n, 1)
        self.assertIn('```', out)

    def test_the_indentation_survives(self):
        out, _ = self.build()
        body = [ln for ln in out.split('\n') if ':=' in ln]
        self.assertEqual(len(body), 2)
        self.assertTrue(body[0].startswith('    power'))
        self.assertTrue(body[1].startswith('        power'))

    def test_no_blank_line_between_rows(self):
        # `\\` ends a row and the source breaks the line after it too, so
        # replacing only the `\\` double-spaced the whole listing.
        out, _ = self.build()
        inner = out.strip().split('```')[1]
        self.assertNotIn('\n\n', inner.strip())

    def test_the_maths_reads_as_text(self):
        out, _ = self.build()
        self.assertIn('power * 2', out)
        self.assertNotIn('$', out)

    def test_a_one_argument_macro_is_expanded(self):
        out, _ = self.build()
        self.assertIn('(mod n)', out)
        self.assertNotIn(r'\mod', out)

    def test_a_spacing_command_goes_even_before_a_letter(self):
        # `\,` is a control symbol: the next character is never part of its
        # name, and requiring one left `result_{\,i}` on the page.
        out, _ = mb.unwrap_tabbing(
            '\\begin{tabbing}\na$_{\\,i}$ \\\\\n\\end{tabbing}', {})
        self.assertIn('a_{i}', out)


class OneArgumentMacrosAreReadNarrowly(unittest.TestCase):
    def make(self, preamble):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(preamble + '\n\\begin{document}\n\\end{document}\n')
        return d

    def test_a_plain_one_argument_macro_is_read(self):
        d = self.make(r'\newcommand{\mod}[1]{{\rm \ (mod\ }#1)}')
        self.assertEqual(mb.read_one_argument_macros(d),
                         {'mod': r'{\rm \ (mod\ }#1)'})

    def test_a_conditional_body_is_refused(self):
        d = self.make(r'\newcommand{\GeV}[1]{\ifmmode #1 \else x\fi}')
        self.assertEqual(mb.read_one_argument_macros(d), {})

    def test_a_body_using_its_argument_twice_is_refused(self):
        d = self.make(r'\newcommand{\dbl}[1]{#1#1}')
        self.assertEqual(mb.read_one_argument_macros(d), {})

    def test_a_two_argument_macro_is_refused(self):
        d = self.make(r'\newcommand{\lr}[2]{{\{#1\}_{#2}}}')
        self.assertEqual(mb.read_one_argument_macros(d), {})

    def test_a_zero_argument_macro_is_not_here(self):
        d = self.make(r'\newcommand{\E}{\mathbb{E}}')
        self.assertEqual(mb.read_one_argument_macros(d), {})


if __name__ == '__main__':
    unittest.main()
