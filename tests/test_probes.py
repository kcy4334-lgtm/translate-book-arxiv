"""The probes' judgement calls, tested without a built book.

A probe that cries wolf gets ignored, and an ignored probe is worse than no
probe: it costs a run and buys nothing. Every case below is one the probes got
wrong on a real paper and now get right, so the reasons are worth keeping.

Only the pure helpers are exercised. Anything needing pymupdf or a temp dir
stays out, because CI runs the suite on stdlib alone.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
for extra in (TESTS_DIR, TESTS_DIR.parent / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import consistency_probe  # noqa: E402
import dry_run  # noqa: E402
import format_probe  # noqa: E402
import source_probe  # noqa: E402


class AcronymTests(unittest.TestCase):
    """`사후 학습 양자화(PTQ)` beside `사후 학습 양자화(post-training
    quantization)` is ordinary practice: gloss the expansion once, the
    acronym thereafter. Reported as a collision it buries the real ones."""

    def test_initials_match_the_expansion(self):
        self.assertTrue(consistency_probe._is_acronym_of(
            "PTQ", "post-training quantization"))

    def test_prefix_of_the_initials_counts(self):
        self.assertTrue(consistency_probe._is_acronym_of(
            "MoE", "mixture of experts layer"))

    def test_unrelated_words_are_not_an_acronym_pair(self):
        self.assertFalse(consistency_probe._is_acronym_of(
            "PTQ", "quantization aware training"))

    def test_lowercase_is_not_an_acronym(self):
        self.assertFalse(consistency_probe._is_acronym_of(
            "ptq", "post-training quantization"))

    def test_long_words_are_not_acronyms(self):
        self.assertFalse(consistency_probe._is_acronym_of(
            "QUANTIZATION", "quantization"))


class SameTermTests(unittest.TestCase):
    """The gloss pattern also catches the words in front of the term, so
    `종단 간`, `에서의 종단 간` and `형식의 종단 간` are one term seen three
    times -- not three different renderings of it."""

    def test_suffix_consistent_candidates_are_one_term(self):
        self.assertTrue(consistency_probe._same_term(
            ["종단 간", "에서의 종단 간", "형식의 종단 간"]))

    def test_genuinely_different_terms_are_not(self):
        self.assertFalse(consistency_probe._same_term(["레이어", "계층"]))

    def test_a_single_candidate_is_trivially_one_term(self):
        self.assertTrue(consistency_probe._same_term(["레이어"]))


class ProbeContextTests(unittest.TestCase):
    """source_probe locates a cross-reference by the words in front of it.
    `is provided in Appendix` occurs a dozen times in one paper, and matching
    the first hit reported a mismatch the paper does not have -- which is why
    the probe now insists the context land in exactly one place."""

    def test_longest_prose_run_is_chosen(self):
        caption = ("\\textbf{Bit allocation.} "
                   "Distribution of quantization times for each method")
        probe = source_probe.probe_of(caption)
        self.assertIn("Distribution of quantization times", probe)

    def test_a_caption_of_pure_math_has_no_probe(self):
        self.assertIsNone(source_probe.probe_of("$x_1$ $y_2$"))

    def test_equation_markers_are_recognised(self):
        self.assertTrue(source_probe._EQ_MARKER_RE.match("(12)"))
        self.assertFalse(source_probe._EQ_MARKER_RE.match("(a)"))
        self.assertFalse(source_probe._EQ_MARKER_RE.match("see (12) there"))


class TargetScriptTests(unittest.TestCase):
    """A heading of one token is a name the paper itself uses -- AlphaQ, SINQ
    -- and translating it would be wrong. Only a multi-word English heading is
    a heading the translator skipped."""

    def test_hangul_counts_as_korean(self):
        self.assertTrue(consistency_probe.in_target_script("양자화 방법", "ko"))

    def test_plain_english_does_not(self):
        self.assertFalse(consistency_probe.in_target_script(
            "Experimental Setup", "ko"))

    def test_a_gloss_still_counts_as_translated(self):
        self.assertTrue(consistency_probe.in_target_script(
            "양자화(quantization)", "ko"))


class CollapsedTableTests(unittest.TestCase):
    """pandoc lays grid and simple tables out by DISPLAY width, where a Hangul
    syllable is two columns. Translate a cell and pad it to the same character
    count -- the obvious thing to do -- and the separators no longer meet the
    rule, so pandoc abandons the table and emits one cell per line with the
    pipes still in it. It is still a <table> with rows and cells, so every
    count the format probe already made came out right while the reader saw
    `방법 | UNIFORM | RANDOM | ...` as one run of text."""

    def fires(self, cell):
        return bool(format_probe._MARKUP_IN_CELL_RE.search(cell))

    def test_a_collapsed_row_is_caught(self):
        self.assertTrue(self.fires("방법 | UNIFORM | RANDOM | 학습된 블록 대각"))

    def test_a_grid_border_left_in_a_cell_is_caught(self):
        self.assertTrue(self.fires("+:====:+:====:+ 양자화 미적용 | 48.0"))

    def test_an_ordinary_cell_is_not(self):
        self.assertFalse(self.fires("평균 상대 손실"))
        self.assertFalse(self.fires("0.176"))

    def test_a_norm_in_a_cell_is_not_a_collapsed_table(self):
        """`|W|` and `∥M∥` are ordinary content, not table markup."""
        self.assertFalse(self.fires("|W|"))
        self.assertFalse(self.fires("error |x - y|"))

    def test_a_dash_run_is_only_markup_at_the_start(self):
        self.assertFalse(self.fires("well-known trade-off"))


class TruncationTests(unittest.TestCase):
    """A sub-agent that stops early loses whole paragraphs, and every other
    check still passes: the placeholders it did copy balance, the headings it
    did reach ladder correctly. Only the bulk gives it away."""

    def test_half_length_is_flagged(self):
        self.assertTrue(consistency_probe.looks_truncated(4000, 1200))

    def test_ordinary_korean_compression_is_not(self):
        """The lowest real chunk across three papers came in at 0.52."""
        self.assertFalse(consistency_probe.looks_truncated(4000, 2080))
        self.assertFalse(consistency_probe.looks_truncated(4000, 2600))

    def test_a_short_chunk_is_exempt(self):
        """A heading and two sentences can legitimately halve."""
        self.assertFalse(consistency_probe.looks_truncated(400, 100))

    def test_an_empty_translation_is_flagged(self):
        self.assertTrue(consistency_probe.looks_truncated(4000, 0))


if __name__ == "__main__":
    unittest.main()


class FormatParityTests(unittest.TestCase):
    """Comparing each format against zero is what let nine of AlphaQ's twelve
    tables sit in the Word file as plain text: three is not zero, so nothing
    complained, and the HTML had all twelve so every other count agreed with
    itself. The formats have to be compared against each other."""

    def test_the_alphaq_case_is_caught(self):
        """3 tables in the DOCX against 12 in the ebook HTML."""
        self.assertTrue(format_probe.short_of_reference(3, 12))

    def test_ordinary_writer_drift_is_not(self):
        """181 equations against 203: a DOCX renders some inline maths as
        text, and that is not a dropped feature."""
        self.assertFalse(format_probe.short_of_reference(181, 203))

    def test_full_parity_passes(self):
        self.assertFalse(format_probe.short_of_reference(12, 12))

    def test_nothing_at_all_is_caught(self):
        self.assertTrue(format_probe.short_of_reference(0, 12))

    def test_a_reference_of_zero_asks_nothing(self):
        """A paper with no tables must not fail for having none."""
        self.assertFalse(format_probe.short_of_reference(0, 0))

    def test_a_format_that_cannot_report_is_skipped(self):
        """The PDF has no countable <table>; None means 'no answer'."""
        self.assertFalse(format_probe.short_of_reference(None, 12))


class BrokenMathTests(unittest.TestCase):
    r"""A formula that renders to nothing still counts as a formula
    everywhere else: the <math> element is there, its <annotation> is there,
    and every parity check between the formats agrees. SINQ's
    `\textbf{Overhead [\%]}` was read back as display maths holding one `%`
    and drew nothing, so the column header said "오버헤드" and stopped."""

    EMPTY = ('<math display="block"><semantics><mrow></mrow>'
             '<annotation encoding="application/x-tex">%</annotation>'
             '</semantics></math>')
    REAL = ('<math><semantics><mrow><mi>x</mi></mrow>'
            '<annotation encoding="application/x-tex">x</annotation>'
            '</semantics></math>')

    def test_an_empty_formula_is_caught(self):
        blank, errors = consistency_probe.check_broken_math(self.EMPTY)
        self.assertEqual((blank, errors), (1, 0))

    def test_a_real_formula_is_not(self):
        blank, _e = consistency_probe.check_broken_math(self.REAL)
        self.assertEqual(blank, 0)

    def test_the_annotation_alone_does_not_count_as_rendering(self):
        """The TeX inside <annotation> is never shown; only the markup is."""
        blank, _e = consistency_probe.check_broken_math(self.EMPTY + self.REAL)
        self.assertEqual(blank, 1)

    def test_merror_is_reported(self):
        _b, errors = consistency_probe.check_broken_math(
            '<math><merror><mtext>bad</mtext></merror></math>')
        self.assertEqual(errors, 1)

    def test_a_document_with_no_maths_is_clean(self):
        self.assertEqual(consistency_probe.check_broken_math('<p>text</p>'),
                         (0, 0))


class SourceSanityTests(unittest.TestCase):
    """A translator renders a broken sentence faithfully and the reader blames
    the translation. CafeQ's published PDF reads "...particularly in the
    attention modules. which in contrast, aims to quantize an already-trained
    model", so the Korean inherits a pronoun with no antecedent."""

    def check(self, text):
        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, "input.md")).write_text(text, encoding="utf-8")
            return dry_run.source_sanity(d)

    def test_a_relative_pronoun_cannot_open_a_sentence(self):
        found = self.check(
            "It does not use the attention modules. which in contrast, aims "
            "to quantize an already-trained model with no retraining.")
        self.assertEqual(len(found), 1)

    def test_it_is_caught_at_a_paragraph_break_too(self):
        """pandoc can put a list between the two halves."""
        found = self.check(
            "It does not use the attention modules.\n\n"
            "which in contrast, aims to quantize an already-trained model.")
        self.assertEqual(len(found), 1)

    def test_a_subordinating_conjunction_opens_a_sentence_fine(self):
        for opener in ("While", "Since", "Because", "Although"):
            found = self.check(
                "We measured the error. %s the scale is fixed, the bound "
                "holds for every layer in the network." % opener)
            self.assertEqual(found, [], opener)

    def test_an_ordinary_relative_clause_is_not_flagged(self):
        found = self.check(
            "We use the scale, which is fixed for every layer in the network.")
        self.assertEqual(found, [])

    def test_maths_is_not_read_as_prose(self):
        found = self.check("The bound is $x. which > y$ holds here always.")
        self.assertEqual(found, [])
