# -*- coding: utf-8 -*-
r"""The reference list stays where the paper put it, with every author.

citeproc appends the list after the last block, so a paper whose
`\bibliography` comes before its appendix had its references printed after
it: 2609.11801, AlphaQ, VLA-Adapter, DDPM and 2609.11716 all did. And
pandoc's default style cut every reference with seven or more authors to
three names and "et al.", where the papers' own styles name them all. The
first half is tested on pandoc's tree without running pandoc; the second runs
it when pypandoc and pandoc are installed.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402

BS = '\\'


def para(word):
    return {'t': 'Para', 'c': [{'t': 'Str', 'c': word}]}


def refs():
    return {'t': 'Div', 'c': [['refs', ['references'], []], [para('Entry.')]]}


class TheAnchor(unittest.TestCase):
    def test_the_anchor_follows_the_command(self):
        tex, ok = ab._anchor_bibliography('a\n' + BS + 'bibliography{refs}\nb')
        self.assertTrue(ok)
        self.assertLess(tex.index(BS + 'bibliography'), tex.index(ab._BIB_ANCHOR))

    def test_a_commented_command_is_not_an_anchor(self):
        tex = '% ' + BS + 'bibliography{old}\n'
        self.assertEqual(ab._anchor_bibliography(tex), (tex, False))

    def test_the_list_moves_to_the_anchor(self):
        tree = {'blocks': [para('Body'), para(ab._BIB_ANCHOR), para('Appendix'),
                           refs()]}
        self.assertTrue(ab._move_refs_to_anchor(tree))
        kinds = [b['t'] for b in tree['blocks']]
        self.assertEqual(kinds, ['Para', 'Div', 'Para'])
        self.assertEqual(tree['blocks'][2]['c'][0]['c'], 'Appendix')

    def test_nothing_moves_without_exactly_one_of_each(self):
        tree = {'blocks': [para('Body'), refs()]}
        self.assertFalse(ab._move_refs_to_anchor(tree))
        tree = {'blocks': [para(ab._BIB_ANCHOR), para(ab._BIB_ANCHOR), refs()]}
        self.assertFalse(ab._move_refs_to_anchor(tree))

    def test_the_anchor_never_reaches_the_page(self):
        tree = {'blocks': [para('Body'), para(ab._BIB_ANCHOR)]}
        ab._drop_anchor(tree)
        self.assertEqual(len(tree['blocks']), 1)


def _pandoc():
    try:
        import pypandoc
        pypandoc.get_pandoc_path()
        return True
    except Exception:
        return False


@unittest.skipUnless(_pandoc(), 'needs pypandoc and pandoc')
class ThroughPandoc(unittest.TestCase):
    BIB = ('@article{many, author={One, A and Two, B and Three, C and Four, D'
           ' and Five, E and Six, F and Seven, G and Eight, H}, title={Many},'
           ' journal={J}, year={2020}}\n')
    TEX = (BS + 'documentclass{article}\n' + BS + 'begin{document}\n'
           + BS + 'section{Intro}\nAs ' + BS + 'citet{many} show.\n'
           + BS + 'bibliographystyle{plainnat}\n' + BS + 'bibliography{refs}\n'
           + BS + 'appendix\n' + BS + 'section{Extra}\nMore.\n'
           + BS + 'end{document}\n')

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.bib = os.path.join(self.dir, 'refs.bib')
        with open(self.bib, 'w', encoding='utf-8') as f:
            f.write(self.BIB)

    def convert(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return ab.latex_to_markdown(self.TEX, self.dir, self.dir,
                                        bib_files=[self.bib])

    def test_references_come_before_the_appendix(self):
        md = self.convert()
        self.assertLess(md.index('H Eight'), md.index('Extra'))
        self.assertNotIn(ab._BIB_ANCHOR, md)

    def test_every_author_is_listed_and_the_citation_still_shortens(self):
        md = self.convert()
        self.assertIn('G Seven, and H Eight', md)
        self.assertRegex(md, r'One et al\.')
        self.assertNotIn('[@many]', md)


if __name__ == '__main__':
    unittest.main()
