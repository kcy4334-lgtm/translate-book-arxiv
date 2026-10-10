import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import arxiv_backend  # noqa: E402

BS = chr(92)
NL = "\n"


class LatexTitleTests(unittest.TestCase):
    """arXiv PDFs routinely ship an empty /Title, and the old fallback took the
    document's first heading -- so every paper came out called 'Introduction'.
    The LaTeX \\title{} is the authoritative source and is always available on
    this path, because flat.tex is written before this runs."""

    def extract(self, tex):
        return arxiv_backend.extract_latex_title(tex)

    def test_plain_title(self):
        self.assertEqual(self.extract(BS + "title{Simple Title}"), "Simple Title")

    def test_no_title_returns_empty(self):
        self.assertEqual(self.extract("no title command here"), "")
        self.assertEqual(self.extract(""), "")
        self.assertEqual(self.extract(None), "")

    def test_optional_short_title_is_ignored(self):
        self.assertEqual(
            self.extract(BS + "title[Short]{The Long One}"), "The Long One")

    def test_thanks_and_footnotes_are_dropped_with_their_argument(self):
        """A funding note is not part of the title."""
        self.assertEqual(
            self.extract(BS + "title{Real Title" + BS + "thanks{Funded by X}}"),
            "Real Title")
        self.assertEqual(
            self.extract(BS + "title{A" + BS + "footnote{note} B}"), "A B")

    def test_affiliation_math_marks_are_dropped(self):
        self.assertEqual(self.extract(BS + "title{Deep$^{1,2}$ Learning}"),
                         "Deep Learning")

    def test_formatting_commands_keep_their_text(self):
        self.assertEqual(
            self.extract(BS + "title{A " + BS + "textbf{Bold} Word}"), "A Bold Word")

    def test_forced_line_breaks_become_spaces(self):
        self.assertEqual(self.extract(BS + "title{Line" + BS + BS + " Break}"),
                         "Line Break")

    def test_nested_braces_are_balanced(self):
        self.assertEqual(
            self.extract(BS + "title{Outer {inner} End}"), "Outer inner End")

    def test_ieee_membership_is_dropped(self):
        self.assertEqual(
            self.extract(BS + "title{Paper" + BS + "IEEEmembership{Member, IEEE}}"),
            "Paper")

    def test_tilde_becomes_a_space(self):
        self.assertEqual(self.extract(BS + "title{A~B}"), "A B")

    def test_colon_bearing_title_survives_intact(self):
        """The common 'Name: subtitle' shape must not be truncated."""
        self.assertEqual(
            self.extract(BS + "title{TinyVLA: Towards Fast Models}"),
            "TinyVLA: Towards Fast Models")

    def test_clean_handles_empty_input(self):
        self.assertEqual(arxiv_backend.clean_latex_title(""), "")
        self.assertEqual(arxiv_backend.clean_latex_title(None), "")


class FrontMatterTests(unittest.TestCase):
    """pandoc's LaTeX reader routes `abstract` to document METADATA, and
    converting without --standalone discards it -- so every paper silently lost
    the part of it that gets read most."""

    def test_abstract_becomes_a_starred_section(self):
        tex = BS + "begin{abstract}" + "\n" + "Body text." + "\n" + BS + "end{abstract}"
        out, n = arxiv_backend.sectionize_front_matter(tex)
        self.assertEqual(n, 1)
        self.assertIn(BS + "section*{Abstract}", out)
        self.assertIn("Body text.", out)
        self.assertNotIn(BS + "begin{abstract}", out)

    def test_keywords_become_a_starred_section(self):
        tex = (BS + "begin{IEEEkeywords}" + "\n" + "A, B." + "\n"
               + BS + "end{IEEEkeywords}")
        out, n = arxiv_backend.sectionize_front_matter(tex)
        self.assertEqual(n, 1)
        self.assertIn(BS + "section*{Index Terms}", out)

    def test_starred_so_it_never_takes_a_section_number(self):
        """A numbered Abstract would make the Introduction II, not I."""
        out, _ = arxiv_backend.sectionize_front_matter(
            BS + "begin{abstract}x" + BS + "end{abstract}")
        self.assertIn("section*", out)

    def test_nothing_to_do_is_a_noop(self):
        out, n = arxiv_backend.sectionize_front_matter("plain tex")
        self.assertEqual((out, n), ("plain tex", 0))


class AlgorithmFigureTests(unittest.TestCase):
    """2609.11801 and DDPM set two algorithms side by side in minipages inside
    one figure. pandoc gave the figure the last caption inside it, and the
    book printed "Inference" once more as a stray line under both."""

    def alg(self, name):
        return (BS + "begin{algorithm}[H]" + BS + "caption{" + name + "}\n"
                + BS + "begin{algorithmic}[1]\n" + BS + "State x\n"
                + BS + "end{algorithmic}\n" + BS + "end{algorithm}")

    def test_a_figure_of_only_algorithms_becomes_the_algorithms(self):
        tex = (BS + "begin{figure}[t!]\n" + BS + "begin{minipage}[t]{0.49" + BS
               + "textwidth}\n" + BS + "algrenewcommand{" + BS
               + "algorithmicindent}{0.5em}\n" + self.alg("Training") + "\n"
               + BS + "end{minipage}%\n" + BS + "hfill\n" + BS
               + "begin{minipage}[t]{0.49" + BS + "textwidth}\n"
               + self.alg("Inference") + "\n" + BS + "end{minipage}\n"
               + BS + "end{figure}")
        out, n = arxiv_backend.unwrap_algorithm_figures(tex)
        self.assertEqual(n, 1)
        self.assertNotIn("figure", out)
        self.assertNotIn("minipage", out)
        self.assertEqual(out.count(BS + "begin{algorithm}"), 2)

    def test_a_figure_with_its_own_caption_or_image_is_left_alone(self):
        for extra in (BS + "caption{Both}", BS + "includegraphics{a.png}",
                      "Some words."):
            tex = (BS + "begin{figure}\n" + self.alg("A") + "\n" + extra + "\n"
                   + BS + "end{figure}")
            out, n = arxiv_backend.unwrap_algorithm_figures(tex)
            self.assertEqual((out, n), (tex, 0), extra)


class UnmarkedFootnoteTextTests(unittest.TestCase):
    """pandoc drops a `\\footnotetext` that no `\\footnotemark` waits for. The
    demo paper's "Equal advising" note under its title and a BERT note after a
    table were both lost that way."""

    def test_an_unmarked_note_stays_as_a_paragraph(self):
        tex = (BS + "begingroup" + BS + "renewcommand{" + BS + "thefootnote}{}%\n"
               + BS + "footnotetext{" + BS + "textsuperscript{$*$}Visiting." + BS
               + "quad" + BS + "textsuperscript{" + BS + "dag}Equal advising.}%\n"
               + BS + "endgroup")
        out, n = arxiv_backend.keep_unmarked_footnotetext(tex)
        self.assertEqual(n, 1)
        self.assertNotIn("footnotetext", out)
        self.assertIn("Visiting.", out)
        self.assertIn("{†}Equal advising.", out)
        self.assertNotIn(BS + "dag", out)
        self.assertIn(BS + "endgroup", out)

    def test_a_note_with_its_mark_is_left_to_pandoc(self):
        tex = "Text." + BS + "footnotemark\n\n" + BS + "footnotetext{Paired.}"
        self.assertEqual(arxiv_backend.keep_unmarked_footnotetext(tex), (tex, 0))

    def test_a_commented_note_is_left_alone(self):
        tex = "% " + BS + "footnotetext{Old.}\n"
        self.assertEqual(arxiv_backend.keep_unmarked_footnotetext(tex), (tex, 0))


