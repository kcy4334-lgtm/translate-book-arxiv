# -*- coding: utf-8 -*-
r"""A web page in the reference list reads as the paper prints it.

2609.11801 cites a blog post the way BibTeX's standard styles allow:

    howpublished = {\url{https://openai.com/index/learning-to-reason-with-llms/}},
    note = {Accessed: 2026-08-24}

The book printed "Https://openai.com/..." and stopped there. pandoc reads
`howpublished` as the publisher, which the style capitalises as the start of
a sentence, and pandoc's default style prints `note` for no entry type at all.
plainnat, the paper's style, prints both as written.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import arxiv_backend as ab

try:
    import pypandoc
except ImportError:          # CI runs the standard library only
    pypandoc = None

ENTRY = (
    '@misc{openai2024o1,\n'
    '  author = {OpenAI},\n'
    '  title = {Learning to Reason with LLMs},\n'
    '  year = {2024},\n'
    '  howpublished = {\\url{https://openai.com/index/x/}},\n'
    '  note = {Accessed: 2026-08-24}\n'
    '}\n')


class HowpublishedUrl(unittest.TestCase):
    def bib(self, text):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, 'refs.bib')
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
        return path

    def read(self, path):
        with open(path, encoding='utf-8') as fh:
            return fh.read()

    def test_the_address_becomes_a_url(self):
        path = self.bib(ENTRY)
        self.assertEqual(ab.howpublished_urls(path), 1)
        text = self.read(path)
        self.assertIn('  url = {https://openai.com/index/x/},\n', text)
        self.assertNotIn('howpublished', text)
        self.assertIn('note = {Accessed: 2026-08-24}', text)

    def test_an_entry_with_its_own_url_loses_only_the_copy(self):
        path = self.bib(ENTRY.replace('  year', '  url = {https://a.org/},\n  year'))
        self.assertEqual(ab.howpublished_urls(path), 1)
        text = self.read(path)
        self.assertIn('url = {https://a.org/}', text)
        self.assertNotIn('openai.com', text)
        self.assertIn('  year = {2024},\n  note = {Accessed', text)

    def test_a_howpublished_that_is_not_only_an_address_is_left(self):
        text = ENTRY.replace('{\\url{https://openai.com/index/x/}}',
                             '{NVIDIA Technical Blog}')
        path = self.bib(text)
        self.assertEqual(ab.howpublished_urls(path), 0)
        self.assertEqual(self.read(path), text)


@unittest.skipUnless(pypandoc and shutil.which('pandoc'),
                     'pandoc or pypandoc not installed')
class RenderedEntry(unittest.TestCase):
    def test_the_entry_prints_its_address_and_its_note(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        bib = os.path.join(folder, 'refs.bib')
        with open(bib, 'w', encoding='utf-8', newline='') as fh:
            fh.write(ENTRY)
        ab.howpublished_urls(bib)
        csl = ab._full_author_csl(pypandoc)
        self.assertIsNotNone(csl)
        self.addCleanup(os.remove, csl)
        doc = os.path.join(folder, 'd.md')
        with open(doc, 'w', encoding='utf-8') as fh:
            fh.write('---\nnocite: "@*"\n---\n')
        out = subprocess.run(
            [pypandoc.get_pandoc_path(), doc, '--citeproc', '--bibliography',
             bib, '--csl', csl, '-t', 'plain', '--wrap=none'],
            capture_output=True, text=True, encoding='utf-8').stdout
        self.assertIn('https://openai.com/index/x/', out)
        self.assertNotIn('Https', out)
        self.assertIn('Accessed: 2026-08-24', out)


if __name__ == '__main__':
    unittest.main()
