# -*- coding: utf-8 -*-
r"""The reference list carries the numbers the citations point at.

`build_bibitem_numbers` numbers the in-text citations 1..N from the inlined
`\bibitem` list, in that list's own order, and prints them as `[1]`. The list
itself was rendered as bare paragraphs with no labels at all, so every book
this pipeline has produced shipped citations reading `[1]` to `[9]` above
nine unlabelled paragraphs. Not one of them could be resolved by a reader.

It reached the ENGLISH pass-through edition as well, which is what proves it
was never a translation defect, and six reading passes over six editions
found it while no check did -- because nothing had ever compared the two
halves against each other.

`resolve_pandoc` is stubbed out here on purpose. The rendering path is the
same either way and the numbering is what is under test; a test that behaves
differently depending on whether pandoc happens to be installed is a test
that passes locally and fails on CI, which this suite has already paid for
once.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


def bibliography(*keys):
    entries = ''.join(
        '\\bibitem{%s}\nA. Author %s.\n\\newblock A title. 2020.\n\n' % (k, k)
        for k in keys)
    return ('Some prose citing [@a].\n\n'
            '\\begin{thebibliography}{1}\n\n' + entries
            + '\\end{thebibliography}\n')


class WithoutPandoc(unittest.TestCase):

    def setUp(self):
        self.real = mb.resolve_pandoc
        mb.resolve_pandoc = lambda: None
        self.addCleanup(setattr, mb, 'resolve_pandoc', self.real)

    def expand(self, text, label='References'):
        return mb.expand_thebibliography(text, label)


class EveryEntryIsNumbered(WithoutPandoc):

    def test_the_labels_run_from_one(self):
        out, count = self.expand(bibliography('a', 'b', 'c'))
        self.assertEqual(count, 3)
        for number in (1, 2, 3):
            self.assertIn('[%d] A. Author' % number, out)

    def test_the_numbers_are_the_ones_the_citations_use(self):
        r"""The two halves are numbered from the same list in the same order,
        so this asserts they agree rather than that each is plausible."""
        text = bibliography('Caruana', 'brain-stuff', 'dropout')
        numbers = mb.build_bibitem_numbers(text)
        out, _ = self.expand(text)
        for key, number in numbers.items():
            self.assertIn('[%d] A. Author %s' % (number, key), out)

    def test_the_natbib_labelled_form_is_numbered_too(self):
        r"""`\bibitem[Adleman 1994]{Adle}` is what natbib and plainnat write,
        and a reader that only accepted the bare form once found 0 keys in a
        file holding 75."""
        text = ('\\begin{thebibliography}{1}\n\n'
                '\\bibitem[Adleman 1994]{Adle}\nA. Adleman.\n\n'
                '\\bibitem[Knuth 1968]{Knut}\nD. Knuth.\n\n'
                '\\end{thebibliography}\n')
        out, count = self.expand(text)
        self.assertEqual(count, 2)
        self.assertIn('[1] A. Adleman', out)
        self.assertIn('[2] D. Knuth', out)

    def test_the_heading_still_comes_first(self):
        out, _ = self.expand(bibliography('a', 'b'), label='Références')
        self.assertLess(out.index('# Références'), out.index('[1]'))

    def test_the_prose_before_the_list_is_untouched(self):
        out, _ = self.expand(bibliography('a'))
        self.assertIn('Some prose citing [@a].', out)


class NothingToNumber(WithoutPandoc):

    def test_a_document_with_no_bibliography(self):
        out, count = self.expand('just prose\n')
        self.assertEqual((out, count), ('just prose\n', 0))

    def test_an_empty_environment(self):
        text = '\\begin{thebibliography}{1}\n\\end{thebibliography}\n'
        _out, count = self.expand(text)
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
