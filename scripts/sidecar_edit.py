# -*- coding: utf-8 -*-
r"""Edit one span of one sidecar, and refuse when someone else edited it too.

Step 4.6 used to tell every table sub-agent to "edit with a Python script".
Several agents run at once, they share one scratch directory, and they all
reach for the same obvious filename, so in one session two of them wrote
`translate_floats.py`. One agent's file was replaced on disk between writing
it and running it; it executed the other agent's code against the wrong book,
noticed, and restored that book from a backup it had taken earlier -- but a
third agent had already finished translating the same file legitimately, and
the restore silently erased that work.

Nothing caught it. `verify_tables.py` cannot: a file reverted to the original
has exactly the numbers, rows and `&` counts the snapshot recorded, so a
revert is structurally perfect. The agent whose work vanished reported success
in good faith, with a full structural comparison, because at the moment it
looked the file was correct.

Three things went wrong and each gets its own answer here.

  * Agents had to author a script, so they had to invent a filename. Giving
    them a command means there is no script, hence no filename, hence no
    collision. That is the reason this module exists at all.
  * A write computed from a stale read overwrote a newer one -- a lost update.
    `write` takes the `sha256` that `read` handed out and refuses if the file
    has moved since. A destructive "restore" is just a write with a stale
    token, so it is refused by the same rule.
  * The damage was invisible. Every write appends to `.sidecar_edits.jsonl`,
    so a caption that was translated and then reverted leaves both events on
    the record instead of none.

Structural invariants that each agent used to re-implement by hand (and each
slightly differently) are checked here once: numbers, rows, cells per row,
spanning cells, control sequences, placeholders, and citation keys.

    python scripts/sidecar_edit.py read  <chunk.math.json>
    python scripts/sidecar_edit.py write <chunk.math.json> \
        --token "T0001" --expect <sha> --latex-file new.tex
    python scripts/sidecar_edit.py log   <temp_dir>
"""
from __future__ import unicode_literals

import argparse
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math_guard
import verify_tables

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

LOG_NAME = '.sidecar_edits.jsonl'

_CONTROL_RE = re.compile(r'\\[A-Za-z]+')
_PLACEHOLDER_RE = re.compile('\u27e6[^\u27e6\u27e7]*\u27e7')
_KEYED_RE = re.compile(r'\\(cite[a-z]*|label|ref|eqref)\s*\{([^{}]*)\}')
_PROSE_RE = re.compile(r'\\caption|\\tablenotes|\\Comment|\\Require|\\Ensure')
_CAPTION_RE = re.compile(r'\\caption\s*(?:\[[^\]]*\])?\s*\{')


def _read_bytes(path):
    with open(path, 'rb') as handle:
        return handle.read()


def _read_text(path):
    with io.open(path, encoding='utf-8') as handle:
        return handle.read()


def sha_of(path):
    return hashlib.sha256(_read_bytes(path)).hexdigest()


def load(path):
    """(payload, spans). Refuses a shape `write_sidecar` could not produce."""
    payload = json.loads(_read_text(path))
    if not isinstance(payload, dict):
        raise ValueError('%s is not a sidecar object' % path)
    extra = set(payload) - {'version', 'chunk', 'spans'}
    if extra:
        raise ValueError(
            'sidecar has top-level key(s) %s that this tool would drop on '
            'write; edit it by hand and say so' % sorted(extra))
    spans = payload.get('spans')
    if not isinstance(spans, list):
        raise ValueError('%s has no span list' % path)
    return payload, spans


def write_atomically(path, payload):
    r"""Serialise exactly as `math_guard.write_sidecar` does, then swap.

    Deliberately not a call to that function: a crash partway through its
    non-atomic write would leave a truncated sidecar, which is the very loss
    this module exists to prevent. `tests/test_sidecar_edit.py` locks the two
    serialisations together byte for byte so they cannot drift apart.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    temp = path + '.writing'
    with io.open(temp, 'w', encoding='utf-8') as handle:
        handle.write(text)
    os.replace(temp, path)


def normalise_token(token):
    r"""Accept `T0001`, `⟦T0001⟧` and `\u27e6T0001\u27e7` alike.

    The brackets are hard to type and easy to mangle through a shell, and a
    tool that rejects the right span over a bracket teaches its user to work
    around it.
    """
    return (token or '').strip().strip('\u27e6\u27e7')


def find_span(spans, token):
    wanted = normalise_token(token)
    hits = [i for i, span in enumerate(spans)
            if isinstance(span, dict)
            and normalise_token(span.get('token')) == wanted]
    if not hits:
        known = ', '.join(normalise_token(s.get('token')) for s in spans
                          if isinstance(s, dict))
        raise ValueError('no span %s in this sidecar; it holds: %s'
                         % (wanted, known or '(none)'))
    if len(hits) > 1:
        raise ValueError('span %s appears %d times' % (wanted, len(hits)))
    return hits[0]


def translatable(span):
    """A span worth a translator's attention: a float, or prose in LaTeX."""
    if not isinstance(span, dict):
        return False
    if span.get('kind') == 'float':
        return True
    return bool(_PROSE_RE.search(span.get('latex') or ''))


