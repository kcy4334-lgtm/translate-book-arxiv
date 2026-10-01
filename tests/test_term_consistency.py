# -*- coding: utf-8 -*-
"""One term, one word — and one word, one job.

`check_doublets` already caught one English term rendered two ways. These are
the two neighbours it does not cover, both of which shipped in AlphaQ and
CafeQ and were invisible to every other check: the placeholders were intact,
the counts agreed, and the prose was fluent.

  check_term_drift    "절단 멱법칙" on one page, "절단된 멱법칙" on another.
  check_homographs    적합 meaning "fit", "suitable" and "overfit" at once,
                      so a reader met the word twice two paragraphs apart and
                      had to work out that it had changed meaning.

The second one is a POINTER, not a verdict — it compares the source for both
senses against the output for the word, which cannot tell a real collision
from a paper that merely contains both English words. These tests pin that
limit down deliberately, so nobody later mistakes it for proof.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import consistency_probe as cp                                   # noqa: E402


class TermDriftTests(unittest.TestCase):
    """The same term spelled two ways, anchored on glossary head nouns."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="drift_")
        self.glossary(["멱법칙", "행렬", "양자화"])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def glossary(self, targets):
        data = {"version": 2, "high_frequency_top_n": 20,
                "applied_meta_hashes": {},
                "terms": [{"id": t, "source": t, "target": t,
                           "category": "concept", "aliases": [],
                           "gender": "unknown", "confidence": "medium",
                           "frequency": 1, "evidence_refs": [], "notes": ""}
                          for t in targets]}
        with io.open(os.path.join(self.dir, "glossary.json"), "w",
                     encoding="utf-8", newline="") as fh:
            json.dump(data, fh, ensure_ascii=False)

    def drift(self, text):
        return cp.check_term_drift(text, self.dir)

    def test_two_spellings_of_one_term_are_caught(self):
        text = ("ESD 꼬리를 절단 멱법칙 밀도로 모델링한다. "
                "부록에서는 절단된 멱법칙 밀도를 유도한다.")
        found = self.drift(text)
        self.assertEqual(len(found), 1)
        self.assertIn("절단 멱법칙", found[0])
        self.assertIn("절단된 멱법칙", found[0])

    def test_one_spelling_used_throughout_is_silent(self):
        text = ("ESD 꼬리를 절단된 멱법칙 밀도로 모델링한다. "
                "부록에서도 절단된 멱법칙 밀도를 유도한다.")
        self.assertEqual(self.drift(text), [])

    def test_a_head_noun_the_glossary_does_not_know_is_ignored(self):
        # Without this restriction, ordinary Korean fires constantly.
        text = "제안 방식을 쓴다. 제안된 방식을 쓴다."
        self.assertEqual(self.drift(text), [])

    def test_a_connective_stem_is_not_a_term(self):
        # "캘리브레이션 기반 양자화" (X-based) and "반올림에 기반한 양자화"
        # (based on X) are different constructions, not one term twice.
        text = ("캘리브레이션 기반 양자화 방법과 비교한다. "
                "최근접 반올림에 기반한 양자화 체계를 쓴다.")
        self.assertEqual(self.drift(text), [])

    def test_no_glossary_means_no_answer(self):
        empty = tempfile.mkdtemp(prefix="drift_none_")
        try:
            text = "절단 멱법칙과 절단된 멱법칙을 함께 쓴다."
            self.assertEqual(cp.check_term_drift(text, empty), [])
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class HomographTests(unittest.TestCase):
    """A word doing two jobs — reported for a human, never asserted."""

    def test_a_word_covering_two_senses_is_surfaced(self):
        merged = ("지표가 더 적합하다. 꼬리 적합에 사용하는 고윳값을 정렬한다. "
                  "피팅한 멱법칙 지수를 쓴다.")
        source = ("this metric is more suitable here. "
                  "the eigenvalues used for the tail fitting are sorted.")
        found = cp.check_homographs(merged, source, "ko")
        self.assertEqual(len(found), 1)
        self.assertIn("적합", found[0])
        self.assertIn("fit", found[0])
        self.assertIn("suitable", found[0])

    def test_overfitting_alone_does_not_count_as_a_use(self):
        # 과적합 contains 적합 but is a settled, unambiguous word.
        merged = "캘리브레이션 도메인에 과적합되어 성능이 떨어진다. 과적합 위험이 있다."
        source = "the model overfits the calibration domain and is suitable."
        self.assertEqual(cp.check_homographs(merged, source, "ko"), [])

    def test_one_sense_in_the_source_is_silent(self):
        merged = "지표가 더 적합하다. 이 방법이 더 적합하다."
        source = "this metric is more suitable. this method is more suitable."
        self.assertEqual(cp.check_homographs(merged, source, "ko"), [])

    def test_a_latin_target_language_is_not_checked(self):
        self.assertEqual(cp.check_homographs("fit and suitable", "fit", "en"),
                         [])

    def test_it_cannot_prove_a_collision_and_must_not_fail_a_build(self):
        # The known limit, pinned so nobody promotes this to a hard failure:
        # every use here means "sorted", but the paper contains "aligned"
        # elsewhere, so the check still fires. That is why the probe reports
        # it instead of failing on it.
        merged = "고윳값을 오름차순으로 정렬한다. 다시 오름차순으로 정렬한다."
        source = ("eigenvalues are sorted in ascending order. "
                  "the spikes are aligned with the labels.")
        self.assertTrue(cp.check_homographs(merged, source, "ko"),
                        "this false positive is expected and is the reason "
                        "the finding is reported rather than failed on")

    def test_the_probe_does_not_fail_on_a_homograph(self):
        with io.open(os.path.join(HERE, "consistency_probe.py"),
                     encoding="utf-8") as fh:
            source = fh.read()
        at = source.index("homographs = check_homographs")
        window = source[at:at + 900]
        self.assertNotIn("fails.append", window,
                         "check_homographs cannot prove a collision, so it "
                         "must not fail the probe")


