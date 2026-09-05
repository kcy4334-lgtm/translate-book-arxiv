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
    r"""Two ways of centring a display equation have already been wrong here.

    `text-align: center` on a block <math> centres the inline content around
    the formula rather than the formula, and a short equation printed at
    x=51 on a page whose centre is 297.

    Flex centred it correctly and lost content instead: a formula wider than
    its flex container drops its FIRST CHILD outright. VLA-Adapter's equation
    (3) printed starting at a bare `=`, its left-hand side absent from the
    PDF content stream -- no glyph, not even a zero-width one -- while a
    short equation rendered perfectly, which is why it survived every check.

    What is there now centres the inner <semantics> box, so the <math>
    element stays full width for the equation number's `right: 0` to measure
    against, and the formula is painted whole. Checked against flex on a
    three-row `aligned` block and on a matrix: identical output, so the row
    spacing tuned further down the sheet is unaffected."""

    def sheet(self):
        import io
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "scripts" / "template_ebook.html"
        return io.open(path, encoding="utf-8").read()

    def blocks(self):
        """The math rule as it appears in the screen sheet and the print one."""
        import re
        return re.findall(r'math\[display="block"\]\s*\{[^}]*\}', self.sheet())

    def semantics_rules(self):
        import re
        return re.findall(
            r'math\[display="block"\]\s*>\s*semantics\s*\{[^}]*\}',
            self.sheet())

    def test_neither_sheet_uses_flex(self):
        """The rule that cost equation (3) its left-hand side."""
        for block in self.blocks():
            self.assertNotIn("display: flex", block)
            self.assertNotIn("justify-content", block)

    def test_both_sheets_centre_the_semantics_box(self):
        found = [r for r in self.semantics_rules()
                 if "width: fit-content" in r and "margin: 0 auto" in r]
        self.assertEqual(len(found), 2,
                         "screen and print must both centre display maths")

    def test_the_math_element_stays_full_width(self):
        """The equation number is positioned against it, so a shrunk <math>
        would pull the number in beside the formula instead of the margin."""
        for block in self.blocks():
            self.assertNotIn("width: fit-content", block)
            self.assertIn("display: block", block)

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


class CjkSerifStackTests(unittest.TestCase):
    r"""What a CJK stack falls back to when the local face is absent.

    Measured on a Korean Windows: the Japanese stack named three Mincho
    faces, all of them tied to a platform or a language pack -- Hiragino is
    macOS, Yu Mincho wants a Japanese Windows, MS Mincho ships with the
    pack. With none installed the stack reached the generic `serif` keyword,
    and for Japanese the browser answered with Yu GOTHIC. The body set in a
    sans where the design says serif, and nothing anywhere said so.

    Source Han Serif JP was tried as the portable answer and rejected on
    measurement: it is CFF, and this Chromium emits it as a Type3 font.
    Naming it would make a machine without a Mincho choose a Type3 serif
    over a cleanly embedded Gothic -- worse than the problem. The rule this
    project already holds for Korean is "static, 0 Type3", and it applies to
    every script.
    """

    def stack(self, code):
        return layout.LANG_CONFIG[code]['font_family']

    def ebook_stack(self, code):
        return layout.LANG_CONFIG[code]['font_family_ebook']

    def test_japanese_names_a_portable_serif(self):
        stack = self.stack('ja')
        self.assertIn('Noto Serif JP', stack)
        self.assertLess(stack.index('Noto Serif JP'), stack.index('serif,')
                        if 'serif,' in stack else len(stack))

    def test_chinese_names_a_face_a_stock_windows_has(self):
        """FangSong is absent outside China; SimSun is the named fallback,
        rather than leaving the generic keyword to guess."""
        self.assertIn('SimSun', self.stack('zh'))

    def test_no_cjk_stack_names_a_type3_producer(self):
        for code in ('ja', 'zh', 'ko'):
            for stack in (self.stack(code), self.ebook_stack(code)):
                self.assertNotIn('Source Han', stack, code)
                self.assertNotIn('Noto Serif CJK', stack, code)

    def test_every_cjk_stack_still_ends_at_the_generic_keyword(self):
        """The last resort has to stay, or a machine with none of the named
        faces gets no font at all rather than an imperfect one."""
        for code in ('ja', 'zh', 'ko'):
            self.assertTrue(self.stack(code).rstrip().endswith('serif'), code)

    def test_the_portable_entries_come_after_the_local_ones(self):
        """A machine that HAS the paper's own typeface must keep using it."""
        stack = self.stack('ja')
        self.assertLess(stack.index('MS Mincho'), stack.index('Noto Serif JP'))


class PrintSheetAndLayoutAgreeTests(unittest.TestCase):
    r"""Two places decide the body face, and they drifted.

    `layout.LANG_CONFIG['font_family']` reaches the screen sheet through the
    `$body_font$` token. The print sheet does not use it at all: it declares
    its own `--p-serif` per `:lang()`. So a stack fixed in layout.py changed
    the EPUB and left the PDF alone, and the PDF is the file people look at.

    That is how a Japanese body kept setting in a Gothic after the fix that
    was supposed to end it. The faces that matter have to be named in both,
    and this checks they are.
    """

    def sheet(self):
        import io
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / "scripts"
                / "template_ebook.html")
        return io.open(path, encoding="utf-8").read()

    def print_serif(self, code):
        import re
        block = re.search(r'html:lang\(%s\)\s*\{(.*?)\}' % code,
                          self.sheet(), re.S)
        self.assertIsNotNone(block, 'no print rule for %s' % code)
        decl = re.search(r'--p-serif:\s*([^;]+);', block.group(1))
        self.assertIsNotNone(decl, 'no --p-serif for %s' % code)
        return decl.group(1)

    def families(self, stack):
        import re
        return {n.strip() for n in re.findall(r"'([^']+)'", stack)}

    def test_the_faces_layout_names_are_named_in_the_print_sheet_too(self):
        for code in ('ko', 'ja', 'zh'):
            declared = self.families(layout.LANG_CONFIG[code]['font_family'])
            printed = self.families(self.print_serif(code))
            missing = sorted(declared - printed)
            self.assertFalse(
                missing,
                '%s: the print sheet does not name %s, so a PDF ignores it'
                % (code, missing))

    def test_the_print_sheet_names_no_type3_producer(self):
        for code in ('ko', 'ja', 'zh'):
            stack = self.print_serif(code)
            self.assertNotIn('Source Han', stack, code)
            self.assertNotIn('Noto Serif CJK', stack, code)

    def test_japanese_has_a_portable_mincho_in_the_print_sheet(self):
        """The one that closed the gap: static, TrueType, embeds cleanly."""
        self.assertIn('BIZ UDMincho', self.print_serif('ja'))

    def test_the_latin_partner_still_leads_each_cjk_print_stack(self):
        r"""`font-family` resolves per character, so a Latin serif in front
        takes the Latin and the CJK flows past it. Losing that is how the
        embedded English in a Korean book ends up with synthesised italics."""
        for code in ('ko', 'ja', 'zh'):
            self.assertTrue(self.print_serif(code).strip()
                            .startswith("'Noto Serif'"), code)


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
