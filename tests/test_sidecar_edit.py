# -*- coding: utf-8 -*-
r"""A second writer cannot erase the first one's translation.

This locks down the incident that produced `scripts/sidecar_edit.py`. Two
table agents, one shared scratch directory, the same obvious script name:
one agent's script was replaced on disk between being written and being run,
so it executed the other's code against the wrong book, then "restored" that
book from its own older backup and erased a third agent's finished Japanese.

Every existing check passed afterwards, and they were right to. A file
reverted to the original keeps exactly the numbers, rows and `&` counts the
snapshot recorded, so `verify_tables.py` reports PASS on a perfect revert.
That is why the guard had to be at the write, not after it.

The class of bug is a lost update, so the tests are the lost-update tests:
a stale writer is refused, a current one succeeds, and the refusal says to
re-read rather than to restore.
"""
from __future__ import unicode_literals

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import math_guard
import sidecar_edit


FLOAT = (
    '\\begin{table}\n'
    '\\begin{tabular}{|c|c|c|}\n'
    '\\hline\n'
    'System & Test Frame Accuracy & WER \\\\\n'
    '\\hline\n'
    'Baseline & 58.9 & 10.9\\% \\\\\n'
    'Distilled Single model & 60.8 & 10.7\\% \\\\\n'
    '\\hline\n'
    '\\end{tabular}\n'
    '\\caption{Frame classification accuracy and WER over 10 models '
    '\\cite{hinton}.}\n'
    '\\end{table}')

JAPANESE = FLOAT.replace(
    'System & Test Frame Accuracy',
    '\u30b7\u30b9\u30c6\u30e0 & \u30c6\u30b9\u30c8\u30d5\u30ec\u30fc'
    '\u30e0\u7cbe\u5ea6').replace(
    'Frame classification accuracy and WER over 10 models',
    '10\u500b\u306e\u30e2\u30c7\u30eb\u306b\u308f\u305f\u308b'
    '\u30d5\u30ec\u30fc\u30e0\u5206\u985e\u7cbe\u5ea6\u3068WER')

KOREAN = FLOAT.replace(
    'Frame classification accuracy and WER over 10 models',
    '10\uac1c \ubaa8\ub378\uc5d0 \ub300\ud55c \ud504\ub808\uc784 '
    '\ubd84\ub958 \uc815\ud655\ub3c4\uc640 WER')


