# -*- coding: utf-8 -*-
r"""Tests for two conversion faults a fourth paper found.

A chunk with nothing in it dispatches a sub-agent to translate a blank file
and then fails the merge with the blank it gets back. DeeR-VLA produced one:
splitting an oversized block on blank lines yields empty pieces whenever the
block starts or ends on one, and a piece made only of those is a chunk of
nothing.

And the figure resolver skipped any reference starting `images/`, meaning
"already ours". DeeR-VLA keeps its own figures in a folder of that name, so
all seven were taken for finished work: nothing was extracted, the refs kept
pointing at files that exist only inside `arxiv_src`, and the build stopped.
What marks a reference as ours is the `figNNNN_` name the resolver writes,
not the folder it happens to sit in.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend
import convert


class ForceSplit(unittest.TestCase):

    def test_no_piece_comes_back_empty(self):
        text = '\n\n' + ('word ' * 400) + '\n\n\n' + ('other ' * 400) + '\n\n'
        pieces = convert._force_split_block(text, 600)
        self.assertTrue(pieces)
        for piece in pieces:
            self.assertTrue(piece.strip(), 'an empty piece became a chunk')

    def test_the_content_is_all_still_there(self):
        text = '\n\nalpha beta\n\n\ngamma delta\n\n'
        joined = ' '.join(convert._force_split_block(text, 8))
        for word in ('alpha', 'beta', 'gamma', 'delta'):
            self.assertIn(word, joined)

    def test_a_block_of_only_blank_lines_yields_nothing(self):
        for piece in convert._force_split_block('\n\n\n\n', 100):
            self.assertTrue(piece.strip())


class ResolvedReference(unittest.TestCase):

    def test_our_own_name_is_recognised(self):
        self.assertTrue(
            arxiv_backend._RESOLVED_REF_RE.match('images/fig0003_plot_p2.png'))

    def test_the_papers_own_images_folder_is_not(self):
        for ref in ('images/train_and_infer.pdf', 'images/deer.png',
                    'images/MLLM_architecture_v2.pdf'):
            self.assertIsNone(arxiv_backend._RESOLVED_REF_RE.match(ref), ref)

    def test_another_folder_is_not_either(self):
        self.assertIsNone(
            arxiv_backend._RESOLVED_REF_RE.match('figures/ff_qerr.pdf'))


if __name__ == '__main__':
    unittest.main()