def structural_problems(before, after):
    r"""What changed that translating words could not have changed.

    Numbers are compared across the whole float, not only inside `tabular`:
    a caption saying "the averaged predictions of 10 models" carries a number
    the reader will trust, and `verify_tables` only ever looks inside a
    `tabular` body.
    """
    problems = []

    was_numbers = sorted(verify_tables._NUMBER_RE.findall(before))
    now_numbers = sorted(verify_tables._NUMBER_RE.findall(after))
    if was_numbers != now_numbers:
        gone, new = list(was_numbers), list(now_numbers)
        for value in was_numbers:
            if value in new:
                new.remove(value)
                gone.remove(value)
        problems.append('numbers changed: lost %s, gained %s'
                        % (gone[:6] or 'none', new[:6] or 'none'))

    was_tables = verify_tables.table_fingerprints(before)
    now_tables = verify_tables.table_fingerprints(after)
    if len(was_tables) != len(now_tables):
        problems.append('%d tabular(s) before, %d after'
                        % (len(was_tables), len(now_tables)))
    else:
        for i, (was, now) in enumerate(zip(was_tables, now_tables)):
            for line in verify_tables._describe(was, now):
                # The whole-float number check above already said this, and
                # saying it twice reads as two faults.
                if line.startswith('numbers changed'):
                    continue
                problems.append('tabular %d: %s' % (i + 1, line))

    was_cs = sorted(_CONTROL_RE.findall(before))
    now_cs = sorted(_CONTROL_RE.findall(after))
    if was_cs != now_cs:
        gone = sorted(set(was_cs) - set(now_cs))
        new = sorted(set(now_cs) - set(was_cs))
        counts = [c for c in set(was_cs) & set(now_cs)
                  if was_cs.count(c) != now_cs.count(c)]
        problems.append('LaTeX commands changed: lost %s, gained %s, '
                        'recounted %s'
                        % (gone[:6] or 'none', new[:6] or 'none',
                           sorted(counts)[:6] or 'none'))

    was_ph = sorted(_PLACEHOLDER_RE.findall(before))
    now_ph = sorted(_PLACEHOLDER_RE.findall(after))
    if was_ph != now_ph:
        problems.append('placeholders changed: %s -> %s'
                        % (was_ph[:4] or 'none', now_ph[:4] or 'none'))

    was_keys = sorted(_KEYED_RE.findall(before))
    now_keys = sorted(_KEYED_RE.findall(after))
    if was_keys != now_keys:
        problems.append('cite/label keys changed: %s -> %s'
                        % (was_keys[:4] or 'none', now_keys[:4] or 'none'))

    return problems


def caption_bodies(latex):
    """The text inside each `\\caption{}`, brace-matched, not regex-matched."""
    out = []
    for match in _CAPTION_RE.finditer(latex):
        start = match.end() - 1
        depth, i = 1, start + 1
        while i < len(latex) and depth:
            depth += (latex[i] == '{') - (latex[i] == '}')
            i += 1
        out.append(latex[start + 1:i - 1])
    return out


def prose_digest(latex, limit=120):
    r"""The part of a float a reader would notice changing.

    The first 120 characters of a table float are `\begin{tabular}` and a
    column spec, identical before and after any translation, so a log keyed
    on them shows two indistinguishable lines for a caption that was
    translated and then reverted. The caption is the prose; log that.
    """
    captions = caption_bodies(latex)
    text = ' | '.join(' '.join(c.split()) for c in captions)
    return (text or ' '.join(latex.split()))[:limit]


def append_log(temp_dir, record):
    """Best effort: an unwritable log must not cost a finished translation."""
    path = os.path.join(temp_dir, LOG_NAME)
    try:
        with io.open(path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False,
                                    sort_keys=True) + '\n')
    except (IOError, OSError) as error:
        sys.stderr.write('warning: could not append to %s (%s)\n'
                         % (path, error))


