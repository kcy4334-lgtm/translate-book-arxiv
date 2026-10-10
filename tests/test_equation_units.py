# -*- coding: utf-8 -*-
r"""Every equation number the paper prints, from one walk.

planck letters groups of equations (69a to 69d) with `subequations` and
with A&A's `\beglet`, builds equations inside its own macros (`\twoonesig`,
`\be`..`\ee`), and its book printed (87) where the paper prints (69a).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend  # noqa: E402
import numbering  # noqa: E402

PRE = ('\\newcommand{\\be}{\\begin{equation}}\n\\newcommand{\\ee}{\\end{equation}}\n'
       '\\newcommand{\\two}[2]{\\begin{equation}\\begin{aligned}#1\\\\#2'
       '\\end{aligned}\\end{equation}}\n'
       '\\def\\beglet{\\addtocounter{equation}{1}%\n'
       '\\setcounter{parentequation}{\\value{equation}}}\n'
       '\\def\\endlet{\\setcounter{equation}{\\value{parentequation}}}\n'
       '\\begin{document}\n')


def printed(body):
    units, steps = numbering.equation_units(PRE + body + '\\end{document}')
    return [u['printed'] for u in units if u['numbered']], steps


class EquationUnits(unittest.TestCase):

    def test_plain_equations_and_rows(self):
        got, steps = printed('\\begin{equation}a\\end{equation}'
                             '\\begin{align}b\\\\c\\nonumber\\\\d\\end{align}')
        self.assertEqual((got, steps), (['1', '2', '3'], 3))

    def test_a_subequations_group_letters_what_it_holds(self):
        got, steps = printed('\\be x \\ee\\begin{subequations}\\label{g}'
                             '\\two{a}{b}\\two{c}{d}\\end{subequations}'
                             '\\be y \\ee')
        self.assertEqual((got, steps), (['1', '2a', '2b', '3'], 3))

    def test_beglet_letters_like_subequations(self):
        got, _steps = printed('\\beglet\\be a\\ee\\be b\\ee\\endlet\\be c\\ee')
        self.assertEqual(got, ['1a', '1b', '2'])

    def test_a_tag_prints_and_does_not_step(self):
        got, steps = printed('\\be a\\tag{*}\\ee\\be b\\ee')
        self.assertEqual((got, steps), (['*', '1'], 1))

    def test_a_definition_is_not_counted(self):
        got, _steps = printed('')
        self.assertEqual(got, [])

    def test_the_group_label_names_the_parent(self):
        units, _steps = numbering.equation_units(
            PRE + '\\begin{subequations}\\label{eq:group}\\be\\label{eq:a} a\\ee'
            '\\end{subequations}\\end{document}')
        labels = {l: u['printed'] for u in units for l in u['labels']}
        self.assertEqual(labels, {'eq:group': '1', 'eq:a': '1a'})


class SplitDisplayGroups(unittest.TestCase):

    def test_four_equations_in_one_display_become_four(self):
        text = ('are $$\\begin{equation}\na\n\\end{equation}\n'
                '\\begin{equation}\nb\n\\end{equation}$$ more')
        out, n = arxiv_backend.split_display_groups(text)
        self.assertEqual(n, 1)
        self.assertEqual(out, 'are $$\\begin{equation}\na\n\\end{equation}$$\n'
                              '$$\\begin{equation}\nb\n\\end{equation}$$ more')

    def test_one_display_is_left(self):
        text = 'x $$\\begin{align}a\\\\b\\end{align}$$ y'
        self.assertEqual(arxiv_backend.split_display_groups(text), (text, 0))


if __name__ == '__main__':
    unittest.main()
