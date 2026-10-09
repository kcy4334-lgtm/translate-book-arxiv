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
