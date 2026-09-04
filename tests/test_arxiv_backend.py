import sys
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


if __name__ == "__main__":
    unittest.main()


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