class ListLabelTests(unittest.TestCase):
    """pandoc ignores enumitem's `label=`; 2609.11801's Q1-Q3 printed 1-3."""

    def test_a_worded_label_is_kept_with_its_own_bold(self):
        tex = (BS + "begin{enumerate}[label={" + BS + "bf Q" + BS + "arabic*}.,"
               "leftmargin=*]\n" + BS + "item First?\n" + BS + "vspace{-0.2em}\n"
               + BS + "item Second?\n" + BS + "end{enumerate}")
        out, n = arxiv_backend.relabel_enumerate(tex)
        self.assertEqual(n, 1)
        self.assertIn("{" + BS + "bf Q1}. First?", out)
        self.assertIn("{" + BS + "bf Q2}. Second?", out)
        self.assertNotIn("enumerate", out)
        self.assertNotIn("vspace", out)

    def test_letters_and_numerals_are_counted(self):
        tex = (BS + "begin{enumerate}[label=(" + BS + "roman*)]\n" + BS + "item a\n"
               + BS + "item b\n" + BS + "item c\n" + BS + "end{enumerate}")
        out, _ = arxiv_backend.relabel_enumerate(tex)
        self.assertIn("(iii) c", out)

    def test_the_plain_label_and_nested_lists_are_left_to_pandoc(self):
        for tex in (BS + "begin{enumerate}[label=" + BS + "arabic*.]\n" + BS
                    + "item a\n" + BS + "end{enumerate}",
                    BS + "begin{enumerate}[leftmargin=*]\n" + BS + "item a\n"
                    + BS + "end{enumerate}",
                    BS + "begin{enumerate}[label=(" + BS + "alph*)]\n" + BS
                    + "item a\n" + BS + "begin{itemize}\n" + BS + "item b\n"
                    + BS + "end{itemize}\n" + BS + "end{enumerate}"):
            self.assertEqual(arxiv_backend.relabel_enumerate(tex), (tex, 0), tex)


class AbstractCommandTests(unittest.TestCase):
    r"""Some classes take the abstract as `\abstract{...}` and print it from
    `\maketitle` (muxlab.cls; A&A's aa.cls with traditabstract). pandoc reads
    no class, so the text was lost: the demo book of 2609.11801 went from the
    authors straight to Figure 1, and Planck 2015 XIII lost its abstract the
    same way."""

    PREAMBLE = (BS + "documentclass{muxlab}\n"
                + BS + "abstract{Humans and " + BS + "textbf{machines} think.%\n}\n"
                + BS + "begin{document}\n" + BS + "maketitle\n"
                + BS + "section{Introduction}\nText.\n" + BS + "end{document}\n")

    def test_a_preamble_abstract_lands_right_after_maketitle(self):
        out, n = arxiv_backend.sectionize_front_matter(self.PREAMBLE)
        self.assertEqual(n, 1)
        title = out.index(BS + "maketitle")
        section = out.index(BS + "section*{Abstract}")
        self.assertLess(title, section)
        self.assertLess(section, out.index(BS + "section{Introduction}"))
        self.assertIn("Humans and " + BS + "textbf{machines} think.", out)
        self.assertLess(out.index(BS + "begin{document}"), out.index("Humans"))

    def test_an_abstract_in_the_body_stays_where_it_is(self):
        tex = (BS + "begin{document}\n" + BS + "abstract{Body abstract.}\n"
               + BS + "maketitle\n")
        out, n = arxiv_backend.sectionize_front_matter(tex)
        self.assertEqual(n, 1)
        self.assertIn(BS + "section*{Abstract}\nBody abstract.\n", out)
        self.assertNotIn(BS + "abstract{", out)

    def test_a_definition_is_not_an_abstract(self):
        for definition in (BS + "newcommand" + BS + "abstract{x}",
                           BS + "renewcommand{" + BS + "abstract}[1]{y}",
                           "% " + BS + "abstract{commented out}"):
            tex = definition + "\n" + BS + "begin{document}\n" + BS + "maketitle\n"
            out, n = arxiv_backend.sectionize_front_matter(tex)
            self.assertEqual((out, n), (tex, 0), definition)

    def test_an_abstract_environment_wins(self):
        """A paper with both keeps the environment and gets one Abstract."""
        tex = (BS + "abstract{command}\n" + BS + "begin{document}\n"
               + BS + "begin{abstract}env" + BS + "end{abstract}\n")
        out, _ = arxiv_backend.sectionize_front_matter(tex)
        self.assertEqual(out.count(BS + "section*{Abstract}"), 1)
        self.assertIn("env", out)


if __name__ == "__main__":
    unittest.main()


class NociteTests(unittest.TestCase):
    """ViT cites Touvron et al. only in Table 2's caption; a table passes
    through as raw LaTeX, citeproc never saw it, and the list lacked it."""

    def test_every_cited_key_is_declared_before_the_end(self):
        tex = ('\\begin{document}Body \\cite{a, b}.\n'
               '\\begin{table*}\\caption{From \\citep[see][]{t}.}\\end{table*}\n'
               '% \\cite{commented}\n\\end{document}')
        out = arxiv_backend.nocite_every_cited_key(tex)
        self.assertIn('\\nocite{a,b,t}\n\\end{document}', out)
        self.assertNotIn('commented}', out.split('\\nocite')[1])

    def test_no_citation_no_change(self):
        tex = '\\begin{document}Plain.\\end{document}'
        self.assertEqual(arxiv_backend.nocite_every_cited_key(tex), tex)


class AddmarginTests(unittest.TestCase):
    """PaLM's worked examples sit in scrextend's `addmargin`."""

    def test_addmargin_becomes_quote(self):
        out = arxiv_backend.sanitize_tex(
            '\\begin{addmargin}[2em]{1em}\nInput (0-shot)\n\\end{addmargin}')
        self.assertIn('\\begin{quote}\nInput (0-shot)\n\\end{quote}', out)