def do_read(args):
    path = os.path.abspath(args.sidecar)
    payload, spans = load(path)
    listed = []
    for i, span in enumerate(spans):
        if not args.all and not translatable(span):
            continue
        listed.append({'index': i,
                       'token': normalise_token(span.get('token')),
                       'kind': span.get('kind'),
                       'latex': span.get('latex', '')})
    print(json.dumps({'file': path,
                      'chunk': payload.get('chunk'),
                      'sha256': sha_of(path),
                      'spans': listed,
                      'total_spans': len(spans)},
                     ensure_ascii=False, indent=2))
    return 0


def do_write(args):
    path = os.path.abspath(args.sidecar)
    temp_dir = os.path.dirname(path)
    current = sha_of(path)
    if current != args.expect:
        sys.stderr.write(
            'REFUSED: %s changed since you read it.\n'
            '  you read   %s\n  it is now  %s\n'
            'Another agent has written to this file. Re-run `read`, redo your\n'
            'edit against what is there now, and write again. Do NOT restore\n'
            'it from a backup: the backup is older than their work and would\n'
            'erase it, which is exactly how a finished translation was lost\n'
            'once already.\n' % (path, args.expect, current))
        return 2

    payload, spans = load(path)
    expected_path = math_guard.sidecar_path(temp_dir, payload.get('chunk') or '')
    if os.path.normcase(expected_path) != os.path.normcase(path):
        sys.stderr.write(
            'REFUSED: this file is named %s but records chunk %r, which '
            'belongs in %s.\nWriting would put the edit in the wrong book.\n'
            % (os.path.basename(path), payload.get('chunk'),
               os.path.basename(expected_path)))
        return 2

    index = find_span(spans, args.token)
    before = spans[index].get('latex', '')
    after = _read_text(args.latex_file)

    if after == before:
        sys.stderr.write('REFUSED: the replacement is identical to what is '
                         'already there; nothing to write.\n')
        return 2

    problems = structural_problems(before, after)
    if problems:
        sys.stderr.write('REFUSED: %s changed in ways translating words '
                         'cannot explain.\n' % normalise_token(args.token))
        for problem in problems:
            sys.stderr.write('  - %s\n' % problem)
        sys.stderr.write('Fix the replacement. Do not relax the check: a '
                         'number the reader trusts is at stake.\n')
        return 2

    spans[index]['latex'] = after
    payload['spans'] = spans
    write_atomically(path, payload)
    new_sha = sha_of(path)
    append_log(temp_dir, {
        'file': os.path.basename(path),
        'token': normalise_token(args.token),
        'from_sha256': current,
        'to_sha256': new_sha,
        'before_prose': prose_digest(before),
        'after_prose': prose_digest(after),
    })
    print('wrote %s span %s' % (os.path.basename(path),
                                normalise_token(args.token)))
    print('sha256 %s' % new_sha)
    return 0


def do_log(args):
    path = os.path.join(args.temp_dir, LOG_NAME)
    if not os.path.isfile(path):
        print('no edits recorded in %s' % path)
        return 0
    for line in _read_text(path).splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        print('%-24s %-8s %s' % (record.get('file'), record.get('token'),
                                 record.get('after_prose', '')[:60]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='action')

    reader = sub.add_parser('read', help='show a sidecar and its sha256')
    reader.add_argument('sidecar')
    reader.add_argument('--all', action='store_true',
                        help='include math and cite spans, not just floats')

    writer = sub.add_parser('write', help='replace one span, guarded')
    writer.add_argument('sidecar')
    writer.add_argument('--token', required=True, help='e.g. T0001')
    writer.add_argument('--expect', required=True,
                        help='the sha256 that `read` printed')
    writer.add_argument('--latex-file', required=True,
                        help='UTF-8 file holding the replacement LaTeX; a '
                             'file, never a command line, because the LaTeX '
                             'is full of backslashes')

    logger = sub.add_parser('log', help='every guarded edit, in order')
    logger.add_argument('temp_dir')

    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return 1
    try:
        return {'read': do_read, 'write': do_write, 'log': do_log}[args.action](args)
    except (ValueError, IOError, OSError) as error:
        sys.stderr.write('ERROR: %s\n' % error)
        return 2


if __name__ == '__main__':
    sys.exit(main())
