import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import layout  # noqa: E402


class LangConfigTests(unittest.TestCase):
    def test_every_entry_has_the_full_key_set(self):
        keys = {"lang_attr", "font_family", "font_family_ebook", "toc_label",
                "pdf_font", "figure_label", "table_label", "equation_label",
                "section_label", "appendix_label", "algorithm_label",
                "theorem_label", "theorem_words", "ref_formats",
                "references_label", "particle_agreement"}
        for code, cfg in layout.LANG_CONFIG.items():
            self.assertEqual(set(cfg), keys, f"{code} has the wrong keys")

    def test_reference_labels_cover_every_kind(self):
        """A (sec:x) or (eq:y) reference needs a word in the target language."""
        for code, cfg in layout.LANG_CONFIG.items():
            for key in ("equation_label", "section_label", "appendix_label",
                        "algorithm_label", "theorem_label"):
                self.assertTrue(cfg[key].strip(), f"{code}.{key} is empty")
            self.assertIsInstance(cfg["ref_formats"], dict)
            for slot, template in cfg["ref_formats"].items():
                # Korean writes "4.1절", not "절 4.1"; whatever the order, both
                # fields have to survive into the string.
                rendered = template.format(label="L", number="9")
                self.assertIn("L", rendered, f"{code}.{slot} drops the label")
                self.assertIn("9", rendered, f"{code}.{slot} drops the number")

    def test_korean_puts_the_section_marker_after_the_number(self):
        formats = layout.get_lang_config("ko")["ref_formats"]
        self.assertEqual(
            formats["section"].format(label="절", number="4.1"), "4.1절")

    def test_float_labels_are_localised(self):
        """(fig:x) resolves to "그림 N" in Korean, not "Figure N"."""
        self.assertEqual(layout.get_lang_config("ko")["figure_label"], "그림")
        self.assertEqual(layout.get_lang_config("ko")["table_label"], "표")
        self.assertEqual(layout.DEFAULT_LANG_CONFIG["figure_label"], "Figure")

    def test_ko_uses_a_static_embeddable_serif(self):
        cfg = layout.get_lang_config("ko")
        self.assertIn("HCR Batang", cfg["font_family"])
        self.assertIn("HCR Batang", cfg["font_family_ebook"])
        self.assertEqual(cfg["pdf_font"], "HCR Batang")

    def test_no_config_references_nanum_myeongjo(self):
        """Regression lock: it is not installed on Windows and resolved to Batang."""
        for code, cfg in layout.LANG_CONFIG.items():
            for key, value in cfg.items():
                self.assertNotIn("Nanum Myeongjo", str(value), f"{code}.{key}")

    def test_ko_stack_lists_no_variable_font(self):
        """Chromium cannot subset-embed a variable font; it emits one Type3
        object per glyph instead, which bloats the PDF ~8x."""
        cfg = layout.get_lang_config("ko")
        for banned in ("Noto Serif KR", "Noto Sans KR"):
            self.assertNotIn(banned, cfg["font_family"])
            self.assertNotIn(banned, cfg["font_family_ebook"])

    def test_ko_leads_with_a_latin_face(self):
        """font-family resolves per character, so a Latin-only face first is
        what gives the embedded English real italics and bold."""
        self.assertTrue(layout.get_lang_config("ko")["font_family"]
                        .startswith("'Noto Serif'"))

    def test_unknown_language_falls_back(self):
        self.assertIs(layout.get_lang_config("xx"), layout.DEFAULT_LANG_CONFIG)

    def test_loose_resolver_maps_region_codes(self):
        cases = {
            "zh-CN": "zh", "ko-KR": "ko", "KO": "ko", "ja": "ja",
            "ko_KR": "ko", "pt-BR": None, "": None, None: None,
        }
        for given, expect in cases.items():
            got = layout.get_lang_config_loose(given)
            want = (layout.LANG_CONFIG[expect] if expect
                    else layout.DEFAULT_LANG_CONFIG)
            self.assertIs(got, want, f"{given!r}")