class AlignmentEnvironmentTests(unittest.TestCase):
    """higgs_atlas's author list sits in `flushleft`, which pandoc keeps raw
    under +raw_tex and the HTML writer then drops."""

    def test_flushleft_and_flushright_are_unwrapped(self):
        out = arxiv_backend.sanitize_tex(
            '\\begin{flushleft}\n{\\Large The ATLAS Collaboration}\n'
            'G.~Aad$^{\\rm 48}$,\n\\end{flushleft}\n'
            '\\begin{flushright}Right\\end{flushright}')
        self.assertNotIn('flushleft', out)
        self.assertNotIn('flushright', out)
        self.assertIn('G.~Aad', out)
        self.assertIn('Right', out)

    def test_labelcref_becomes_cref(self):
        out = arxiv_backend.sanitize_tex(
            'the variational bound~\\labelcref{eq:vb} can be')
        self.assertIn('\\cref{eq:vb}', out)
        self.assertNotIn('labelcref', out)

    def test_elsarticle_frontmatter_is_unwrapped(self):
        out = arxiv_backend.sanitize_tex(
            '\\begin{frontmatter}\n\\title{T}\n\\section*{Abstract}\nA search.'
            '\n\\end{frontmatter}')
        self.assertNotIn('frontmatter', out)
        self.assertIn('\\section*{Abstract}\nA search.', out)


class ToggleTests(unittest.TestCase):
    """DDPM picks every figure file with etoolbox's \\iftoggle."""

    TEX = ('\\newtoggle{hqfigures}\n% \\toggletrue{hqfigures}\n'
           '\\togglefalse{hqfigures}  % low quality\n\\begin{document}\n'
           '\\includegraphics{\\iftoggle{hqfigures}{hq/a.pdf}{images/a.jpg}}\n'
           '\\nottoggle{hqfigures}{small}{large}\n'
           '\\iftoggle{unknown}{x}{y}\n')

    def test_the_toggle_as_set_decides(self):
        out, n = arxiv_backend.resolve_toggles(self.TEX)
        self.assertIn('\\includegraphics{images/a.jpg}', out)
        self.assertIn('\nsmall\n', out)
        self.assertEqual(n, 2)

    def test_an_undeclared_toggle_is_left(self):
        out, _n = arxiv_backend.resolve_toggles(self.TEX)
        self.assertIn('\\iftoggle{unknown}{x}{y}', out)

    def test_a_later_setting_wins(self):
        out, _n = arxiv_backend.resolve_toggles(
            self.TEX.replace('\\begin{document}', '\\toggletrue{hqfigures}\n'
                             '\\begin{document}'))
        self.assertIn('\\includegraphics{hq/a.pdf}', out)


class TextSuperscriptTests(unittest.TestCase):
    """higgs_atlas: 3,023 `$^{\\rm 48}$` marks made one 730 KB paragraph of
    MathML that Calibre could not split; the EPUB was never made."""

    def test_upright_marks_become_text(self):
        out, n = arxiv_backend.text_superscripts(
            'G.~Aad$^{\\rm 48}$, A.~B$^{\\rm 164a,164b}$$^{,a}$, '
            'C$^{\\mathrm{1,2}}$')
        self.assertEqual(out, 'G.~Aad\\textsuperscript{48}, '
                              'A.~B\\textsuperscript{164a,164b}$^{,a}$, '
                              'C\\textsuperscript{1,2}')
        self.assertEqual(n, 3)

    def test_formulas_stay_formulas(self):
        for tex in ('m$^{2}$', '$x^{\\rm T}$', '$^{\\rm T}A$', '$^{\\rm max}_i$'):
            self.assertEqual(arxiv_backend.text_superscripts(tex), (tex, 0), tex)


class TildeTests(unittest.TestCase):
    r"""Sentence-BERT's "(\texttildelow 65 hours)" printed as "( hours)":
    pandoc kept the unknown command and the number after it as raw LaTeX."""

    def test_texttildelow_becomes_a_command_pandoc_reads(self):
        out = arxiv_backend.sanitize_tex(r"about (\texttildelow 65 hours) and "
                                         r"\texttildelow{}5 s")
        self.assertIn(r"(\textasciitilde{}65 hours)", out)
        self.assertIn(r"\textasciitilde{}5 s", out)
        self.assertNotIn('texttildelow', out)


class PercentInAUrl(unittest.TestCase):
    """planck's acknowledgement links `planck%2dcollaboration`; pandoc read
    the `%` as a comment and every footnote definition after it was lost."""

    def test_the_percent_is_escaped_in_the_url_only(self):
        tex = ('\\href{http://e.int/planck%2dc}{\\texttt{x}} 50\\% and '
               '\\url{a%20b} % a comment {\n')
        out, n = arxiv_backend.escape_url_percents(tex)
        self.assertEqual(n, 2)
        self.assertIn('\\href{http://e.int/planck\\%2dc}{\\texttt{x}}', out)
        self.assertIn('\\url{a\\%20b}', out)
        self.assertIn('50\\% and', out)
        self.assertIn(' % a comment {', out)


class CaptionofMinipages(unittest.TestCase):
    """gpt3's Figure H.2 is a `\\captionof{figure}` minipage beside H.3's
    `\\caption` one; refused, H.2's caption was not in the book."""

    def test_a_captionof_figure_minipage_splits_too(self):
        tex = ('\\begin{figure}\\begin{minipage}{.33\\textwidth}'
               '\\includegraphics{a}\\captionof{figure}{SAT.}\\label{h2}'
               '\\end{minipage}\\hfill\\begin{minipage}{.6\\textwidth}'
               '\\includegraphics{b}\\caption{Winograd.}\\end{minipage}'
               '\\end{figure}')
        out, n = arxiv_backend.split_captioned_minipages(tex)
        self.assertEqual(n, 1)
        self.assertIn('\\caption{SAT.}', out)
        self.assertEqual(out.count('\\begin{figure}'), 2)

    def test_a_captionof_table_is_left(self):
        tex = ('\\begin{figure}\\begin{minipage}{.5\\textwidth}'
               '\\captionof{table}{T.}\\begin{tabular}{c}x\\end{tabular}'
               '\\end{minipage}\\begin{minipage}{.5\\textwidth}'
               '\\includegraphics{b}\\caption{F.}\\end{minipage}\\end{figure}')
        self.assertEqual(arxiv_backend.split_captioned_minipages(tex), (tex, 0))


class FormulasBackToBack(unittest.TestCase):
    r"""planck's `{$\rm{\Lambda CDM}$}$+A_{\rm L}$` reached the markdown as
    `$..$$..$`; every `$$` pattern read the middle as a display opening."""

    def test_two_become_one(self):
        out, n = arxiv_backend.join_adjacent_inline_math(
            r'the $\rm{\Lambda CDM}$$+A_{\rm L}$ model')
        self.assertEqual(out, r'the ${\rm{\Lambda CDM}}{+A_{\rm L}}$ model')
        self.assertEqual(n, 1)

    def test_a_display_is_left(self):
        text = 'text $a$ and\n$$x = y$$\nmore $b$.'
        self.assertEqual(arxiv_backend.join_adjacent_inline_math(text), (text, 0))

    def test_a_display_right_after_a_formula_is_left(self):
        text = 'see $a$$$x$$ end'
        self.assertEqual(arxiv_backend.join_adjacent_inline_math(text), (text, 0))

    def test_a_code_span_does_not_throw_the_count(self):
        # AlphaQ: a code span mid-paragraph, then `$b$ as $$\begin{equation}`.
        text = ('variance of `PL_Alpha_Hill` here. At bit-width $b$ as '
                '$$\\begin{equation}x\\end{equation}$$ and $c$.')
        self.assertEqual(arxiv_backend.join_adjacent_inline_math(text), (text, 0))
        out, n = arxiv_backend.join_adjacent_inline_math(
            'see `code` then $a$$b$ end')
        self.assertEqual((out, n), ('see `code` then ${a}{b}$ end', 1))

    def test_code_and_escaped_dollars_are_left(self):
        text = 'cost \\$5 and `$a$$b$` here'
        self.assertEqual(arxiv_backend.join_adjacent_inline_math(text), (text, 0))


