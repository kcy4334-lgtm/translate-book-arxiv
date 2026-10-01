# -*- coding: utf-8 -*-
r"""A citation inside a table, when the paper ships a `.bib`.

`resolve_fragment_citations` already existed and was already called on every
table's body, caption and notes. It resolves from `build_citation_labels`,
which reads an INLINED `\bibitem[Authors Year]{key}` list. VLA-Adapter ships
a `.bib` and lets citeproc render it, so that map came back empty with 0
entries, the resolver had nothing to work with, and pandoc dropped all 51
`\citep` calls in its tables.

Nothing noticed. Every numeric value was present, every column and row count
was right, and the 22-baseline comparison simply lost the paper each number
came from. The mechanism was there; it was built from the one bibliography
shape this paper does not use.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

BIB = '''
@article{One-2024,
  author = {Hendrycks, Dan},
  year = {2024},
  title = {A single author},
}

@inproceedings{Two-2023,
  author = {Liu, Bo and Zhang, Wei},
  year = {2023},
  title = {Two authors},
}

@article{Many-2025,
  author = {Kim, Moo Jin and Pertsch, Karl and Karamcheti, Siddharth},
  year = {2025},
  title = {Three or more},
}

@misc{Plain-2022,
  author = {Ada Lovelace and Charles Babbage},
  year = {2022},
  title = {Names written first-last},
}

@misc{NoYear,
  author = {Nobody},
  title = {Missing the year},
}
'''


class LabelsFromABib(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        src = os.path.join(self.dir, 'arxiv_src')
        os.makedirs(src)
        with io.open(os.path.join(src, 'refs.bib'), 'w',
                     encoding='utf-8') as fh:
            fh.write(BIB)
        self.labels = mb.build_citation_labels_from_bib(self.dir)

    def test_one_author(self):
        self.assertEqual(self.labels['One-2024'], 'Hendrycks 2024')

    def test_two_authors_are_joined(self):
        self.assertEqual(self.labels['Two-2023'], 'Liu and Zhang 2023')

    def test_three_become_et_al(self):
        self.assertEqual(self.labels['Many-2025'], 'Kim et al. 2025')

    def test_first_last_names_are_read_too(self):
        self.assertEqual(self.labels['Plain-2022'],
                         'Lovelace and Babbage 2022')

    def test_an_entry_with_no_year_is_skipped(self):
        """A half-built label is worse than none: it would print a name with
        no date beside numbers that need dating."""
        self.assertNotIn('NoYear', self.labels)

    def test_no_tarball_gives_an_empty_map(self):
        self.assertEqual(mb.build_citation_labels_from_bib(None), {})
        self.assertEqual(
            mb.build_citation_labels_from_bib(tempfile.mkdtemp()), {})

    def test_the_labels_actually_resolve_a_fragment(self):
        tex = r'A & \citep{Many-2025} & 90.6 \\'
        out, n = mb.resolve_fragment_citations(tex, self.labels)
        self.assertEqual(n, 1)
        self.assertIn('Kim et al. 2025', out)
        self.assertNotIn(r'\citep', out)
        self.assertEqual(out.count('&'), tex.count('&'),
                         'the cell separators must not move')


if __name__ == '__main__':
    unittest.main()
