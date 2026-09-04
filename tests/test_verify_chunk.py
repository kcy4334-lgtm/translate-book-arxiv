# -*- coding: utf-8 -*-
"""Every check must be able to fail, and must not fail on a good chunk.

Half of these tests break something and require the check to notice; the
other half hand it correct work and require silence. Both halves are the
point. `check_neighbor_leak` read the wrong dictionary keys and could never
have found anything -- it passed every book it was ever run on, and only a
test that demanded a catch exposed it.

Fixtures are synthetic and stdlib-only so CI can run them. The same checks
are calibrated against three real books separately; see KNOWLEDGE K70.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import verify_chunk as vc                                        # noqa: E402

KO = ("이 절에서는 제안한 방법의 성능을 여러 벤치마크에서 평가하고, "
      "각 설정에 대한 정확도를 보고한다. 실험 결과는 제안 기법이 기존 "
      "방식보다 일관되게 우수함을 보여준다.\n")
EN = ("This section evaluates the performance of the proposed method on "
      "several benchmarks and reports the accuracy for each configuration "
      "considered in the study.\n")


class ChunkCase(unittest.TestCase):
    """One source chunk, one translation, in a throwaway directory."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="verify_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def pair(self, source, output, chunk="chunk0002"):
        self.write(chunk + ".md", source)
        self.write("output_%s.md" % chunk, output)
        return chunk + ".md"

    def checks(self, source, output, chunk="chunk0002", lang="ko"):
        name = self.pair(source, output, chunk)
        result = vc.verify_chunk(self.dir, name, lang)
        return sorted({f["check"] for f in result["findings"]
                       if f["severity"] == "fail"}), result


class GoodWorkIsSilent(ChunkCase):

    def test_a_plain_translation_passes(self):
        checks, result = self.checks(EN, KO)
        self.assertEqual(checks, [])
        self.assertTrue(result["ok"])

    def test_latin_names_and_numbers_are_not_a_failure(self):
        source = "The Qwen3-1.7B model reaches 62.4 on MMLU.\n"
        output = "Qwen3-1.7B 모델은 MMLU에서 62.4를 기록한다.\n"
        self.assertEqual(self.checks(source, output)[0], [])

    def test_a_bibliography_may_stay_in_the_source_language(self):
        bib = ("## References\n\n"
               "Dettmers, Tim, and Luke Zettlemoyer. 2023. “Qlora: "
               "Efficient Finetuning of Quantized Llms.” In *Advances in "
               "Neural Information Processing Systems*.\n\n"
               "Lin, Ji, and Haotian Tang. 2024. “Awq: Activation-Aware "
               "Weight Quantization.” In *Proceedings of MLSys*.\n")
        self.assertEqual(self.checks(bib, bib)[0], [])

    def test_a_chunk_that_is_only_references_may_come_back_unchanged(self):
        bib = "".join(
            "Author%d, First. 202%d. “A Paper Title Here.” In "
            "*Proceedings of the Conference on Machine Learning*, pp. 1-9.\n\n"
            % (i, i % 10) for i in range(8))
        self.assertEqual(self.checks(bib, bib)[0], [])

    def test_an_unresolved_label_is_machinery_not_prose(self):
        # The merge turns (app:pattern) into "Appendix A.1" from flat.tex.
        source = "as shown in Appendix (app:activation_pattern).\n"
        output = "부록 (app:activation_pattern)에서 보인 바와 같다.\n"
        self.assertEqual(self.checks(source, output)[0], [])


