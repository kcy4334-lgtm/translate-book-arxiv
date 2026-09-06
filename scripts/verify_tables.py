# -*- coding: utf-8 -*-
r"""Prove a table survived being translated, instead of asking whether it did.

Translating table captions and headers means editing raw LaTeX in place, in a
sidecar the merge will paste into the book verbatim. An agent doing that can
drop an `&`, merge two rows, or retype a number, and every check downstream
still passes: the table is present, the caption is Korean, the counts agree.
The reader gets a number that was never in the paper.

The invariant is exact and cheap. Translation changes WORDS. It must not
change the multiset of numbers, the count of `&` per row, the count of rows,
or any `\multicolumn`/`\multirow` span. So:

    python scripts/verify_tables.py snapshot "<temp_dir>"   # before editing
    ... table sub-agents run ...
    python scripts/verify_tables.py check "<temp_dir>" --strict

`check` refuses to answer without a snapshot rather than inventing a baseline
from the edited files -- a baseline the editor could also have touched is not
a baseline (KNOWLEDGE K57).
"""
from __future__ import unicode_literals

import argparse
import glob
import io
import json
import os
import re
import shutil
import sys

# A CLI prints, and what it prints may carry the book's text. A Windows
# console under a non-UTF-8 locale then raises UnicodeEncodeError and the
# command dies -- which stayed hidden while every caller happened to set
# PYTHONIOENCODING for it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

SNAPSHOT_DIR = '.table_snapshot'

_TABULAR_RE = re.compile(
    r'\\begin\{(tabular\*?|tabularx|longtable|array)\}(.*?)\\end\{\1\}',
    re.DOTALL)
_NUMBER_RE = re.compile(r'-?\d+(?:\.\d+)?')
_SPAN_RE = re.compile(r'\\(multicolumn|multirow)\s*\{\s*(\d+)\s*\}')
_ROW_SEP_RE = re.compile(r'\\\\')
_COMMENT_RE = re.compile(r'(?<!\\)%.*')


def _read(path):
    with io.open(path, encoding='utf-8', errors='replace') as handle:
        return handle.read()


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def table_files(temp_dir):
    """Every file a table's LaTeX can live in, in a stable order."""
    names = sorted(glob.glob(os.path.join(temp_dir, 'chunk*.math.json')))
    names += sorted(p for p in glob.glob(os.path.join(temp_dir, 'chunk*.md'))
                    if not os.path.basename(p).startswith('output_'))
    names += sorted(glob.glob(os.path.join(temp_dir, 'output_chunk*.md')))
    return [p for p in names if os.path.isfile(p)]


def latex_of(path):
    """All LaTeX in one file, whether it is a sidecar or markdown."""
    text = _read(path)
    if path.endswith('.math.json'):
        try:
            spans = json.loads(text)
        except ValueError:
            return ''
        if isinstance(spans, dict):
            spans = spans.get('spans', [])
        return '\n'.join(s.get('latex', '') for s in spans
                         if isinstance(s, dict))
    return text


def table_fingerprints(latex):
    """One fingerprint per tabular: what translation must not change."""
    out = []
    for match in _TABULAR_RE.finditer(latex):
        body = _COMMENT_RE.sub('', match.group(2))
        rows = [r for r in _ROW_SEP_RE.split(body) if r.strip()]
        out.append({
            'numbers': sorted(_NUMBER_RE.findall(body)),
            'rows': len(rows),
            'ampersands': [r.count('&') for r in rows],
            'spans': sorted('%s:%s' % (k, n) for k, n in _SPAN_RE.findall(body)),
        })
    return out


def snapshot(temp_dir):
    """Copy every file that can hold a table, before anything edits one."""
    dest = os.path.join(temp_dir, SNAPSHOT_DIR)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    files = table_files(temp_dir)
    for path in files:
        shutil.copy(path, os.path.join(dest, os.path.basename(path)))
    _write(os.path.join(dest, 'INDEX.json'),
           json.dumps([os.path.basename(p) for p in files], indent=1))
    return len(files), sum(len(table_fingerprints(latex_of(p))) for p in files)


def _describe(before, after):
    """What changed, in the reader's terms."""
    out = []
    if before['numbers'] != after['numbers']:
        # Multiset difference, not membership: "3" can survive in another
        # cell while THIS 3 became a 4, and a membership test would then
        # report a change it could not name.
        gone, new = list(before['numbers']), list(after['numbers'])
        for value in before['numbers']:
            if value in new:
                new.remove(value)
                gone.remove(value)
        out.append('numbers changed: %s -> %s'
                   % (gone[:6] or 'none', new[:6] or 'none'))
    if before['rows'] != after['rows']:
        out.append('rows: %d -> %d' % (before['rows'], after['rows']))
    if before['ampersands'] != after['ampersands']:
        wrong = [i for i, (a, b) in
                 enumerate(zip(before['ampersands'], after['ampersands']))
                 if a != b]
        out.append('cells per row changed in row(s) %s' % (wrong[:6] or '?'))
    if before['spans'] != after['spans']:
        out.append('spanning cells: %s -> %s'
                   % (before['spans'][:4], after['spans'][:4]))
    return out


def check(temp_dir):
    """(findings, tables checked). A finding is a table that was altered."""
    snap = os.path.join(temp_dir, SNAPSHOT_DIR)
    index = os.path.join(snap, 'INDEX.json')
    if not os.path.isfile(index):
        return None, 0
    names = json.loads(_read(index))
    findings, total = [], 0
    for name in names:
        old_path = os.path.join(snap, name)
        new_path = os.path.join(temp_dir, name)
        if not os.path.isfile(new_path):
            findings.append({'file': name, 'table': None,
                             'problems': ['the file is gone']})
            continue
        before = table_fingerprints(latex_of(old_path))
        after = table_fingerprints(latex_of(new_path))
        total += len(before)
        if len(before) != len(after):
            findings.append({
                'file': name, 'table': None,
                'problems': ['%d table(s) before, %d after'
                             % (len(before), len(after))]})
            continue
        for i, (was, now) in enumerate(zip(before, after)):
            problems = _describe(was, now)
            if problems:
                findings.append({'file': name, 'table': i + 1,
                                 'problems': problems})
    return findings, total


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('action', choices=['snapshot', 'check'])
    parser.add_argument('temp_dir')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()

    if args.action == 'snapshot':
        files, tables = snapshot(args.temp_dir)
        print('snapshot: %d file(s), %d table(s) recorded' % (files, tables))
        return 0

    findings, total = check(args.temp_dir)
    if findings is None:
        print('no snapshot in %s' % os.path.join(args.temp_dir, SNAPSHOT_DIR))
        print('run "verify_tables.py snapshot" BEFORE the table agents, not '
              'after: a baseline the editor could have touched is not one')
        return 1 if args.strict else 0

    print('%d table(s) compared against the snapshot' % total)
    for finding in findings:
        where = finding['file']
        if finding['table']:
            where += ' table %d' % finding['table']
        print('  %s' % where)
        for problem in finding['problems']:
            print('     - %s' % problem)
    print()
    if findings:
        print('FAIL: %d table(s) changed in a way translation cannot explain'
              % len(findings))
        return 1 if args.strict else 0
    print('PASS: every table kept its numbers, rows, cells and spans')
    return 0


if __name__ == '__main__':
    sys.exit(main())
