# -*- coding: utf-8 -*-
r"""A citation inside a table, when the paper inlines its `.bbl`.

`build_citation_labels` reads the `\bibitem` list out of the text it is
given, but by the time the tables are expanded `resolve_bibliography` has
already rendered that list to plain entries. The map came back empty, and
Sentence-BERT's AFS table printed "SVR" where the paper has
"SVR (Misra et al., 2016)"; its captions lost the datasets they credit.
flat.tex still holds the list as the paper wrote it.

acl_natbib also wraps the whole label in braces,
`\bibitem[{Misra et~al.(2016)Misra, Ecker, and Walker}]{MisraEW16}`, which
put a stray `{` in front of every author.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb  # noqa: E402

BS = '\\'
FLAT = ('body' + '\n'
        + BS + 'begin{thebibliography}{2}' + '\n'
        + BS + 'bibitem[{Misra et~al.(2016)Misra, Ecker, and Walker}]{MisraEW16}'
        + '\n' + 'Amita Misra. 2016. Measuring the similarity.' + '\n'
        + BS + 'end{thebibliography}' + '\n')
TABLE = (BS + 'begin{table}' + '\n'
         + BS + 'begin{tabular}{lr}' + '\n'
         + 'SVR ' + BS + 'cite{MisraEW16} & 63.33 ' + BS + BS + '\n'
         + BS + 'end{tabular}' + '\n'
         + BS + 'caption{Results on the AFS corpus ' + BS + 'cite{MisraEW16}.}'
         + '\n' + BS + 'end{table}')


class InlinedListLabels(unittest.TestCase):

    def test_a_braced_label_reads_without_the_brace(self):
        labels = mb.build_citation_labels(FLAT)
        self.assertEqual(labels['MisraEW16'], 'Misra et al. 2016')

    def test_an_alphabetic_label_is_used_as_it_stands(self):
        """VAE's `.bbl` writes `\\bibitem[DHS10]{duchi2010adaptive}`."""
        labels = mb.build_citation_labels(BS + 'bibitem[DHS10]{duchi2010adaptive} x')
        self.assertEqual(labels, {'duchi2010adaptive': 'DHS10'})

    def test_an_algorithm_float_gets_its_citation_and_reference(self):
        """VAE's algorithm: "section~\\ref{...}", "Adagrad~\\cite{...}"."""
        import latex_tables
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(BS + 'section{Intro}' + BS + 'subsection{Est}' + BS
                     + 'label{subsec:est}\n' + BS + 'begin{thebibliography}{1}\n'
                     + BS + 'bibitem[DHS10]{duchi}\nD.\n' + BS
                     + 'end{thebibliography}\n')
        tex = ('estimators in section~' + BS + 'ref{subsec:est} or Adagrad~'
               + BS + 'cite{duchi}')
        out = latex_tables.resolve_float_links(tex, '', d)
        self.assertEqual(out, 'estimators in section~1.1 or Adagrad~[DHS10]')

    def test_an_alphabetic_reference_list_is_labelled_as_cited(self):
        """VAE's body cited [BJP12]; its list was numbered [1] to [17]."""
        md = (BS + 'begin{thebibliography}{2}\n' + BS + 'bibitem[BJP12]{blei}\n'
              'D. Blei.\n' + BS + 'bibitem[DHS10]{duchi}\nJ. Duchi.\n'
              + BS + 'end{thebibliography}\n')
        out, n = mb.expand_thebibliography(md, '참고문헌')
        self.assertEqual(n, 2)
        self.assertIn('[BJP12] D. Blei.', out)
        self.assertIn('[DHS10] J. Duchi.', out)

    def test_an_alpha_label_with_a_raised_plus_prints_plainly(self):
        """VAE's `\\bibitem[VLL$^+$10]` reached the page as TeX."""
        import arxiv_backend
        self.assertEqual(arxiv_backend._clean_bib_label('VLL$^+$10'), 'VLL+10')
        self.assertEqual(arxiv_backend._clean_bib_label('ABC$^{+}$12'), 'ABC+12')

    def test_an_author_year_list_keeps_its_numbers(self):
        md = (BS + 'begin{thebibliography}{1}\n' + BS
              + 'bibitem[{Misra et~al.(2016)}]{m}\nA. Misra.\n'
              + BS + 'end{thebibliography}\n')
        self.assertIn('[1] A. Misra.', mb.expand_thebibliography(md, 'R')[0])

    def test_a_citation_group_takes_the_papers_brackets(self):
        import arxiv_backend
        self.assertEqual(arxiv_backend.cite_group(['BJP12', 'DHS10']),
                         '[BJP12, DHS10]')
        self.assertEqual(arxiv_backend.cite_group(['Kingma et al. 2014']),
                         '(Kingma et al. 2014)')

    def test_the_table_finds_the_keys_in_flat_tex(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(FLAT)
        seen = []

        def run(cmd, **kwargs):
            for arg in cmd:
                if str(arg).endswith('.tex') and os.path.exists(arg):
                    with open(arg, encoding='utf-8') as fh:
                        seen.append(fh.read())
            return mock.Mock(returncode=0, stdout='<table><tr><td>A</td></tr></table>',
                             stderr='')

        # The reference list has already been rendered: no \bibitem is left.
        md = 'prose\n\n' + TABLE + '\n\n# References\n\nMisra, Amita. 2016.\n'
        with mock.patch.object(mb.subprocess, 'run', side_effect=run):
            mb.expand_raw_latex_tables(md, pandoc='pandoc', temp_dir=d)
        sent = '\n'.join(seen)
        self.assertIn('SVR (Misra et al. 2016)', sent)
        self.assertNotIn(BS + 'cite', sent)


if __name__ == '__main__':
    unittest.main()
