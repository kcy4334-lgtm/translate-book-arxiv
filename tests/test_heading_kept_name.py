# -*- coding: utf-8 -*-
r"""A heading that is a name the glossary keeps in English is translated.

The chunk check calls a multi-word English heading untranslated, and lets a
single word through as a name (AlphaQ, SINQ). ViT's "Vision Transformer
(ViT)" is two words and a name: the glossary keeps it in English. The check
failed a correct chunk for it.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import consistency_probe as cp  # noqa: E402


class KeptNames(unittest.TestCase):

    def _dir(self, out_heading, kept=True):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with io.open(os.path.join(d, 'chunk0001.md'), 'w', encoding='utf-8') as fh:
            fh.write('## Vision Transformer (ViT)\n\nAn overview.\n')
        with io.open(os.path.join(d, 'output_chunk0001.md'), 'w', encoding='utf-8') as fh:
            fh.write('## %s\n\n개요이다.\n' % out_heading)
        terms = [{'source': 'Vision Transformer',
                  'target': 'Vision Transformer' if kept else '비전 트랜스포머'}]
        with io.open(os.path.join(d, 'glossary.json'), 'w', encoding='utf-8') as fh:
            json.dump({'terms': terms}, fh)
        return d

    def test_a_kept_name_is_not_an_untranslated_heading(self):
        problems = cp.check_chunks(self._dir('Vision Transformer (ViT)'), 'ko')
        self.assertFalse(any('not translated' in p for p in problems), problems)

    def test_a_term_the_glossary_translates_is_still_caught(self):
        problems = cp.check_chunks(
            self._dir('Vision Transformer (ViT)', kept=False), 'ko')
        self.assertTrue(any('not translated' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main()