class Harness(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = math_guard.write_sidecar(self.dir, 'chunk0004.md', [
            {'token': '\u27e6T0001\u27e7', 'kind': 'float', 'prefix': 'T',
             'latex': FLOAT},
            {'token': '\u27e6M0009\u27e7', 'kind': 'inline', 'prefix': 'M',
             'latex': '$m$'},
        ])

    def latex_file(self, text, name='new.tex'):
        path = os.path.join(self.dir, name)
        with io.open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return path

    def run_write(self, replacement, expect, token='T0001'):
        """(exit code, stderr). `main` is the contract an agent actually uses."""
        stderr = io.StringIO()
        held, sys.stderr = sys.stderr, stderr
        try:
            code = sidecar_edit.main([
                'write', self.path, '--token', token, '--expect', expect,
                '--latex-file', self.latex_file(replacement)])
        finally:
            sys.stderr = held
        return code, stderr.getvalue()

    def latex_now(self, index=0):
        payload, spans = sidecar_edit.load(self.path)
        return spans[index]['latex']

    def sha(self):
        return sidecar_edit.sha_of(self.path)


class TheIncident(Harness):
    r"""Agent A translates, agent B overwrites from a read taken earlier."""

    def test_the_second_writer_is_refused_and_the_first_survives(self):
        stale = self.sha()                      # B reads
        code, _ = self.run_write(JAPANESE, stale)   # A translates and writes
        self.assertEqual(code, 0)
        self.assertIn('\u7cbe\u5ea6', self.latex_now())

        code, message = self.run_write(FLOAT, stale)  # B "restores"
        self.assertEqual(code, 2)
        self.assertIn('REFUSED', message)
        self.assertIn('\u7cbe\u5ea6', self.latex_now(),
                      'the restore erased a finished translation')

    def test_the_refusal_says_re_read_not_restore(self):
        """A refusal that leaves the reader guessing gets worked around."""
        stale = self.sha()
        self.run_write(JAPANESE, stale)
        _, message = self.run_write(KOREAN, stale)
        self.assertIn('Re-run `read`', message)
        self.assertIn('Do NOT restore', message)

    def test_a_fresh_read_lets_the_second_writer_through(self):
        """The guard is against stale writes, not against writing twice."""
        self.run_write(JAPANESE, self.sha())
        code, _ = self.run_write(KOREAN, self.sha())
        self.assertEqual(code, 0)
        self.assertIn('\ubd84\ub958', self.latex_now())


class WhyVerifyTablesCouldNotCatchIt(Harness):
    r"""The premise of this module, stated as a test so it stays true."""

    def test_a_revert_is_structurally_perfect(self):
        import verify_tables
        self.assertEqual(verify_tables.table_fingerprints(FLOAT),
                         verify_tables.table_fingerprints(JAPANESE))
        self.assertEqual(sidecar_edit.structural_problems(JAPANESE, FLOAT), [])


class StructureIsGuarded(Harness):

    def refuse(self, replacement):
        code, message = self.run_write(replacement, self.sha())
        self.assertEqual(code, 2, message)
        self.assertEqual(self.latex_now(), FLOAT, 'refused but wrote anyway')
        return message

    def test_a_retyped_number_inside_the_table(self):
        self.assertIn('numbers changed',
                      self.refuse(JAPANESE.replace('58.9', '58.8')))

    def test_a_retyped_number_in_the_caption(self):
        r"""`verify_tables` only looks inside `tabular`, so the caption's own
        numbers were unguarded until this module compared the whole float."""
        self.assertIn('numbers changed',
                      self.refuse(JAPANESE.replace('10 models', '100 models')
                                  .replace('10\u500b', '100\u500b')))

    def test_a_dropped_rule(self):
        self.assertIn('LaTeX commands changed',
                      self.refuse(JAPANESE.replace('\\hline\n', '', 1)))

    def test_a_merged_cell(self):
        self.assertIn('cells per row',
                      self.refuse(JAPANESE.replace(
                          '58.9 & 10.9', '58.9 10.9')))

    def test_a_dropped_row(self):
        self.assertIn('rows', self.refuse(JAPANESE.replace(
            'Distilled Single model & 60.8 & 10.7\\% \\\\\n', '')))

    def test_a_rewritten_citation_key(self):
        self.assertIn('cite/label keys',
                      self.refuse(JAPANESE.replace('hinton', 'Hinton')))

    def test_a_mangled_placeholder(self):
        with_token = FLOAT.replace('WER \\\\', 'WER \u27e6M0031\u27e7 \\\\')
        payload, spans = sidecar_edit.load(self.path)
        spans[0]['latex'] = with_token
        sidecar_edit.write_atomically(self.path, payload)
        code, message = self.run_write(
            with_token.replace('\u27e6M0031\u27e7', '\u27e6M0032\u27e7'),
            self.sha())
        self.assertEqual(code, 2)
        self.assertIn('placeholders changed', message)

    def test_a_no_op_is_refused_rather_than_logged_as_work(self):
        code, message = self.run_write(FLOAT, self.sha())
        self.assertEqual(code, 2)
        self.assertIn('identical', message)


class CorrectWorkIsNotRefused(Harness):
    r"""K68: a check that fires on a good edit teaches its reader to skip it.

    Each case here is a judgement a table agent actually made in this repo.
    """

    def accept(self, replacement):
        code, message = self.run_write(replacement, self.sha())
        self.assertEqual(code, 0, message)

    def test_translating_words(self):
        self.accept(JAPANESE)

    def test_dropping_an_escaped_hash_that_meant_the_word_number(self):
        r"""`\# of specialists` -> `\u5c02\u7528\u30e2\u30c7\u30eb\u6570\u91cf`:
        the `#` is the word "number of", absorbed into the noun. It is an
        escaped character in prose, not a command, so it must not be counted
        as structure."""
        hashed = FLOAT.replace('System &', '\\# of systems &')
        payload, spans = sidecar_edit.load(self.path)
        spans[0]['latex'] = hashed
        sidecar_edit.write_atomically(self.path, payload)
        self.accept(hashed.replace('\\# of systems',
                                   '\u30b7\u30b9\u30c6\u30e0\u6570'))

    def test_keeping_a_percent_sign_the_words_moved_around(self):
        self.accept(JAPANESE.replace('WER \\\\', 'WER (\\%) \\\\')
                    .replace('10.9\\%', '10.9').replace('10.7\\%', '10.7'))

    def test_a_caption_that_reorders_the_numbers(self):
        """Word order changes; the multiset does not."""
        self.accept(JAPANESE.replace(
            'Baseline & 58.9 & 10.9\\%', 'Baseline & 10.9\\% & 58.9'))


class TheTokenIsForgiving(Harness):
    r"""The brackets are hard to type and easy to mangle through a shell."""

    def test_bare_and_bracketed_forms_both_resolve(self):
        for token in ('T0001', '\u27e6T0001\u27e7', ' T0001 '):
            payload, spans = sidecar_edit.load(self.path)
            self.assertEqual(sidecar_edit.find_span(spans, token), 0)

    def test_an_unknown_token_lists_what_is_there(self):
        payload, spans = sidecar_edit.load(self.path)
        with self.assertRaises(ValueError) as caught:
            sidecar_edit.find_span(spans, 'T9999')
        self.assertIn('T0001', str(caught.exception))


class TheFileIsNotSilentlyReshaped(Harness):

    def test_the_serialisation_matches_the_pipeline_byte_for_byte(self):
        r"""If this drifts, every guarded edit rewrites the whole file and the
        next `git diff` (or the next agent's byte comparison) is noise."""
        payload, spans = sidecar_edit.load(self.path)
        spans[0]['latex'] = JAPANESE
        sidecar_edit.write_atomically(self.path, payload)
        with open(self.path, 'rb') as handle:
            mine = handle.read()
        math_guard.write_sidecar(self.dir, 'chunk0004.md', spans)
        with open(self.path, 'rb') as handle:
            self.assertEqual(mine, handle.read())

    def test_the_untouched_spans_are_left_alone(self):
        self.run_write(JAPANESE, self.sha())
        payload, spans = sidecar_edit.load(self.path)
        self.assertEqual(spans[1]['latex'], '$m$')
        self.assertEqual(spans[1]['prefix'], 'M')
        self.assertEqual(payload['chunk'], 'chunk0004.md')

    def test_no_temporary_file_is_left_behind(self):
        self.run_write(JAPANESE, self.sha())
        self.assertFalse(os.path.exists(self.path + '.writing'))


class TheWrongBookIsRefused(Harness):
    r"""The incident wrote Korean into the Japanese book. A sidecar knows
    which chunk it belongs to, so the tool can tell before writing."""

    def test_a_sidecar_whose_name_disagrees_with_its_chunk(self):
        payload, spans = sidecar_edit.load(self.path)
        payload['chunk'] = 'chunk0006.md'
        sidecar_edit.write_atomically(self.path, payload)
        code, message = self.run_write(JAPANESE, self.sha())
        self.assertEqual(code, 2)
        self.assertIn('wrong book', message)


class EveryEditIsOnTheRecord(Harness):
    r"""The loss was invisible: nothing anywhere recorded that a translated
    caption had existed. Both events belong on the record, not neither."""

    def read_log(self):
        path = os.path.join(self.dir, sidecar_edit.LOG_NAME)
        with io.open(path, encoding='utf-8') as handle:
            return [json.loads(l) for l in handle.read().splitlines()
                    if l.strip()]

    def test_the_log_holds_both_writes(self):
        self.run_write(JAPANESE, self.sha())
        self.run_write(KOREAN, self.sha())
        lines = self.read_log()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['to_sha256'], lines[1]['from_sha256'],
                         'the log must chain, or it cannot show an overwrite')
        self.assertIn('\u7cbe\u5ea6', lines[0]['after_prose'])
        self.assertIn('\ubd84\ub958', lines[1]['after_prose'])

    def test_the_log_records_the_caption_not_the_tabular_preamble(self):
        r"""A float opens with `\begin{tabular}` and a column spec, the same
        before and after any translation. Logging the head would print two
        identical lines for a caption that was translated and then reverted,
        which is precisely the event the log exists to make visible."""
        self.run_write(JAPANESE, self.sha())
        self.run_write(FLOAT, self.sha())          # a revert, freshly read
        lines = self.read_log()
        self.assertNotEqual(lines[0]['after_prose'], lines[1]['after_prose'])
        self.assertNotIn('tabular', lines[0]['after_prose'])
        self.assertIn('Frame classification', lines[1]['after_prose'])

    def test_a_refused_write_leaves_no_trace(self):
        stale = self.sha()
        self.run_write(JAPANESE, stale)
        self.run_write(KOREAN, stale)
        self.assertEqual(len(self.read_log()), 1)


class TheReadHandsOutWhatTheWriteDemands(Harness):

    def capture_read(self, *extra):
        stdout = io.StringIO()
        held, sys.stdout = sys.stdout, stdout
        try:
            code = sidecar_edit.main(['read', self.path] + list(extra))
        finally:
            sys.stdout = held
        self.assertEqual(code, 0)
        return json.loads(stdout.getvalue())

    def test_read_prints_the_sha_that_write_accepts(self):
        report = self.capture_read()
        code, message = self.run_write(JAPANESE, report['sha256'])
        self.assertEqual(code, 0, message)

    def test_read_shows_floats_and_hides_the_math(self):
        report = self.capture_read()
        self.assertEqual([s['token'] for s in report['spans']], ['T0001'])
        self.assertEqual(report['total_spans'], 2)

    def test_read_all_shows_everything(self):
        self.assertEqual(
            [s['token'] for s in self.capture_read('--all')['spans']],
            ['T0001', 'M0009'])


if __name__ == '__main__':
    unittest.main()