class BrokenWorkIsCaught(ChunkCase):

    def test_output_identical_to_source(self):
        self.assertIn("untranslated", self.checks(EN * 4, EN * 4)[0])

    def test_output_still_in_the_source_language(self):
        self.assertIn("target_language", self.checks(EN * 4, EN * 4 + "x")[0])

    def test_one_paragraph_never_translated(self):
        long_en = ("We evaluate the proposed approach on a wide range of "
                   "standard benchmarks and report the resulting accuracy "
                   "for every configuration.\n")
        self.assertIn("untranslated_block",
                      self.checks(EN + long_en, KO + "\n" + long_en)[0])

    def test_a_dropped_placeholder(self):
        source = "The result is ⟦M0007⟧ for every model.\n"
        output = "결과는 모든 모델에서 동일하다.\n"
        self.assertIn("placeholders", self.checks(source, output)[0])

    def test_a_duplicated_placeholder(self):
        source = "The result is ⟦M0007⟧ here.\n"
        output = "결과는 ⟦M0007⟧ 이며 ⟦M0007⟧ 이다.\n"
        self.assertIn("placeholders", self.checks(source, output)[0])

    def test_an_invented_placeholder(self):
        source = "The result is ⟦M0007⟧ here.\n"
        output = "결과는 ⟦M0007⟧ 이고 ⟦M9999⟧ 이다.\n"
        self.assertIn("placeholders", self.checks(source, output)[0])

    def test_a_dropped_image(self):
        source = "![Figure 1](media/image-001.png)\n\n" + EN
        self.assertIn("images", self.checks(source, KO)[0])

    def test_a_dropped_html_image(self):
        source = '<img src="media/a.png" alt="x" />\n\n' + EN
        self.assertIn("images", self.checks(source, KO)[0])

    def test_a_message_to_the_reader_at_the_top(self):
        self.assertIn("commentary",
                      self.checks(EN, "Here is the translation:\n\n" + KO)[0])

    def test_a_note_to_the_reader_at_the_bottom(self):
        self.assertIn("commentary",
                      self.checks(EN, KO + "\nNote: I hope this helps!\n")[0])

    def test_the_whole_file_wrapped_in_a_fence(self):
        self.assertIn("commentary",
                      self.checks(EN, "```markdown\n" + KO + "```\n")[0])

    def test_an_unclosed_code_fence(self):
        self.assertIn("fences", self.checks(EN, KO + "\n```python\nx = 1\n")[0])

    def test_a_lost_table_row(self):
        source = ("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n" + EN)
        output = ("| 가 | 나 |\n|---|---|\n| 1 | 2 |\n\n" + KO)
        self.assertIn("structure", self.checks(source, output)[0])

    def test_a_truncated_translation(self):
        self.assertIn("length", self.checks(EN * 6, KO[:20])[0])

    def test_a_fabricated_evidence_quote(self):
        name = self.pair(EN, KO)
        meta = {"schema_version": 1,
                "new_entities": [{"source": "Zephyr",
                                  "target_proposal": "제퍼",
                                  "category": "model",
                                  "evidence": "Zephyr beat every baseline "
                                              "in the ablation study"}],
                "alias_hypotheses": [], "attribute_hypotheses": [],
                "used_term_sources": [], "conflicts": []}
        self.write("output_chunk0002.meta.json",
                   json.dumps(meta, ensure_ascii=False))
        result = vc.verify_chunk(self.dir, name, "ko")
        self.assertIn("meta_evidence",
                      [f["check"] for f in result["findings"]])

    def test_a_real_evidence_quote_is_accepted(self):
        name = self.pair("Zephyr beat every baseline here.\n" + EN, KO)
        meta = {"schema_version": 1,
                "new_entities": [{"source": "Zephyr",
                                  "target_proposal": "제퍼",
                                  "category": "model",
                                  "evidence": "Zephyr beat every baseline"}],
                "alias_hypotheses": [], "attribute_hypotheses": [],
                "used_term_sources": [], "conflicts": []}
        self.write("output_chunk0002.meta.json",
                   json.dumps(meta, ensure_ascii=False))
        result = vc.verify_chunk(self.dir, name, "ko")
        self.assertNotIn("meta_evidence",
                         [f["check"] for f in result["findings"]])

    def test_meta_that_asserts_its_own_chunk_id(self):
        name = self.pair(EN, KO)
        self.write("output_chunk0002.meta.json",
                   json.dumps({"schema_version": 1, "chunk_id": "chunk0002"}))
        result = vc.verify_chunk(self.dir, name, "ko")
        self.assertIn("meta", [f["check"] for f in result["findings"]])

    def test_meta_that_is_not_json(self):
        name = self.pair(EN, KO)
        self.write("output_chunk0002.meta.json", '{"schema_version": 1,')
        result = vc.verify_chunk(self.dir, name, "ko")
        self.assertIn("meta", [f["check"] for f in result["findings"]])

    def test_a_missing_translation(self):
        self.write("chunk0002.md", EN)
        result = vc.verify_chunk(self.dir, "chunk0002.md", "ko")
        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["check"], "output")

    def test_a_blank_translation(self):
        name = self.pair(EN, "   \n\n")
        result = vc.verify_chunk(self.dir, name, "ko")
        self.assertFalse(result["ok"])