class PrintProfileTests(unittest.TestCase):
    def test_default_profile_exists(self):
        self.assertIn(layout.DEFAULT_PRINT_PROFILE, layout.PRINT_PROFILES)

    def test_every_profile_has_the_keys_the_renderer_reads(self):
        needed = {"page_size", "margin_top_mm", "margin_right_mm",
                  "margin_bottom_mm", "margin_left_mm",
                  "base_font_size_pt", "line_height"}
        for name, cfg in layout.PRINT_PROFILES.items():
            self.assertTrue(needed.issubset(cfg), f"{name} is missing keys")

    def test_page_margin_css_is_trbl_order(self):
        cfg = layout.get_print_profile("a4-book")
        self.assertEqual(layout.page_margin_css(cfg), "18mm 18mm 22mm 18mm")

    def test_template_values_covers_every_declared_token(self):
        cfg = layout.get_print_profile()
        self.assertEqual(set(layout.template_values(cfg)),
                         set(layout.TEMPLATE_TOKENS))

    def test_template_values_are_css_ready_strings(self):
        vals = layout.template_values(layout.get_print_profile("a4-book"))
        self.assertEqual(vals["page_size"], "A4")
        self.assertEqual(vals["print_font_size"], "11.5pt")
        self.assertEqual(vals["print_line_height"], "1.75")
        for v in vals.values():
            self.assertIsInstance(v, str)

    def test_unknown_profile_falls_back_to_default(self):
        self.assertEqual(layout.get_print_profile("nope"),
                         layout.get_print_profile(layout.DEFAULT_PRINT_PROFILE))

    def test_overrides_do_not_mutate_the_source(self):
        before = layout.PRINT_PROFILES["a4-book"]["base_font_size_pt"]
        cfg = layout.get_print_profile("a4-book", {"base_font_size_pt": 99})
        self.assertEqual(cfg["base_font_size_pt"], 99)
        self.assertEqual(layout.PRINT_PROFILES["a4-book"]["base_font_size_pt"], before)

    def test_bottom_margin_leaves_room_for_the_stamped_folio(self):
        """chromium_pdf places the page number inside the bottom band, so it
        has to be deeper than the top margin."""
        for name, cfg in layout.PRINT_PROFILES.items():
            self.assertGreater(cfg["margin_bottom_mm"], cfg["margin_top_mm"],
                               f"{name}: folio would crowd the text block")


class TemplateContractTests(unittest.TestCase):
    """The template and the substitution table must not drift apart."""

    def test_ebook_template_declares_the_page_rule(self):
        text = (SCRIPT_DIR / "template_ebook.html").read_text(encoding="utf-8")
        self.assertIn("@page", text)
        for token in ("$page_size$", "$page_margin$",
                      "$print_font_size$", "$print_line_height$"):
            self.assertIn(token, text, f"{token} missing from template_ebook.html")

    def test_multi_row_equations_get_row_spacing(self):
        """MathML Core dropped the rowspacing attribute, so the rows of an
        `aligned` block touch unless CSS separates them: measured 15.0/18.0pt
        apart at 12pt math, which read as one line. The child combinator keeps
        the rule off matrices, which are nested <mtable>s between their
        fences."""
        css = (SCRIPT_DIR / "template_ebook.html").read_text(encoding="utf-8")
        selector = 'math[display="block"] > semantics > mtable'
        self.assertIn(selector, css)
        print_block = css[css.index("@media print"):]
        self.assertIn(selector, print_block,
                      "the print sheet needs it too, not just the screen one")
        for line in css.splitlines():
            stripped = line.strip()
            if stripped.startswith("mtable {"):
                self.assertNotIn(
                    "border-spacing", stripped,
                    "an unscoped mtable rule would loosen matrices too")

    def test_ebook_template_print_block_is_last(self):
        """At equal specificity the later rule wins. The math/figure/table
        block used to sit after the print block and silently override it."""
        text = (SCRIPT_DIR / "template_ebook.html").read_text(encoding="utf-8")
        self.assertLess(text.index("figure { margin:"), text.index("@media print"))

    def test_responsive_blocks_are_scoped_to_screen(self):
        """The A4 page area is ~658 CSS px, so an unscoped max-width:768px
        query matches while printing and drops headings to phone sizes."""
        text = (SCRIPT_DIR / "template_ebook.html").read_text(encoding="utf-8")
        self.assertNotIn("@media (max-width", text)
        self.assertIn("@media screen and (max-width: 768px)", text)


