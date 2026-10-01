"""Tests for math/citation placeholdering.

Each case here corresponds to a defect that was measured on real papers:
pandoc's LaTeX reader eating `\\\\` row separators, `\\label` removal leaving a
blank line that terminates `$$` math, tokens nested inside another token's
stored LaTeX, and translators dropping or duplicating a placeholder.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import math_guard  # noqa: E402

BS = chr(92)


class ProtectRestoreTests(unittest.TestCase):
    def test_inline_math_round_trip(self):
        src = r'The value $\alpha_i$ matters.'
        protected, spans = math_guard.protect(src)
        self.assertNotIn('$', protected)
        self.assertEqual(len(spans), 1)
        self.assertEqual(math_guard.restore(protected, spans), src)

    def test_display_math_round_trip(self):
        src = 'Before\n\n$$x = y$$\n\nAfter'
        protected, spans = math_guard.protect(src)
        self.assertNotIn('$', protected)
        self.assertEqual(math_guard.restore(protected, spans), src)

    def test_citation_is_protected(self):
        src = 'As shown [@smith2020; @jones2021] earlier.'
        protected, spans = math_guard.protect(src)
        self.assertNotIn('@smith2020', protected)
        self.assertEqual(math_guard.restore(protected, spans), src)

    def test_currency_is_not_treated_as_math(self):
        # `$5 and $6` must not be read as one formula.
        src = 'It costs $5 and $6 each.'
        protected, spans = math_guard.protect(src)
        self.assertEqual(spans, [])
        self.assertEqual(protected, src)

    def test_math_inside_code_is_left_alone(self):
        src = 'Run `echo $HOME` and `cost=$5`.'
        protected, spans = math_guard.protect(src)
        self.assertEqual(spans, [])
        self.assertEqual(protected, src)

    def test_nested_tokens_are_restored(self):
        r"""pandoc emits `$$\begin{align}...\end{align}$$`, so the environment
        token ends up nested inside the `$$...$$` token's stored LaTeX."""
        src = '$$\\begin{align}\na &= b\n\\end{align}$$'
        protected, spans = math_guard.protect(src)
        self.assertNotIn('$', protected)
        needed = math_guard.spans_for_chunk(protected, spans)
        # the outer token plus the nested inner one
        self.assertGreaterEqual(len(needed), 2)
        restored = math_guard.restore(protected, needed)
        self.assertNotIn('\u27e6', restored)
        self.assertIn(r'\begin{align}', restored)

    def test_restore_is_idempotent(self):
        src = r'Value $x$ here.'
        protected, spans = math_guard.protect(src)
        once = math_guard.restore(protected, spans)
        self.assertEqual(math_guard.restore(once, spans), once)


class RepairDisplayMathTests(unittest.TestCase):
    def test_restores_eaten_row_separator(self):
        r"""pandoc's LaTeX reader turns `a &= b \\` into `a &= b \`."""
        eaten = 'a &= b \\\nc &= d'
        fixed = math_guard.repair_display_math(eaten)
        self.assertIn('\\\\\n', fixed)

    def test_collapses_blank_line(self):
        """A blank line terminates $$ math in pandoc's markdown reader, and is
        not valid inside a LaTeX math environment either."""
        src = '\\begin{equation}\n\n    x = 1\n\n\\end{equation}'
        fixed = math_guard.repair_display_math(src)
        self.assertNotRegex(fixed, r'\n[ \t]*\n')
        self.assertIn('x = 1', fixed)

    def test_leaves_escaped_backslash_alone(self):
        src = r'a \\\\ b'
        self.assertEqual(math_guard.repair_display_math(src), src)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.src, self.spans = math_guard.protect(r'One $a$ and two $b$.')

    def test_clean_translation_passes(self):
        report = math_guard.verify(self.src, self.src, self.spans)
        self.assertEqual(report['missing'], [])
        self.assertEqual(report['duplicated'], [])
        self.assertEqual(report['foreign'], [])

    def test_detects_dropped_token(self):
        token = self.spans[0]['token']
        broken = self.src.replace(token, '')
        report = math_guard.verify(self.src, broken, self.spans)
        self.assertEqual(report['missing'], [token])

    def test_detects_duplicated_token(self):
        token = self.spans[0]['token']
        broken = self.src.replace(token, token + token)
        report = math_guard.verify(self.src, broken, self.spans)
        self.assertEqual(report['duplicated'], [token])

    def test_detects_invented_token(self):
        broken = self.src + ' \u27e6M9999\u27e7'
        report = math_guard.verify(self.src, broken, self.spans)
        self.assertEqual(report['foreign'], ['\u27e6M9999\u27e7'])


class SidecarTests(unittest.TestCase):
    def test_write_and_load(self):
        _, spans = math_guard.protect(r'A $z$ formula.')
        with tempfile.TemporaryDirectory() as tmp:
            math_guard.write_sidecar(tmp, 'chunk0001.md', spans)
            loaded = math_guard.load_sidecar(tmp, 'chunk0001.md')
            self.assertEqual(loaded, spans)

    def test_missing_sidecar_returns_none(self):
        """None is the 'pre-upgrade temp dir' signal — callers must no-op."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(math_guard.load_sidecar(tmp, 'chunk0001.md'))

    def test_rejects_unknown_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = math_guard.sidecar_path(tmp, 'chunk0001.md')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'version': 999, 'spans': []}, f)
            with self.assertRaises(ValueError):
                math_guard.load_sidecar(tmp, 'chunk0001.md')

    def test_sidecar_name_does_not_collide_with_chunk_glob(self):
        """chunk*.math.json must be invisible to chunk*.md consumers."""
        name = os.path.basename(math_guard.sidecar_path('/tmp', 'chunk0001.md'))
        self.assertFalse(name.endswith('.md'))
        self.assertTrue(name.endswith('.math.json'))


if __name__ == '__main__':
    unittest.main()


class EscapedBracketTests(unittest.TestCase):
    r"""pandoc's markdown writer escapes a literal `[` as `\[`, and our reader
    has tex_math_single_backslash on, so it reads that straight back as
    display maths. SINQ's `\textbf{Overhead [\%]}` -- the units of a column --
    became a display formula holding one `%`, which renders as nothing: the
    header read "오버헤드" and then stopped."""

    def protect(self, text):
        _out, spans = math_guard.protect(text)
        return spans

    def test_a_unit_in_brackets_is_not_a_formula(self):
        for unit in ('%', 'ms', 'GB', 's', '°'):
            self.assertFalse(math_guard.looks_like_math(unit), unit)
            self.assertEqual(self.protect(BS + '[' + unit + BS + ']'), [])

    def test_a_real_formula_still_is_one(self):
        for body in ('x^2 = y', BS + 'frac{a}{b}', '1 + 2', 'a_i', 'x < y'):
            self.assertTrue(math_guard.looks_like_math(body), body)
            self.assertEqual(len(self.protect(BS + '[' + body + BS + ']')), 1)

    def test_dollar_display_math_is_untouched_by_the_rule(self):
        r"""The rule is about `\[..\]` only; `$$..$$` is unambiguous."""
        spans = self.protect('$$%$$')
        self.assertEqual(len(spans), 1)

    def test_a_greek_letter_alone_is_a_formula(self):
        self.assertTrue(math_guard.looks_like_math('α'))