class DoubledLabelTests(unittest.TestCase):
    """A label followed by a particle is still a doubled label.

    `3.2절 절을 따라` shipped in a build whose consistency probe reported zero
    doubled labels: the check ended in `(?![가-힣])`, and Korean attaches a
    particle to almost every noun, so the ordinary case was the invisible
    one. The guard cannot simply be dropped — 표 is also the first syllable
    of 표현, 표시, 표준.
    """

    def doubled(self, text):
        html = "<html><body><p>%s</p></body></html>" % text
        return [kind for kind, _hit, _ctx in cp.check_doubled_labels(html, "ko")
                if kind == "doubled"]

    def test_a_doubled_label_with_a_particle_is_caught(self):
        self.assertTrue(self.doubled("3.2절 절을 따라 모델링한다"),
                        "the case that actually shipped")

    def test_every_common_particle(self):
        for particle in ("을", "은", "이", "에", "에서", "으로", "과", "의"):
            self.assertTrue(self.doubled("그림 그림%s 나타난다" % particle),
                            "particle %s hides the doubling" % particle)

    def test_a_doubled_label_with_no_particle_is_still_caught(self):
        self.assertTrue(self.doubled("식 식 (5)에서"))

    def test_a_label_that_starts_a_longer_word_is_not_doubled(self):
        # 표 is also the first syllable of 표현 / 표시 / 표준.
        for word in ("표현을", "표시가", "표준을"):
            self.assertFalse(self.doubled("표 %s 따른다" % word),
                             "%s is a different word, not a second label" % word)

    def test_an_ordinary_reference_is_not_doubled(self):
        for text in ("표 3의 값을 보면", "그림 4는 이를 보여준다",
                     "부록 A.8에 제시한다", "식 (7)에서 유도한다"):
            self.assertFalse(self.doubled(text), text)


if __name__ == "__main__":
    unittest.main()
