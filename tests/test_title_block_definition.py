# -*- coding: utf-8 -*-
r"""A redefinition of `\twocolumn` is not a use of it.

The ICCV template opens its title block with `\twocolumn[` and then, INSIDE
that block, redefines the command so the block renders in one column:

    \twocolumn[
    {%
    \renewcommand\twocolumn[1][]{#1}
    \maketitle
    ...

`strip_title_block` leaves the outer block alone, correctly, because it holds
the abstract. The walk then arrives at the second `\twocolumn[`, which is not
a title block at all: the `[1]` is the macro's argument count. Cutting it
mangles the definition.

What that costs is out of all proportion to the line. pandoc dies on the
whole document with exit 64, and `--backend auto` falls back to calibre
without a word -- the path that cannot recover an equation -- while printing
"Conversion completed successfully!". MoLe-VLA came out as 36 chunks with
zero math placeholders and looked fine.

The idiom is in the CVPR, ICCV and NeurIPS templates, so every paper that
redefines a command with an optional argument meets this.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

REAL = ('\\begin{document}\n'
        '\\twocolumn[\n'
        '{%\n'
        '\\renewcommand\\twocolumn[1][]{#1}\n'
        '\\maketitle\n'
        '\\section{Abstract}\n'
        'We present a thing.\n'
        '}\n'
        ']\n'
        '\\section{Introduction}\n')


class ADefinitionIsLeftAlone(unittest.TestCase):

    def test_the_iccv_shape_survives_intact(self):
        out, _n = ab.strip_title_block(REAL)
        self.assertIn('\\renewcommand\\twocolumn[1][]{#1}', out)

    def test_every_declaration_that_can_define_it(self):
        for word in ('newcommand', 'renewcommand', 'providecommand',
                     'DeclareRobustCommand'):
            line = '\\%s\\twocolumn[1][]{#1}\n' % word
            out, n = ab.strip_title_block('\\begin{document}\n' + line)
            self.assertEqual(n, 0, word)
            self.assertIn(line.strip(), out)

    def test_a_starred_declaration_too(self):
        line = '\\newcommand*\\twocolumn[1][]{#1}\n'
        out, n = ab.strip_title_block(line)
        self.assertEqual(n, 0)
        self.assertIn(line.strip(), out)


class ARealTitleBlockIsStillDropped(unittest.TestCase):
    r"""The pass exists because thirty-seven lines of template boilerplate --
    "It is OKAY to include author information" -- sat at the top of an
    exported book. Teaching it about definitions must not cost that."""

    def test_a_plain_title_block_goes(self):
        tex = ('\\twocolumn[\n\\icmltitle{A Paper}\n'
               '\\icmlauthor{Somebody}\n]\n\\section{Introduction}\n')
        out, n = ab.strip_title_block(tex)
        self.assertEqual(n, 1)
        self.assertNotIn('icmltitle', out)
        self.assertIn('\\section{Introduction}', out)

    def test_a_block_holding_the_abstract_is_still_kept(self):
        tex = ('\\twocolumn[\n\\icmltitle{A Paper}\n'
               '\\begin{abstract}\nWe present a thing.\n\\end{abstract}\n]\n')
        out, n = ab.strip_title_block(tex)
        self.assertEqual(n, 0)
        self.assertIn('We present a thing.', out)

    def test_the_word_alone_is_not_a_block(self):
        """`\\twocolumn` with no bracket after it starts nothing."""
        tex = '\\twocolumn\n\\section{Introduction}\n'
        self.assertEqual(ab.strip_title_block(tex), (tex, 0))


if __name__ == '__main__':
    unittest.main()
