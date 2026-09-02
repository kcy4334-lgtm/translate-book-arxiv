# -*- coding: utf-8 -*-
r"""`meta_evidence` rejected a quote over a character the pipeline itself made.

pandoc's latex reader smartens quotes and dashes. `arxiv_backend._WRITER` ends
in `-smart`, so the markdown writer does not turn them back: the chunk says
`Zhang’s` where `flat.tex` says `Zhang's`. A sub-agent that copies the author's
sentence faithfully therefore fails a check whose whole purpose is to catch
sentences that were NOT copied.

Measured across every meta in the corpus at the time of writing: 1055 quotes
matched exactly, 1 failed on typography alone, 0 were genuinely absent. The
check's only hit in its lifetime was a false one, and the doctrine's price for
it is re-translating the chunk in full.

So the fold exists — and these tests fix its width. It must cover exactly what
pandoc introduces (measured through the real writer spec: en dash, em dash, the
four curly quotes, and the non-breaking space from `~`), and it must NOT cover
the ellipsis, which pandoc leaves as `...`. Wider than that and the check stops
catching the reconstructions in R2.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import verify_chunk as vc  # noqa: E402


class TheFoldCoversWhatPandocIntroduces(unittest.TestCase):
    def test_curly_apostrophe_folds_to_straight(self):
        self.assertEqual(vc._fold_typography('Zhang’s work'),
                         "Zhang's work")

    def test_both_single_quotes_fold(self):
        self.assertEqual(vc._fold_typography('‘GPY’'), "'GPY'")

    def test_both_double_quotes_fold(self):
        self.assertEqual(vc._fold_typography('“GPY”'), '"GPY"')

    def test_en_dash_and_a_double_hyphen_land_on_the_same_string(self):
        self.assertEqual(vc._fold_typography('pages 12–18'),
                         vc._fold_typography('pages 12--18'))

    def test_em_dash_and_a_triple_hyphen_land_on_the_same_string(self):
        self.assertEqual(vc._fold_typography('a — b'),
                         vc._fold_typography('a --- b'))

    def test_non_breaking_space_becomes_a_space(self):
        self.assertEqual(vc._fold_typography('Theorem 1'), 'Theorem 1')

    def test_the_ellipsis_is_left_alone(self):
        # pandoc does not convert it, so folding it would widen the check
        # past the pipeline's own behaviour.
        self.assertEqual(vc._fold_typography('and so on…'),
                         'and so on…')

    def test_ordinary_text_is_untouched(self):
        self.assertEqual(vc._fold_typography('plain ascii text'),
                         'plain ascii text')


class _MetaCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write_meta(self, evidence):
        payload = {'schema_version': 1,
                   'new_entities': [{'source': 'x', 'target_proposal': 'y',
                                     'category': 'term',
                                     'evidence': evidence}]}
        path = os.path.join(self.dir, 'output_chunk0001.meta.json')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(payload, ensure_ascii=False))


class AFaithfulQuoteIsAccepted(_MetaCase):
    SOURCE = ('most of the ideas of Zhang’s work (and the refinements '
              'produced by the polymath project) should be able to be '
              'combined with this method')

    def test_the_authors_straight_apostrophe_passes(self):
        self.write_meta("most of the ideas of Zhang's work (and the "
                        "refinements produced by the polymath project)")
        self.assertEqual(
            vc.check_meta_evidence(self.dir, 'chunk0001.md', self.SOURCE), [])

    def test_the_chunks_curly_apostrophe_still_passes(self):
        self.write_meta('most of the ideas of Zhang’s work (and the '
                        'refinements produced by the polymath project)')
        self.assertEqual(
            vc.check_meta_evidence(self.dir, 'chunk0001.md', self.SOURCE), [])

    def test_hard_wrapping_is_still_forgiven(self):
        self.write_meta('most of the ideas of\n   Zhang’s work')
        self.assertEqual(
            vc.check_meta_evidence(self.dir, 'chunk0001.md', self.SOURCE), [])


class AReconstructedQuoteIsStillCaught(_MetaCase):
    SOURCE = ('The basic idea of the GPY method is, for a fixed admissible '
              'set, to consider the sum over the weights')

    def test_a_plausible_paraphrase_fails(self):
        self.write_meta('The central idea of the GPY method is to consider '
                        'a weighted sum over admissible sets')
        found = vc.check_meta_evidence(self.dir, 'chunk0001.md', self.SOURCE)
        self.assertEqual([f['check'] for f in found], ['meta_evidence'])

    def test_an_invented_sentence_fails(self):
        self.write_meta('This result was first proved by Hardy and Littlewood '
                        'in nineteen twenty three')
        found = vc.check_meta_evidence(self.dir, 'chunk0001.md', self.SOURCE)
        self.assertEqual(len(found), 1)

    def test_the_reported_evidence_is_what_the_agent_wrote(self):
        # Not the folded form — someone chasing the finding needs to be able
        # to grep the meta file for the string the message shows them.
        quote = 'A sentence with ’ in it that is not in the chunk at all'
        self.write_meta(quote)
        found = vc.check_meta_evidence(self.dir, 'chunk0001.md', self.SOURCE)
        self.assertEqual(found[0]['evidence'], quote)


if __name__ == '__main__':
    unittest.main()
