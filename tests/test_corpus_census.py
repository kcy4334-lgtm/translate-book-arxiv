# -*- coding: utf-8 -*-
r"""The census is what makes `old-man` grow instead of guess.

Its value is entirely in being right about two things: which shapes the corpus
has met, and which it has NOT. The second is the warning nobody else can give
— a pattern deciding on a shape no paper has ever contained was written by
someone who had not seen one — and it is worthless the moment the census
under-reports, because a shape it fails to count is announced as never seen.

That happened while this was being written. Every marker was spelled
`\\command\b`, and `\b` is not the boundary after a TeX control word: `_` is a
word character to `re`, so `\nolimits_{X}` — how the command is nearly always
written — did not match, and the digest called `nolimits` never seen while a
paper in the corpus used it. The repair had a second edge: `\\begin` and
`\\bibitem` carry `\b` as their own second and third characters, so replacing
every `\b` produced patterns that did not compile at all.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import corpus_census as cc


class Boundaries(unittest.TestCase):

    def shapes(self, tex):
        found = cc.survey(tex)
        return set(n for group in found.values() for n in group)

    def test_a_command_followed_by_a_subscript_is_counted(self):
        self.assertIn('nolimits', self.shapes(r'$\sum\nolimits_{X} f$'))

    def test_a_command_followed_by_a_brace_is_counted(self):
        self.assertIn('multirow', self.shapes(r'\multirow{2}{*}{x}'))

    def test_a_longer_command_is_not_matched_by_a_shorter_marker(self):
        """`\\citep` must not be counted as `\\cite`."""
        found = cc.survey(r'\citep{a}')
        bib = found.get('bibliography', {})
        self.assertIn('citep', bib)
        self.assertNotIn('cite', bib)

    def test_every_marker_compiles(self):
        for group, patterns in cc.MARKERS.items():
            for pattern, name in patterns:
                self.assertTrue(hasattr(pattern, 'findall'), '%s/%s' % (group,
                                                                        name))


class Comments(unittest.TestCase):

    def test_a_commented_command_is_not_counted_as_present(self):
        found = cc.survey('% \\begin{tikzpicture}\n')
        self.assertNotIn('tikzpicture', found.get('other', {}))

    def test_but_it_is_counted_as_disabled_in_place(self):
        found = cc.survey('% \\caption{Old}\n\\caption{Live}\n')
        self.assertIn('commented-caption', found.get('disabled in place', {}))

    def test_a_live_command_on_the_same_line_after_a_percent_is_not_counted(self):
        found = cc.survey('text % \\begin{longtable}\n')
        self.assertNotIn('longtable', found.get('table', {}))


class Identity(unittest.TestCase):

    def setUp(self):
        import shutil
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, text):
        with open(os.path.join(self.dir, name), 'w', encoding='utf-8') as fh:
            fh.write(text)

    def test_the_arxiv_id_names_the_paper(self):
        self.write('config.txt', 'arxiv_id=2411.02359v1\n')
        self.assertEqual(cc.paper_id(self.dir), '2411.02359')

    def test_both_spellings_of_one_id_are_one_paper(self):
        """The store held 24 rows for 21 papers because this did not hold.

        A caller passing `--arxiv-id 2509.22944` and detection returning
        `2509.22944v4` are the same paper. Two rows for it corrupt both
        halves of every fraction `digest` prints.
        """
        self.write('config.txt', 'arxiv_id=2509.22944v4\n')
        versioned = cc.paper_id(self.dir)
        self.write('config.txt', 'arxiv_id=2509.22944\n')
        self.assertEqual(versioned, cc.paper_id(self.dir))

    def test_the_old_style_id_normalises_too(self):
        self.write('config.txt', 'arxiv_id=quant-ph/9508027v2\n')
        self.assertEqual(cc.paper_id(self.dir), 'quant-ph/9508027')

    def test_a_name_that_is_not_an_arxiv_id_keeps_its_v(self):
        """`planck` and `adam` are in the store under names, not ids, and a
        name is never rewritten by a rule meant for arXiv's numbering."""
        for name in ('planck', 'adam', 'resnetv2', 'Paperv1'):
            self.assertEqual(cc.normalise_id(name), name)

    def test_without_one_the_folder_does(self):
        self.assertEqual(cc.paper_id(os.path.join(self.dir, 'Paper_temp')),
                         'Paper')

    def test_a_dry_run_folder_resolves_to_the_same_paper(self):
        self.assertEqual(cc.paper_id(os.path.join(self.dir,
                                                  'Paper_temp_dryrun')),
                         'Paper')

    def test_a_build_with_no_latex_records_nothing(self):
        """The calibre backend has no source to survey; that is not an error."""
        self.assertIsNone(cc.record(self.dir, quiet=True))


if __name__ == '__main__':
    unittest.main()
