# -*- coding: utf-8 -*-
r"""citeproc's year letters follow the `.bbl`'s, not citeproc's own sort.

ViT cites Axial-DeepLab twice, ECCV and arXiv, same authors, year and title.
BibTeX letters them a (ECCV) and b (arXiv); citeproc broke the tie the other
way, so the book's 2020a was the original's 2020b, and a citation inside a
table, rendered from the `.bbl`, disagreed with the text around it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab


def words(text):
    out = []
    for i, w in enumerate(text.split(' ')):
        if i:
            out.append({'t': 'Space'})
        out.append({'t': 'Str', 'c': w})
    return out


def cite(keys, text):
    return {'t': 'Cite', 'c': [[{'citationId': k} for k in keys], words(text)]}


def entry(key, text):
    return {'t': 'Div', 'c': [['ref-' + key, ['csl-entry'], []],
                              [{'t': 'Para', 'c': words(text)}]]}


def tree(*paras, refs=()):
    blocks = [{'t': 'Para', 'c': p} for p in paras]
    blocks.append({'t': 'Div', 'c': [['refs', [], []], list(refs)]})
    return {'blocks': blocks}


def text_of(node):
    return ab._inline_text(node)


LETTERS = ab.bbl_year_letters({
    'eccv': 'Wang et al. 2020a', 'arxiv': 'Wang et al. 2020b',
    'smith': 'Smith 2020a', 'smith2': 'Smith 2020b', 'ho': 'Ho et al. 2019'})


def wang_refs():
    """Fresh entries: the pass edits the tree in place."""
    return (entry('arxiv', 'Wang, Huiyu. 2020a. Same. arXiv.'),
            entry('eccv', 'Wang, Huiyu. 2020b. Same. ECCV.'))


class AlignYearLetters(unittest.TestCase):

    def test_labels_without_a_letter_are_not_read(self):
        self.assertNotIn('ho', LETTERS)
        self.assertEqual(LETTERS['eccv'], ('Wang et al.', '2020', 'a'))

    def test_entries_and_citations_take_the_bbl_letters(self):
        doc = tree([cite(['eccv'], '(Wang et al. 2020b)')],
                   [cite(['arxiv'], 'Wang et al. (2020a)')], refs=wang_refs())
        n = ab.align_year_letters(doc, LETTERS)
        self.assertEqual(text_of(doc['blocks'][0]), '(Wang et al. 2020a)')
        self.assertEqual(text_of(doc['blocks'][1]), 'Wang et al. (2020b)')
        refs = doc['blocks'][2]['c'][1]
        # Relabelled, and back in letter order.
        self.assertEqual([r['c'][0][0] for r in refs], ['ref-eccv', 'ref-arxiv'])
        self.assertIn('2020a. Same. ECCV.', text_of(refs[0]))
        self.assertIn('2020b. Same. arXiv.', text_of(refs[1]))
        self.assertEqual(n, 4)

    def test_another_author_with_the_same_year_is_left(self):
        # Smith's letters already agree; only Wang's are swapped.
        refs = wang_refs() + (entry('smith', 'Smith, A. 2020a. X.'),
                              entry('smith2', 'Smith, A. 2020b. Y.'))
        doc = tree([cite(['smith', 'eccv'], '(Smith 2020a; Wang et al. 2020b)')],
                   refs=refs)
        ab.align_year_letters(doc, LETTERS)
        self.assertEqual(text_of(doc['blocks'][0]),
                         '(Smith 2020a; Wang et al. 2020a)')

    def test_a_collapsed_pair_swaps_both(self):
        doc = tree([cite(['arxiv', 'eccv'], '(Wang et al. 2020a, 2020b)')],
                   refs=wang_refs())
        ab.align_year_letters(doc, LETTERS)
        self.assertEqual(text_of(doc['blocks'][0]), '(Wang et al. 2020b, 2020a)')

    def test_letters_that_already_agree_change_nothing(self):
        refs = (entry('eccv', 'Wang, Huiyu. 2020a. Same. ECCV.'),
                entry('arxiv', 'Wang, Huiyu. 2020b. Same. arXiv.'))
        doc = tree([cite(['eccv'], '(Wang et al. 2020a)')], refs=refs)
        self.assertEqual(ab.align_year_letters(doc, LETTERS), 0)

    def test_citeproc_without_letters_is_left(self):
        # citeproc may disambiguate by names instead; then there is no
        # permutation to apply.
        refs = (entry('eccv', 'Wang, Huiyu. 2020. Same. ECCV.'),
                entry('arxiv', 'Wang, Huiyu. 2020. Same. arXiv.'))
        doc = tree([cite(['eccv'], '(Wang, Zhu 2020)')], refs=refs)
        self.assertEqual(ab.align_year_letters(doc, LETTERS), 0)


if __name__ == '__main__':
    unittest.main()