class ArgumentCountInsideTheName(unittest.TestCase):
    r"""planck: `\providecommand{\arxivlink[1]}{...}` stopped pandoc at
    "unexpected [". LaTeX reads it as `\providecommand{\arxivlink}[1]`."""

    def test_the_count_moves_out_of_the_braces(self):
        out = arxiv_backend.sanitize_tex(
            r"\providecommand{\arxivlink[1]}{\href{http://arxiv.org/abs/#1}{#1}}"
            "\n" r"\newcommand*{ \x [2] }{#1#2}")
        self.assertIn(r"\providecommand{\arxivlink}[1]{\href", out)
        self.assertIn(r"\newcommand*{\x}[2]{#1#2}", out)


class PickBblTests(unittest.TestCase):
    r"""LaTeX reads `\jobname.bbl`; bert ships `lumiere.bbl` beside
    `main.bbl`, and an os.walk took whichever came first."""

    def tree(self, *names):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for name in names:
            Path(root, name).write_text(name, encoding='utf-8')
        return root

    def test_the_one_named_after_the_main_file_wins(self):
        root = self.tree('lumiere.bbl', 'main.bbl', 'zz.bbl')
        got = arxiv_backend.pick_bbl(root, str(Path(root, 'main.tex')))
        self.assertEqual(Path(got).name, 'main.bbl')

    def test_a_single_bbl_is_used_whatever_its_name(self):
        root = self.tree('paper459.bbl')
        got = arxiv_backend.pick_bbl(root, str(Path(root, 'main.tex')))
        self.assertEqual(Path(got).name, 'paper459.bbl')

    def test_the_citation_map_reads_that_file_alone(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        item = BS + 'bibitem[%s(2020)]{k}'
        Path(root, 'main.bbl').write_text(item % 'Right', encoding='utf-8')
        Path(root, 'aaa.bbl').write_text(item % 'Wrong', encoding='utf-8')
        mapping = arxiv_backend.build_citation_map(
            root, str(Path(root, 'main.tex')))
        self.assertEqual(mapping, {'k': 'Right 2020'})


class LlncsTheoremTests(unittest.TestCase):
    r"""llncs defines lemma, theorem, remark... in the class; AdamX never
    declares them, pandoc kept them as raw LaTeX and the build refused."""

    DOC = ('\\documentclass[runningheads]{llncs}\n\\newtheorem{assumption}{Assumption}\n'
           '\\begin{document}\n\\begin{lemma}A\\end{lemma}\\begin{remark}B\\end{remark}\n'
           '\\begin{credits}\\subsubsection{\\ackname} Thanks.\\end{credits}\n'
           '\\end{document}')

    def test_the_used_ones_are_declared_with_their_own_counters(self):
        out, n = arxiv_backend.declare_class_theorems(self.DOC)
        self.assertEqual(n, 2)
        self.assertIn('\\newtheorem{lemma}{Lemma}', out)
        self.assertIn('\\newtheorem{remark}{Remark}', out)
        self.assertNotIn('{theorem}{Theorem}', out)
        self.assertNotIn('newtheorem{assumption}{Assumption}\n\\newtheorem', out)

    def test_credits_lose_their_wrapper(self):
        out, _n = arxiv_backend.declare_class_theorems(self.DOC)
        self.assertNotIn('credits', out)
        self.assertIn('\\subsubsection{Acknowledgements} Thanks.', out)

    def test_a_redefinition_of_ackname_is_left_a_definition(self):
        doc = self.DOC.replace(
            '\\begin{document}',
            '\\renewcommand{\\ackname}{Thanks}\n\\begin{document}')
        out, _n = arxiv_backend.declare_class_theorems(doc)
        self.assertIn('\\renewcommand{\\ackname}{Thanks}', out)
        self.assertIn('\\subsubsection{Acknowledgements}', out)

    def test_envcountsame_shares_the_theorem_counter(self):
        doc = self.DOC.replace('[runningheads]', '[envcountsame]')
        out, _n = arxiv_backend.declare_class_theorems(doc)
        self.assertIn('\\newtheorem{lemma}[theorem]{Lemma}', out)
        self.assertIn('\\newtheorem{theorem}{Theorem}', out)

    def test_another_class_is_left_alone(self):
        doc = self.DOC.replace('{llncs}', '{article}')
        self.assertEqual(arxiv_backend.declare_class_theorems(doc), (doc, 0))


class SubfigureCaptionTests(unittest.TestCase):
    r"""pandoc writes a subfigure's caption as a plain paragraph, which was
    taken for the figure's caption: VAE's figure 4 printed panel (b)'s label
    as its caption and the real one as body text."""

    def test_each_subfigure_caption_becomes_a_bold_paragraph(self):
        tex = ("\\begin{figure}\\begin{subfigure}[t]{0.3\\textwidth}"
               "\\includegraphics{a}\n\\caption{Learned Frey Face manifold}"
               "\\end{subfigure}\\caption{Visualisations.}\\end{figure}")
        out, n = arxiv_backend.bold_subfigure_captions(tex)
        self.assertEqual(n, 1)
        self.assertIn('\\par\\textbf{Learned Frey Face manifold}', out)
        self.assertIn('\\caption{Visualisations.}', out)

    def test_a_caption_outside_a_subfigure_is_left_alone(self):
        tex = "\\begin{figure}\\includegraphics{a}\\caption{X}\\end{figure}"
        self.assertEqual(arxiv_backend.bold_subfigure_captions(tex), (tex, 0))


class ManualEquationTagTests(unittest.TestCase):
    r"""VAE numbers `align*` rows by hand with
    `\newcommand{\eqnr}{\addtocounter{equation}{1}\tag{\theequation}}`. The
    book counted 2 equations of the paper's 24, and printed 22 as raw TeX."""

    DEF = '\\newcommand{\\eqnr}{\\addtocounter{equation}{1}\\tag{\\theequation}}\n'

    def test_the_tagged_row_keeps_its_number_and_the_rest_take_none(self):
        tex = self.DEF + ('\\begin{align*}\na &= b \\\\\nc &= d\n'
                          '\\eqnr\\label{eq:x}\\end{align*}')
        out, n = arxiv_backend.number_manually_tagged_rows(tex)
        self.assertEqual(n, 1)
        self.assertIn('\\begin{align}', out)
        self.assertIn('a &= b \\nonumber', out)
        self.assertIn('c &= d\n\\label{eq:x}\\end{align}', out)
        self.assertNotIn('\\eqnr\\label', out)

    def test_the_literal_idiom_without_a_macro(self):
        tex = ('\\begin{equation*}x = 1 \\addtocounter{equation}{1}'
               '\\tag{\\theequation}\\end{equation*}')
        out, n = arxiv_backend.number_manually_tagged_rows(tex)
        self.assertEqual((out, n), ('\\begin{equation}x = 1 \\end{equation}', 1))

    def test_a_starred_display_with_no_tag_is_left_alone(self):
        tex = self.DEF + '\\begin{align*}a &= b\\end{align*}'
        self.assertEqual(arxiv_backend.number_manually_tagged_rows(tex), (tex, 0))


class CaptionedMinipageTests(unittest.TestCase):
    r"""ViT's figures 3 and 4 are two captioned minipages in one figure;
    pandoc kept only the second caption and printed both images as one."""

    FIG = ("\\begin{figure}\n"
           "\\begin{minipage}[t]{0.47\\textwidth}\\centering\n"
           "\\includegraphics{a}\n\\caption{First.}\\label{fig:a}\n"
           "\\end{minipage}\\;\\;\n"
           "\\begin{minipage}[t]{0.47\\textwidth}\\centering\n"
           "\\includegraphics{b}\n\\caption{Second.}\\label{fig:b}\n"
           "\\end{minipage}\n\\vspace{-3mm}\n\\end{figure}")

    def test_each_captioned_minipage_becomes_a_figure(self):
        out, n = arxiv_backend.split_captioned_minipages(self.FIG)
        self.assertEqual(n, 1)
        self.assertEqual(out.count('\\begin{figure}'), 2)
        first, second = out.split('\\end{figure}')[:2]
        self.assertIn('\\includegraphics{a}', first)
        self.assertIn('First.', first)
        self.assertIn('\\includegraphics{b}', second)
        self.assertNotIn('\\;', out)

    def test_panels_under_one_float_caption_stay_one_figure(self):
        tex = ("\\begin{figure}\\begin{minipage}{.5\\textwidth}\\includegraphics{a}"
               "\\end{minipage}\\begin{minipage}{.5\\textwidth}\\includegraphics{b}"
               "\\end{minipage}\\caption{Both.}\\end{figure}")
        self.assertEqual(arxiv_backend.split_captioned_minipages(tex), (tex, 0))


class GraphicsTabularTests(unittest.TestCase):
    r"""ViT centres its model diagram in a one-cell tabular; pandoc made the
    figure a table and its caption an unnumbered paragraph."""

    def test_a_tabular_holding_only_a_graphic_is_unwrapped(self):
        tex = ("\\begin{figure}[h]\n\\begin{center}\n\\begin{tabular}{c}\n"
               "\\includegraphics[width=.83\\textwidth]{images/model.pdf}\n"
               "\\end{tabular}\n\\end{center}\n\\caption{Model.}\n\\end{figure}")
        out, n = arxiv_backend.unwrap_graphics_tabulars(tex)
        self.assertEqual(n, 1)
        self.assertNotIn('tabular', out)
        self.assertIn('\\includegraphics[width=.83\\textwidth]{images/model.pdf}', out)
        self.assertIn('\\caption{Model.}', out)

    def test_a_grid_of_graphics_is_unwrapped_to_its_panels(self):
        tex = ("\\begin{figure}\\begin{tabular}{cc}\\includegraphics{a} & "
               "\\includegraphics{b} \\\\ \\includegraphics{c} & \\includegraphics{d}"
               "\\end{tabular}\\caption{Grid.}\\end{figure}")
        out, n = arxiv_backend.unwrap_graphics_tabulars(tex)
        self.assertEqual(n, 1)
        self.assertEqual(out.count('\\includegraphics'), 4)

    def test_a_tabular_with_labels_is_a_real_table(self):
        tex = ("\\begin{figure}\\begin{tabular}{cc}Input & Output \\\\ "
               "\\includegraphics{a} & \\includegraphics{b}\\end{tabular}"
               "\\caption{Pairs.}\\end{figure}")
        self.assertEqual(arxiv_backend.unwrap_graphics_tabulars(tex), (tex, 0))

    def test_a_tabular_outside_a_figure_is_left_alone(self):
        tex = "\\begin{tabular}{c}\\includegraphics{a}\\end{tabular}"
        self.assertEqual(arxiv_backend.unwrap_graphics_tabulars(tex), (tex, 0))


class RaisedGraphicTests(unittest.TestCase):
    r"""ViT's figure 7 sets two of its three panels as
    `\raisebox{-0.15in}{\includegraphics..}`; pandoc kept the box as raw
    LaTeX and those two panels never became images."""

    def test_a_raised_graphic_is_unwrapped(self):
        text = (r"\raisebox{-0.15in}{\includegraphics[height=1.5in]{a.pdf}}"
                r" \hfill \raisebox{1pt}[0pt][0pt]{\includegraphics{b.pdf}}")
        out, n = arxiv_backend.unwrap_raised_graphics(text)
        self.assertEqual(n, 2)
        self.assertEqual(out, r"\includegraphics[height=1.5in]{a.pdf}"
                              r" \hfill \includegraphics{b.pdf}")

    def test_a_raised_symbol_is_left_alone(self):
        text = r"& \raisebox{0.5pt}{\tikz\fill[natural] (0,0) circle (.5ex);} DTD"
        self.assertEqual(arxiv_backend.unwrap_raised_graphics(text), (text, 0))


class ResizeboxTests(unittest.TestCase):
    r"""`\begin{table}` + `\caption` + `\resizebox{..}{..}{\begin{tabular}...}`
    loses its caption: pandoc understands `table`, cannot parse `\resizebox`,
    and emits the bare tabular with the caption discarded. `\begin{table*}` is
    not a standard environment so it passes through whole and keeps its
    caption — which is why whether a paper loses captions depends only on which
    of the two its authors used. AlphaQ lost five."""

    def test_unwraps_the_body_and_drops_the_measurements(self):
        text = r"before \resizebox{0.85\linewidth}{!}{TABLE BODY} after"
        out, n = arxiv_backend.unwrap_resizebox(text)
        self.assertEqual(n, 1)
        self.assertEqual(out, "before TABLE BODY after")

    def test_handles_braces_inside_the_body(self):
        text = r"\resizebox{1cm}{!}{\begin{tabular}{l c}a & b\\end{tabular}}"
        out, n = arxiv_backend.unwrap_resizebox(text)
        self.assertEqual(n, 1)
        self.assertNotIn("resizebox", out)
        self.assertTrue(out.startswith(r"\begin{tabular}"))
        self.assertEqual(out.count("{"), out.count("}"))

    def test_scalebox_takes_two_arguments(self):
        text = r"\scalebox{0.9}{KEPT}"
        out, n = arxiv_backend.unwrap_resizebox(text)
        self.assertEqual((out, n), ("KEPT", 1))

    def test_nested_wrappers_all_come_off(self):
        text = r"\resizebox{1cm}{!}{\resizebox{2cm}{!}{INNER}}"
        out, n = arxiv_backend.unwrap_resizebox(text)
        self.assertEqual(out, "INNER")
        self.assertEqual(n, 2)

    def test_a_malformed_wrapper_is_left_alone(self):
        """Missing its third argument: leave it rather than guess."""
        text = r"\resizebox{1cm}{!}"
        out, n = arxiv_backend.unwrap_resizebox(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_sanitize_tex_unwraps_and_keeps_the_caption_reachable(self):
        text = (r"\begin{table}\caption{Real caption here}"
                r"\resizebox{0.8\linewidth}{!}{\begin{tabular}{l}x\\end{tabular}}"
                r"\end{table}")
        out = arxiv_backend.sanitize_tex(text)
        self.assertNotIn("resizebox", out)
        self.assertIn("Real caption here", out)
        self.assertIn(r"\begin{tabular}", out)
        self.assertEqual(out.count("{"), out.count("}"))



class FigureSurvivalTests(unittest.TestCase):
    """Everything here is a figure that reached the reader as nothing at all.

    pandoc's LaTeX reader knows a fixed set of constructs. Anything else --
    a subfig panel, a sidecap float -- passes through as raw LaTeX, and
    resolve_images only rewrites images pandoc already emitted. So the
    picture is dropped, its caption still prints, and no stage reports a
    problem. Papers do not warn you which construct they used."""

    def test_subfloat_panel_is_unwrapped(self):
        tex = (BS + "begin{figure}" + NL
               + BS + "subfloat[]{" + BS + "includegraphics[width=0.4"
               + BS + "textwidth]{figures/pareto.pdf}}" + NL
               + BS + "end{figure}")
        out, n = arxiv_backend.unwrap_subfloat(tex)
        self.assertEqual(n, 1)
        self.assertNotIn(BS + "subfloat", out)
        self.assertIn(BS + "includegraphics", out)

    def test_subfloat_keeps_its_label(self):
        tex = (BS + "subfloat[]{" + BS + "includegraphics{a.pdf}"
               + BS + "label{fig:a}}")
        out, _n = arxiv_backend.unwrap_subfloat(tex)
        self.assertIn(BS + "label{fig:a}", out)

    def test_commented_out_subfloat_stays_hidden(self):
        """Unwrapping lifts the body out from behind its own % comment."""
        tex = ("% " + BS + "subfloat[]{" + BS + "includegraphics{gone.pdf}}")
        out, n = arxiv_backend.unwrap_subfloat(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)

    def test_two_panels_land_in_separate_paragraphs(self):
        """format_figure_blocks only sees an image alone on its line."""
        tex = (BS + "subfloat[]{" + BS + "includegraphics{a.pdf}} "
               + BS + "subfloat[]{" + BS + "includegraphics{b.pdf}}")
        out, n = arxiv_backend.unwrap_subfloat(tex)
        self.assertEqual(n, 2)
        self.assertIn(NL + NL, out)

    def test_the_subfigure_package_command_too(self):
        # higgs_atlas's Figure 5; the subcaption environment is left to pandoc.
        tex = (BS + "subfigure[]{" + BS + "includegraphics{a.eps} }" + NL
               + BS + "subfigure[]{" + BS + "includegraphics{b.eps}}" + NL
               + BS + "begin{subfigure}{0.5" + BS + "linewidth}y"
               + BS + "end{subfigure}")
        out, n = arxiv_backend.unwrap_subfloat(tex)
        self.assertEqual(n, 2)
        self.assertNotIn(BS + "subfigure[", out)
        self.assertIn(BS + "begin{subfigure}", out)

    def test_sidecap_float_becomes_a_figure(self):
        tex = (BS + "begin{SCfigure}[50][t]" + NL
               + BS + "includegraphics{x.pdf}" + NL + BS + "end{SCfigure}")
        out, n = arxiv_backend.normalize_float_envs(tex)
        self.assertEqual(n, 1)
        self.assertIn(BS + "begin{figure}", out)
        self.assertIn(BS + "end{figure}", out)
        self.assertNotIn("SCfigure", out)

    def test_wrapfigure_arguments_are_dropped(self):
        tex = BS + "begin{wrapfigure}{r}{0.5" + BS + "textwidth}"
        out, n = arxiv_backend.normalize_float_envs(tex)
        self.assertEqual(n, 1)
        self.assertEqual(out, BS + "begin{figure}")

    def test_plain_figure_is_left_alone(self):
        tex = BS + "begin{figure}[t]"
        out, n = arxiv_backend.normalize_float_envs(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)


class GraphicPageTests(unittest.TestCase):
    r"""A figure PDF is often a multi-page sheet with one panel per page.
    pandoc drops \includegraphics options, so without carrying the page in
    the filename every panel rasterizes to page 1 -- one wrong plot and one
    duplicate, both of which look like perfectly ordinary figures."""

    def test_page_option_is_carried_into_the_name(self):
        tex = BS + "includegraphics[width=1cm,page=4]{figures/x.pdf}"
        out, n = arxiv_backend.encode_graphic_pages(tex)
        self.assertEqual(n, 1)
        self.assertIn("figures/x--page4.pdf", out)

    def test_page_one_needs_no_tag(self):
        tex = BS + "includegraphics[page=1]{figures/x.pdf}"
        out, n = arxiv_backend.encode_graphic_pages(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)

    def test_no_page_option_is_untouched(self):
        tex = BS + "includegraphics[width=2cm]{figures/x.pdf}"
        out, n = arxiv_backend.encode_graphic_pages(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)

    def test_tag_round_trips(self):
        self.assertEqual(arxiv_backend.split_page_tag("figures/x--page4.pdf"),
                         ("figures/x.pdf", 4))
        self.assertEqual(arxiv_backend.split_page_tag("figures/x.pdf"),
                         ("figures/x.pdf", 1))

    def test_encoding_is_idempotent(self):
        tex = BS + "includegraphics[page=4]{figures/x.pdf}"
        once, _ = arxiv_backend.encode_graphic_pages(tex)
        twice, n = arxiv_backend.encode_graphic_pages(once)
        self.assertEqual(n, 0)
        self.assertEqual(once, twice)


class EmptyCodeSpanTests(unittest.TestCase):
    """strip_latex_cruft removes the command from inside a code span and used
    to leave the span. An empty `` renders as nothing but still counts as
    content, so it pushed an image off the end of its own line and
    format_figure_blocks stopped recognising the image."""

    def test_empty_span_left_by_a_stripped_label_is_removed(self):
        text = "![image](images/x.png)`" + BS + "label{fig:a}`"
        self.assertEqual(arxiv_backend.strip_latex_cruft(text),
                         "![image](images/x.png)")

    def test_real_code_span_survives(self):
        text = "use `git status` here"
        self.assertEqual(arxiv_backend.strip_latex_cruft(text), text)


class CruftWhitespaceTests(unittest.TestCase):
    r"""The whitespace after a stripped command must not cross a newline.

    It was `\s*`, which matches newlines, so a command with no argument ate
    everything up to the next word. VLA-Adapter writes `{\small` in front of
    a `verbatim` listing; pandoc leaves `\small` alone on a line above an
    indented code block, and the match came out as twelve characters ending
    in the four spaces that made the next line code. At column zero that line
    is a paragraph, so the listing broke in two and its first line was
    typeset as body prose in a serif face beside the code it belongs to.
    """

    def strip(self, text):
        return arxiv_backend.strip_latex_cruft(text)

    def test_the_shipped_listing_keeps_its_indentation(self):
        text = ("below:\n\n" + BS + "small\n\n"
                "    class MLPResNetBlock_Pro(nn.Module):\n"
                "        pass\n")
        got = self.strip(text)
        self.assertIn("\n    class MLPResNetBlock_Pro", got)
        self.assertNotIn(BS + "small", got)

    def test_indentation_survives_for_every_stripped_command(self):
        for name in ('small', 'noindent', 'centering', 'bigskip',
                     'clearpage', 'footnotesize'):
            text = BS + name + "\n\n    indented line\n"
            self.assertIn("\n    indented line", self.strip(text), name)

    def test_an_argument_on_the_same_line_still_comes_off(self):
        self.assertEqual(self.strip(BS + "vspace{-2.5mm}"), "")
        self.assertEqual(self.strip(BS + "vspace {-2.5mm}"), "")
        self.assertEqual(self.strip(BS + "vspace*{-2.5mm}"), "")

    def test_an_argument_on_the_next_line_still_comes_off(self):
        r"""K111: the starred form once lost its head and left `{-2.5mm}`
        standing on the page. A brace left behind is the failure that branch
        exists to prevent, so it has to survive the newline restriction."""
        self.assertEqual(self.strip(BS + "vspace\n{-2.5mm}"), "")

    def test_a_trailing_space_still_comes_off(self):
        self.assertEqual(self.strip(BS + "noindent   text"), "text")

    def test_the_paragraph_break_is_left_where_it_was(self):
        r"""Downstream expects it: `repair_display_math` and the `\n{4,}`
        collapse both run after this and read the paragraph breaks."""
        got = self.strip("a\n\n" + BS + "centering\n\nb\n")
        self.assertTrue(got.startswith('a\n\n'))
        self.assertTrue(got.endswith('\n\nb\n'))


class ColumnSpecTests(unittest.TestCase):
    """pandoc understands `*{9}{r}` perfectly well, and that is the problem:
    reading the tabular it expands the repeat, and writing the raw block back
    out it emits the ORIGINAL spec followed by the expansion. Twenty-one
    columns where the paper has twelve, so every row rendered with nine empty
    cells after it and SINQ's results were squeezed into half the page."""

    def spec(self, tex):
        return arxiv_backend.expand_tabular_stars(tex)

    def test_repeat_is_expanded(self):
        out, n = self.spec(BS + "begin{tabular}{l l l*{9}{r}}")
        self.assertEqual(n, 1)
        self.assertEqual(out, BS + "begin{tabular}{l l lrrrrrrrrr}")

    def test_the_original_spec_does_not_survive(self):
        out, _n = self.spec(BS + "begin{tabular}{l*{3}{c}}")
        self.assertNotIn("*{3}", out)
        self.assertEqual(out.count("c"), 3)

    def test_other_column_letters_are_kept(self):
        out, _n = self.spec(BS + "begin{tabular}{l@{} l l*{2}{c}}")
        self.assertEqual(out, BS + "begin{tabular}{l@{} l lcc}")

    def test_a_spec_without_a_repeat_is_untouched(self):
        tex = BS + "begin{tabular}{lrrr}"
        out, n = self.spec(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)

    def test_every_environment_is_covered(self):
        for env in ("tabular", "tabularx", "longtable", "array"):
            out, n = self.spec(BS + "begin{" + env + "}{*{2}{c}}")
            self.assertEqual(n, 1, env)
            self.assertIn("{cc}", out)

    def test_expansion_is_idempotent(self):
        once, _ = self.spec(BS + "begin{tabular}{l*{4}{r}}")
        twice, n = self.spec(once)
        self.assertEqual(n, 0)
        self.assertEqual(once, twice)


class BoxedLabelTests(unittest.TestCase):
    """A rotated or row-spanning label is how a narrow column carries a group
    name. pandoc drops both calls whole -- argument and all -- so SINQ's
    bit-width column came out empty in every table that used one: the rows
    were there and nothing said which group they belonged to."""

    def test_rotatebox_keeps_its_text(self):
        out, n = arxiv_backend.unwrap_rotatebox(
            BS + "rotatebox[origin=c]{90}{" + BS + "textsc{4-bit}}")
        self.assertEqual(n, 1)
        self.assertEqual(out, BS + "textsc{4-bit}")

    def test_multirow_keeps_its_text(self):
        out, n = arxiv_backend.unwrap_rotatebox(
            BS + "multirow{4}{*}{" + BS + "textsc{3-bit}}")
        self.assertEqual(n, 1)
        self.assertEqual(out, BS + "textsc{3-bit}")

    def test_nested_braces_survive(self):
        """The body is normally `{\textsc{...}}`, not a flat string."""
        out, _n = arxiv_backend.unwrap_rotatebox(
            BS + "multirow{10}{*}{" + BS + "textsc{Calibration free}} & x")
        self.assertEqual(out, BS + "textsc{Calibration free} & x")

    def test_several_in_one_row(self):
        row = (BS + "multirow{10}{*}{A} & " + BS + "rotatebox{90}{B} & C")
        out, n = arxiv_backend.unwrap_rotatebox(row)
        self.assertEqual(n, 2)
        self.assertEqual(out, "A & B & C")

    def test_unrelated_text_is_untouched(self):
        tex = BS + "textbf{plain}"
        out, n = arxiv_backend.unwrap_rotatebox(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)


class TitleBlockTests(unittest.TestCase):
    """ICML-style classes put title, authors and keywords inside
    `\twocolumn[...]`. pandoc has no reader for it, so the whole block came
    through as raw LaTeX and sat at the top of the exported markdown: 37 lines
    of "It is OKAY to include author information" before the paper began."""

    def test_the_block_goes(self):
        tex = (BS + "begin{document}" + NL + BS + "twocolumn[" + NL
               + BS + "icmltitle{A Paper}" + NL + "% a template comment" + NL
               + "]" + NL + BS + "section*{Abstract}" + NL + "Real text.")
        out, n = arxiv_backend.strip_title_block(tex)
        self.assertEqual(n, 1)
        self.assertNotIn("icmltitle", out)
        self.assertNotIn("template comment", out)
        self.assertIn("Real text.", out)

    def test_a_block_holding_the_abstract_is_left_alone(self):
        """Losing an abstract would be far worse than keeping the noise."""
        tex = (BS + "twocolumn[" + NL + BS + "icmltitle{A Paper}" + NL
               + BS + "begin{abstract}" + NL + "The abstract." + NL
               + BS + "end{abstract}" + NL + "]")
        out, n = arxiv_backend.strip_title_block(tex)
        self.assertEqual(n, 0)
        self.assertIn("The abstract.", out)

    def test_a_block_holding_a_section_is_left_alone(self):
        """sectionize_front_matter runs first, so an abstract arrives as one."""
        tex = (BS + "twocolumn[" + BS + "section*{Abstract}" + NL + "Text." + NL
               + "]")
        _out, n = arxiv_backend.strip_title_block(tex)
        self.assertEqual(n, 0)

    def test_nested_brackets_do_not_end_the_block_early(self):
        tex = (BS + "twocolumn[" + BS + "icmlauthor[note]{A}{B}" + NL + "]"
               + NL + "After.")
        out, n = arxiv_backend.strip_title_block(tex)
        self.assertEqual(n, 1)
        self.assertEqual(out.strip(), "After.")

    def test_plain_twocolumn_without_brackets_is_untouched(self):
        tex = BS + "twocolumn" + NL + "Body."
        out, n = arxiv_backend.strip_title_block(tex)
        self.assertEqual(n, 0)
        self.assertEqual(out, tex)


class TableRuleTests(unittest.TestCase):
    r"""`\cmidrule` leaks its argument into a cell if kept and takes the
    row-group separator with it if deleted. SINQ's 3-bit and 4-bit blocks ran
    together with nothing between them because every one was deleted."""

    def tab(self, body):
        return (BS + "begin{tabular}{lll}" + NL + body + NL
                + BS + "end{tabular}")

    def test_a_rule_under_a_column_group_is_dropped(self):
        """CSS underlines a spanning header cell from its colspan instead."""
        tex = self.tab(BS + "toprule" + NL + "A & B & C" + BS + BS + NL
                       + BS + "cmidrule(lr){2-3}" + NL
                       + "D & E & F" + BS + BS + NL + BS + "midrule" + NL
                       + "1 & 2 & 3" + BS + BS)
        out, kept = arxiv_backend.normalize_table_rules(tex)
        self.assertEqual(kept, 0)
        self.assertNotIn("cmidrule", out)

    def test_a_rule_between_row_groups_becomes_a_midrule(self):
        tex = self.tab(BS + "toprule" + NL + "A & B & C" + BS + BS + NL
                       + BS + "midrule" + NL + "1 & 2 & 3" + BS + BS + NL
                       + BS + "cmidrule(lr){1-3}" + NL
                       + "4 & 5 & 6" + BS + BS)
        out, kept = arxiv_backend.normalize_table_rules(tex)
        self.assertEqual(kept, 1)
        self.assertNotIn("cmidrule", out)
        self.assertEqual(out.count(BS + "midrule"), 2)

    def test_cline_is_treated_the_same(self):
        tex = self.tab(BS + "toprule" + NL + "A & B & C" + BS + BS + NL
                       + BS + "midrule" + NL + "1 & 2 & 3" + BS + BS + NL
                       + BS + "cline{1-3}" + NL + "4 & 5 & 6" + BS + BS)
        out, kept = arxiv_backend.normalize_table_rules(tex)
        self.assertEqual(kept, 1)
        self.assertNotIn("cline", out)

    def test_a_trim_with_widths_is_read(self):
        # PaLM: "(l 3pt r 3pt ) 2-3" printed in a header cell.
        tex = self.tab("& A & B" + BS + BS + NL + BS + "cmidrule(l{3pt}r{3pt}){2-3}"
                       + NL + "x & 1 & 2" + BS + BS)
        out, _kept = arxiv_backend.normalize_table_rules(tex)
        self.assertNotIn("3pt", out)
        self.assertNotIn("2-3", out)

    def test_text_outside_a_tabular_is_untouched(self):
        tex = "prose " + BS + "cmidrule(lr){1-2} more prose"
        out, kept = arxiv_backend.normalize_table_rules(tex)
        self.assertEqual((out, kept), (tex, 0))

    def test_no_argument_ever_survives_into_a_cell(self):
        """"4-6" in the first cell is what deleting them was meant to fix."""
        tex = self.tab(BS + "toprule" + NL + "A & B & C" + BS + BS + NL
                       + BS + "cmidrule(lr){4-6} " + BS + "cmidrule(lr){7-9}"
                       + NL + BS + "midrule" + NL + "1 & 2 & 3" + BS + BS)
        out, _kept = arxiv_backend.normalize_table_rules(tex)
        self.assertNotIn("4-6", out)
        self.assertNotIn("7-9", out)


class AnInputIsResolvedBeforePandocSeesIt(unittest.TestCase):
    r"""`input` sat under NEVER SEEN, and never seen is never tested.

    `flatten_tex` exists because an unresolved `\input` deletes a whole
    section and the loss is invisible in the output: no error, no warning
    in the book, just a paper missing its method. Nothing had ever put a
    real one in front of it.

    It turned out to be right, which is the answer worth having. These
    tests are here so it stays right, and because two of the four shapes
    checked in this batch were already correct -- writing tests against an
    assumed bug would have locked in the wrong answer.
    """

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.work), True)

    def write(self, rel, text):
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def flatten(self, text):
        root = self.write("main.tex", text)
        return arxiv_backend.flatten_tex(str(root), str(self.work))

    def test_the_section_body_arrives(self):
        self.write("sections/method.tex",
                   BS + "section{Method}" + NL + "The body of the section.")
        out = self.flatten(BS + "input{sections/method}" + NL)
        self.assertIn("The body of the section.", out)

    def test_an_input_inside_an_input(self):
        self.write("a.tex", BS + "input{b}")
        self.write("b.tex", "the innermost text")
        self.assertIn("the innermost text", self.flatten(BS + "input{a}"))

    def test_a_commented_out_input_is_not_followed(self):
        self.write("secret.tex", "text nobody should see")
        out = self.flatten("%% " + BS + "input{secret}" + NL)
        self.assertNotIn("text nobody should see", out)

    def test_a_cycle_terminates(self):
        """Two files including each other. The guard is why this returns
        at all rather than recursing until the interpreter gives up."""
        self.write("a.tex", "alpha" + NL + BS + "input{b}")
        self.write("b.tex", "beta" + NL + BS + "input{a}")
        out = self.flatten(BS + "input{a}")
        self.assertIn("alpha", out)
        self.assertIn("beta", out)

    def test_an_unresolved_input_leaves_the_line_alone(self):
        r"""Deleting it would be the silent loss this function exists to
        prevent. The line stays, and `flatten_tex` prints a warning."""
        out = self.flatten("before" + NL + BS + "input{nowhere}" + NL + "after")
        self.assertIn("before", out)
        self.assertIn("after", out)
        self.assertIn("nowhere", out)

    def test_text_on_the_same_line_survives_on_both_sides(self):
        self.write("mid.tex", "MIDDLE")
        out = self.flatten("left " + BS + "input{mid}" + " right")
        self.assertIn("left", out)
        self.assertIn("MIDDLE", out)
        self.assertIn("right", out)