class ReferenceExemptionTests(ChunkCase):
    """The exemption must cover references and stop there.

    It used to be a POSITION: everything after the first place the text
    looked citation-dense was exempt from the language checks. In a chunk of
    prose followed by a long reference list that place is line 0, so AlphaQ's
    entire "Limitation" section could have come back in English and this file
    would have reported nothing. Measured, not supposed. It is now decided
    line by line, and by the LaTeX environment where there is one.
    """

    LIMITATION = (
        "## Limitation\n\n"
        "This work still has several limitations that we now describe.\n\n"
        "First, our experiments are restricted to weight-only quantization "
        "and extending them would require broader validation.\n\n"
        "Second, AlphaQ relies on the degree of heavy-tailedness as a proxy "
        "for importance, following Martin and Mahoney 2019.\n\n"
    )
    ENTRIES = "".join(
        "Author%d, First, Second Author, and Third Author. 202%d. "
        "\u201cA Paper Title.\u201d In *Proceedings of the Conference*, pp. 1-9.\n\n"
        % (i, i % 10) for i in range(12))

    def test_prose_before_a_bibliography_is_still_checked(self):
        source = self.LIMITATION + self.ENTRIES
        checks, _ = self.checks(source, source)
        self.assertIn("untranslated_block", checks,
                      "the prose ahead of the reference list must not inherit "
                      "the list's exemption")

    def test_the_same_chunk_translated_passes(self):
        translated = (KO + "\n\n") * 3 + self.ENTRIES
        self.assertEqual(self.checks(self.LIMITATION + self.ENTRIES,
                                     translated)[0], [])

    def test_a_footnote_is_prose_that_happens_to_cite(self):
        source = ("[^1]: We emphasize that the term calibration-free applies "
                  "only to the bit allocation stage, following the setup of "
                  "Gholami et al. 2021 and the discussion there.\n") * 4
        checks, _ = self.checks(source, source)
        self.assertIn("untranslated_block", checks,
                      "a footnote carries a year and 'et al.' but is content")

    def test_a_latex_bibliography_environment_is_exempt_whole(self):
        # Its author lines read "Tom Brown, Benjamin Mann" -- first name
        # first -- so no surname heuristic matches them. The environment
        # delimiter is exact, and is what decides here.
        bib = ("\\begin{thebibliography}{29}\n"
               "\\providecommand{\\natexlab}[1]{#1}\n"
               + "".join(
                   "\\bibitem[Brown et~al.(2020)]{brown2020}\n"
                   "Tom Brown, Benjamin Mann, Nick Ryder, and Melanie Subbiah.\n"
                   "\\newblock Language models are few-shot learners.\n" for _ in range(6))
               + "\\end{thebibliography}\n")
        self.assertEqual(self.checks(bib, bib)[0], [],
                         "a raw-LaTeX bibliography returned unchanged is the "
                         "correct answer, not an untranslated chunk")

    def test_prose_after_a_latex_bibliography_is_still_checked(self):
        bib = ("\\begin{thebibliography}{2}\n"
               "\\bibitem[A(2020)]{a}\n\\newblock A title.\n"
               "\\end{thebibliography}\n\n")
        source = bib + self.LIMITATION
        self.assertIn("untranslated_block", self.checks(source, source)[0])

class YearShapeTests(ChunkCase):
    """What counts as a date on a reference line."""

    def is_ref(self, line):
        return vc._is_reference_line(line)

    def test_a_plain_year(self):
        self.assertTrue(self.is_ref('Hu, Xing, and Zhixuan Chen. 2025. '
                                    '\u201cMoEQuant.\u201d In *Proceedings*.'))

    def test_a_disambiguated_year(self):
        # One author, two papers, one year: 2024a and 2024b.
        for suffix in ('a', 'b', 'c'):
            self.assertTrue(
                self.is_ref('Team, Qwen. 2024%s. *Introducing Qwen1.5*.' % suffix),
                'a disambiguated year is still a year')

    def test_no_date_at_all_is_not_a_reference(self):
        self.assertFalse(self.is_ref('Second, AlphaQ relies on the degree of '
                                     'heavy-tailedness in weight spectra.'))

    def test_a_sentence_that_merely_cites_is_not_a_reference(self):
        # Same shape as an author list, and a year later in the line.
        self.assertFalse(self.is_ref('However, AlphaQ follows the setup of '
                                     'Martin and Mahoney 2019 throughout.'))

    def test_two_disambiguated_entries_are_all_references(self):
        chunk = ('Team, Qwen. 2024a. *Introducing Qwen1.5*. '
                 '<https://example.invalid/a>.\n\n'
                 'Team, Qwen. 2024b. *Qwen1.5-MoE: Matching 7B Performance*. '
                 '<https://example.invalid/b>.\n\n'
                 'Team, Qwen. 2024c. *Qwen2 Technical Report*. '
                 '<https://example.invalid/c>.\n')
        self.assertTrue(vc.is_all_references(chunk),
                        'a chunk of nothing but entries must be exempt, or it '
                        'gets dispatched to a translator')