if __name__ == "__main__":
    unittest.main()


class ParticleAgreementTests(unittest.TestCase):
    """Korean picks a particle by the sound of the syllable before it, so a
    number substituted into a finished sentence can leave the wrong one:
    twelve of "그림 1를" and "표 9은" shipped. Only Korean needs this, but
    every entry carries the key so the table stays answerable."""

    def test_korean_has_it_on(self):
        self.assertIs(layout.LANG_CONFIG["ko"]["particle_agreement"], True)

    def test_no_other_language_does(self):
        for code, cfg in layout.LANG_CONFIG.items():
            if code == "ko":
                continue
            self.assertIs(cfg["particle_agreement"], False, code)

    def test_the_key_is_declared_once_per_language(self):
        """A duplicate key silently wins, and the feature would be off."""
        import io
        import re
        from pathlib import Path
        src = io.open(Path(layout.__file__), encoding="utf-8").read()
        block = src[src.index("'ko': {"):]
        block = block[:block.index("\n    },")]
        self.assertEqual(block.count("'particle_agreement'"), 1)


class DisplayMathCenteringTests(unittest.TestCase):
    """`text-align: center` on a block <math> centres the inline content
    around the formula, not the formula: every display equation printed at
    x=51 on a page whose centre is 297. A flex container centres its one
    child and, unlike `width: fit-content`, keeps the element full width --
    which is what the equation number's `right: 0` is measured against."""

    def sheet(self):
        import io
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "scripts" / "template_ebook.html"
        return io.open(path, encoding="utf-8").read()

    def blocks(self):
        """The math rule as it appears in the screen sheet and the print one."""
        import re
        return re.findall(r'math\[display="block"\]\s*\{[^}]*\}', self.sheet())

    def test_both_sheets_centre_with_flex(self):
        found = [b for b in self.blocks() if "justify-content: center" in b]
        self.assertEqual(len(found), 2,
                         "screen and print must both centre display maths")

    def test_neither_sheet_relies_on_text_align(self):
        for block in self.blocks():
            self.assertNotIn("text-align: center", block)

    def test_the_equation_number_padding_is_symmetric(self):
        """With padding only on the right a numbered equation sat 17pt left
        of centre."""
        import re
        rules = re.findall(r'math\[display="block"\]\[data-eqno\]\s*\{[^}]*\}',
                           self.sheet())
        self.assertEqual(len(rules), 2)
        for rule in rules:
            self.assertIn("padding-left: 3em", rule)
            self.assertIn("padding-right: 3em", rule)


class TableRuleStyleTests(unittest.TestCase):
    """A dense results table is unreadable without its rules. SINQ's main
    table printed nine numeric columns with no line under the header and
    nothing showing which three belonged to which model."""

    def sheet(self):
        import io
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "scripts" / "template_ebook.html"
        return io.open(path, encoding="utf-8").read()

    def test_the_header_is_ruled_off(self):
        self.assertIn("thead th { border-bottom", self.sheet())

    def test_a_column_group_is_underlined(self):
        r"""This is what \cmidrule draws and pandoc cannot carry."""
        self.assertIn('thead th[colspan]:not(:empty)', self.sheet())

    def test_a_row_group_gets_a_rule_above_it(self):
        self.assertIn("tbody tr.rule-above", self.sheet())
