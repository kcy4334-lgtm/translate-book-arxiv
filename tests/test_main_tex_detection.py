# -*- coding: utf-8 -*-
r"""Picking the top-level .tex, and the ways that used to go silently wrong.

Shor 1995 was rejected as having "no top-level .tex found" while holding a
complete 111 KB single-file document -- 47 equations, 75 references -- and the
run fell back to a backend that cannot recover equations at all. Three
separate defects, none of which raised anything:

  * the file declares itself with `\documentstyle`, the LaTeX 2.09 spelling
    replaced by `\documentclass` in 1994, and only the modern one was accepted;
  * the requirement was expressed as a SCORE >= 20 while the two mandatory
    flags were worth exactly 20, so any other adjustment could veto a real
    document -- and a top-level file already paid -1 for depth;
  * the error message named a condition the code never tested, blaming a
    missing `\begin{document}` that sat on line 58 of the file it rejected.
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import arxiv_backend as ab  # noqa: E402


def _tree(**files):
    root = tempfile.mkdtemp(prefix='tb-maintex-')
    for name, body in files.items():
        path = os.path.join(root, name.replace('__', os.sep))
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(body)
    return root


BODY = '\\begin{document}\n\\title{T}\\maketitle\nhi\n\\end{document}\n'


class DocumentDeclaration(unittest.TestCase):
    def test_latex_2e_documentclass(self):
        root = _tree(**{'main.tex': '\\documentclass{article}\n' + BODY})
        self.assertEqual(ab.find_main_tex(root),
                         os.path.join(root, 'main.tex'))

    def test_latex_209_documentstyle(self):
        # Exactly Shor 1995's line 1.
        root = _tree(**{'main.tex': '\\documentstyle[twoside]{article}\n'
                                    + BODY})
        self.assertEqual(ab.find_main_tex(root),
                         os.path.join(root, 'main.tex'))

    def test_declaration_need_not_start_the_line(self):
        root = _tree(**{'main.tex': '\\makeatletter\\documentclass{article}\n'
                                    + BODY})
        self.assertIsNotNone(ab.find_main_tex(root))

    def test_a_commented_out_declaration_does_not_count(self):
        root = _tree(**{'main.tex': '% \\documentclass{article}\n' + BODY})
        self.assertIsNone(ab.find_main_tex(root))

    def test_begin_document_may_carry_whitespace(self):
        root = _tree(**{'main.tex': '\\documentclass{article}\n'
                                    '\\begin {document}\nhi\n'
                                    '\\end{document}\n'})
        self.assertIsNotNone(ab.find_main_tex(root))

    def test_a_file_with_no_body_is_not_the_document(self):
        root = _tree(**{'preamble.tex': '\\documentclass{article}\n'})
        self.assertIsNone(ab.find_main_tex(root))


class ScoringOnlyRanksQualifiedFiles(unittest.TestCase):
    def test_a_qualified_file_is_not_vetoed_by_its_name_or_depth(self):
        # The old arithmetic: documentclass(10) + begin(10) - 1 depth = 19,
        # under a threshold of 20, so this real document was rejected for
        # being called something other than main/ms/paper/arxiv and keeping
        # its \title in an \input'd file.
        root = _tree(**{'shor.tex': '\\documentclass{article}\n'
                                    '\\begin{document}\nhi\n'
                                    '\\end{document}\n'})
        self.assertEqual(ab.find_main_tex(root),
                         os.path.join(root, 'shor.tex'))

    def test_the_shallower_of_two_documents_wins(self):
        root = _tree(**{'main.tex': '\\documentclass{article}\n' + BODY,
                        'sub__main.tex': '\\documentclass{article}\n' + BODY})
        self.assertEqual(ab.find_main_tex(root),
                         os.path.join(root, 'main.tex'))

    def test_a_conventional_name_wins_at_equal_depth(self):
        root = _tree(**{'zzz.tex': '\\documentclass{article}\n' + BODY,
                        'main.tex': '\\documentclass{article}\n' + BODY})
        self.assertEqual(ab.find_main_tex(root),
                         os.path.join(root, 'main.tex'))


class EnvironmentRedefinitionsAreDropped(unittest.TestCase):
    r"""`\def\thebibliography` collides with pandoc's own reader.

    Measured on Shor 1995: pandoc abandoned the file at the closing `\end`,
    2400 lines in, reporting only "unexpected \end". Removing that one
    definition converted the paper; removing the `\@biblabel` beside it changed
    nothing. Which names count is read from the document, not listed.
    """

    def test_a_def_of_a_used_environment_is_dropped(self):
        tex = ('\\def\\thebibliography#1{\\section*{refs}}\n'
               '\\begin{document}\\begin{thebibliography}{9}\n'
               '\\end{thebibliography}\\end{document}\n')
        out, n = ab.neutralize_tex_defs(tex)
        self.assertEqual(n, 1)
        self.assertNotIn('\\def\\thebibliography', out)
        # The USE must survive; only the definition goes.
        self.assertIn('\\begin{thebibliography}', out)

    def test_an_ordinary_shorthand_is_kept(self):
        # pandoc expands these, and expanding them is how a paper's own
        # notation reaches the page.
        tex = '\\def\\R#1{\\mathbb{R}^{#1}}\n\\begin{document}x\\end{document}'
        out, n = ab.neutralize_tex_defs(tex)
        self.assertEqual(n, 0)
        self.assertIn('\\def\\R', out)

    def test_a_def_named_like_an_unused_environment_is_kept(self):
        # No `\begin{thefigure}` anywhere, so nothing can collide.
        tex = '\\def\\thefigure{\\thesection.\\arabic{figure}}\n' \
              '\\begin{document}x\\end{document}'
        out, n = ab.neutralize_tex_defs(tex)
        self.assertEqual(n, 0)
        self.assertIn('\\def\\thefigure', out)


if __name__ == '__main__':
    unittest.main()