class NothingToTranslateTests(unittest.TestCase):
    """Identical output is a defect only where there was a word to render.

    VLA-Adapter's last chunk is three footnote definitions holding one bare
    URL each. `untranslated` failed it and asked for a re-translation that
    could only produce the same bytes and fail again.
    """

    FOOTNOTES = ('[^1]: <https://example.invalid/datasets>\n\n'
                 '[^2]: <http://example.invalid/>\n\n'
                 '[^3]: <https://example.invalid/a/b/c.py>\n')

    def test_footnote_definitions_holding_only_urls_are_exempt(self):
        self.assertTrue(vc.has_nothing_to_translate(self.FOOTNOTES))
        self.assertEqual(
            vc.check_translated(self.FOOTNOTES, self.FOOTNOTES, 'ko'), [],
            'a chunk with no word in it can only come back identical')

    def test_a_footnote_carrying_prose_is_not_exempt(self):
        """The exemption is about words, not about the footnote syntax."""
        chunk = '[^1]: The benchmark suite is described in the appendix.\n'
        self.assertFalse(vc.has_nothing_to_translate(chunk))
        self.assertTrue(vc.check_translated(chunk, chunk, 'ko'),
                        'prose left untranslated must still fail')

    def test_ordinary_prose_is_not_exempt(self):
        chunk = 'The policy network receives the action latent.\n'
        self.assertFalse(vc.has_nothing_to_translate(chunk))
        self.assertTrue(vc.check_translated(chunk, chunk, 'ko'))

    def test_digits_and_symbols_alone_are_not_words(self):
        self.assertTrue(vc.has_nothing_to_translate('224 x 224\n\n1. 2. 3.\n'))


class NeighborLeakTests(ChunkCase):
    """Read-only context, pasted into the output as if it were content."""

    def build(self, tail):
        self.write("chunk0001.md", "A" * 200 + tail)
        self.write("chunk0002.md", EN)
        self.write("chunk0003.md", EN)
        self.write("output_chunk0002.md", KO + tail)
        return vc.verify_chunk(self.dir, "chunk0002.md", "ko")

    def test_the_previous_excerpt_copied_in_is_caught(self):
        tail = ("\n\n이전 청크의 마지막 문장이며 번역자가 그대로 붙여 넣은 "
                "읽기 전용 맥락 문장이다. 여기에 충분한 길이의 내용이 있다.\n")
        result = self.build(tail)
        self.assertIn("neighbor_leak",
                      [f["check"] for f in result["findings"]])

    def test_a_chunk_that_did_not_copy_it_is_silent(self):
        self.write("chunk0001.md", "A" * 200 + "\n\n이전 청크의 고유한 마지막 문장.\n")
        self.write("chunk0002.md", EN)
        self.write("output_chunk0002.md", KO)
        result = vc.verify_chunk(self.dir, "chunk0002.md", "ko")
        self.assertNotIn("neighbor_leak",
                         [f["check"] for f in result["findings"]])

    def test_the_context_keys_are_the_ones_the_provider_writes(self):
        # The bug this locks: reading 'previous'/'next' instead of
        # prev_excerpt/next_excerpt made the check incapable of failing.
        import chunk_context
        self.write("chunk0001.md", "A" * 100)
        self.write("chunk0002.md", EN)
        keys = chunk_context.get_neighbor_context(self.dir, "chunk0002.md")
        self.assertIn("prev_excerpt", keys)
        self.assertIn("next_excerpt", keys)
        with io.open(os.path.join(os.path.dirname(HERE), "scripts",
                                  "verify_chunk.py"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("prev_excerpt", source)
        self.assertIn("next_excerpt", source)


class GlossaryComplianceTests(ChunkCase):

    def glossary(self, source, target):
        self.write("glossary.json", json.dumps({
            "version": 2,
            "terms": [{"id": source, "source": source, "target": target,
                       "category": "term", "aliases": [], "gender": "unknown",
                       "confidence": "medium", "frequency": 3,
                       "evidence_refs": [], "notes": ""}],
            "high_frequency_top_n": 20, "applied_meta_hashes": {}},
            ensure_ascii=False))

    def test_a_term_left_in_the_source_language_is_caught(self):
        self.glossary("quantization", "양자화")
        source = "We apply quantization to every layer of the model here.\n"
        output = "우리는 모델의 모든 레이어에 quantization 을 적용한다.\n"
        self.assertIn("glossary", self.checks(source, output)[0])

    def test_the_agreed_translation_passes(self):
        self.glossary("quantization", "양자화")
        source = "We apply quantization to every layer of the model here.\n"
        output = "우리는 모델의 모든 레이어에 양자화를 적용한다.\n"
        self.assertEqual(self.checks(source, output)[0], [])

    def test_a_term_inside_code_is_not_a_violation(self):
        self.glossary("quantization", "양자화")
        source = "Call `quantization` on the tensor to apply it here.\n"
        output = "텐서에 `quantization` 을 호출하여 양자화를 적용한다.\n"
        self.assertEqual(self.checks(source, output)[0], [])


if __name__ == "__main__":
    unittest.main()
