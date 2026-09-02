#!/usr/bin/env python3
"""
repair.py - Fix a book that is already translated, without re-translating it.

    python scripts/repair.py rehash  <temp_dir> [...]
    python scripts/repair.py sidecar <temp_dir> [...] [--apply]

Re-converting a finished book is the wrong instinct. It moves every chunk
boundary and renumbers every `⟦M####⟧`, so nearly every chunk's hash changes
and the planner asks to translate the lot again -- discarding whatever review
has been done on the prose. Almost everything worth fixing can be fixed in
place instead.

**rehash** refreshes `manifest.json` after a source chunk was edited by hand.
A chunk's source hash is what decides whether it needs translating again, so
skipping this makes the next run quietly re-translate text that was already
right. It is the easiest step to forget and the most expensive to miss.

**sidecar** applies the ingest-side repairs to the raw LaTeX tables held in
`chunk*.math.json`. Those tables never pass through a translator -- they are
restored verbatim at merge -- so rewriting them touches no prose at all. It
undoes the column spec pandoc emitted twice and lifts the labels out of
`\\rotatebox`/`\\multirow`, which is how SINQ's tables went from ten ragged to
none without a single chunk being re-translated.

After either, confirm nothing is queued before rebuilding:

    python scripts/run_state.py plan "<temp_dir>"
"""

import argparse
import glob
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import arxiv_backend as ab                                      # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass


_TABULAR_OPEN_RE = re.compile(
    r'(\\begin\{(?:tabular|tabularx|longtable|array)\*?\}'
    r'(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\})?\s*)\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}')
_STAR_RE = re.compile(r'\*\s*\{\s*(\d+)\s*\}\s*\{([^{}]*)\}')


def undouble_spec(spec):
    """Remove `*{n}{X}` when exactly n copies of X already follow it.

    Reading `{l l l*{9}{r}}` pandoc expands the repeat; writing the raw block
    back out it emits the original spec AND the expansion, so the table gains
    nine columns it does not have. Keep the expansion, drop the repeat.
    """
    changed = True
    while changed:
        changed = False
        for m in _STAR_RE.finditer(spec):
            count, unit = int(m.group(1)), m.group(2)
            tail = spec[m.end():]
            if unit and tail.lstrip().startswith(unit * count):
                gap = len(tail) - len(tail.lstrip())
                spec = spec[:m.start()] + tail[gap:]
                changed = True
                break
    return spec


_TABULAR_BEGIN_RE = re.compile(r'\\begin\{tabular\*?\}\s*(?:\{[^{}]*\})?')
_ROW_END = '\\\\'
_RULE_RE = re.compile(r'^\s*(?:%[^\n]*\n\s*)*\\(?:mid|cmid|c|h)(?:rule|line)')


def restore_header_rule(latex):
    """Put back the rule that tells pandoc where a table's header ends.

    pandoc finds the header by looking for a rule, and an earlier version of
    the ingest deleted every `\\cmidrule` outright. With it gone a table whose
    header spans two rows produced NO <thead> at all: no rule under the
    header, no header repeated across a page break, and not one cell a <th>.
    SINQ's main results table printed as nine columns of numbers under
    nothing.

    A group row -- the one carrying `\\multicolumn` -- is exactly where the
    `\\cmidrule` used to be, so a `\\midrule` goes back there. Tables that
    already have a rule in that position are left alone.
    """
    out, cursor, count = [], 0, 0
    for m in _TABULAR_BEGIN_RE.finditer(latex):
        row_end = latex.find(_ROW_END, m.end())
        if row_end < 0:
            continue
        first_row = latex[m.end():row_end]
        if '\\multicolumn' not in first_row:
            continue
        after = latex[row_end + len(_ROW_END):]
        if _RULE_RE.match(after):
            continue                       # the rule is already there
        at = row_end + len(_ROW_END)
        if at < cursor:
            continue
        out.append(latex[cursor:at])
        out.append('\n\\midrule')
        cursor = at
        count += 1
    out.append(latex[cursor:])
    return ''.join(out), count


def repair_latex(latex):
    """Every in-place fix that applies to a raw LaTeX table. (text, notes)."""
    notes = []

    def swap(m):
        fixed = undouble_spec(m.group(2))
        if fixed == m.group(2):
            return m.group(0)
        notes.append('column spec')
        return m.group(1) + '{' + fixed + '}'

    latex = _TABULAR_OPEN_RE.sub(swap, latex)
    latex, turned = ab.unwrap_rotatebox(latex)
    if turned:
        notes.append('%d rotated/spanning label(s)' % turned)
    latex, rules = restore_header_rule(latex)
    if rules:
        notes.append('%d header rule(s)' % rules)
    return latex, notes


def cmd_sidecar(temp_dirs, apply):
    total = 0
    for temp in temp_dirs:
        touched = 0
        for path in sorted(glob.glob(os.path.join(temp, 'chunk*.math.json'))):
            with io.open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            changed = False
            for span in data.get('spans', []):
                latex = span.get('latex')
                if not latex or 'tabular' not in latex:
                    continue
                fixed, notes = repair_latex(latex)
                if fixed != latex:
                    span['latex'] = fixed
                    changed = True
                    touched += 1
                    print('   %-22s %s'
                          % (os.path.basename(path), ', '.join(notes)))
            if changed and apply:
                with io.open(path, 'w', encoding='utf-8', newline='') as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
        print('%-14s %d raw table(s) repaired%s'
              % (os.path.basename(temp), touched, '' if apply else ' (dry run)'))
        total += touched
    if total and not apply:
        print('\nNothing was written. Re-run with --apply.')
    elif total:
        print('\nThe merge is keyed on the output chunks, so touch them before '
              'rebuilding:\n  touch <temp_dir>/output_chunk*.md')
    return 0


def cmd_rehash(temp_dirs, _apply):
    for temp in temp_dirs:
        path = os.path.join(temp, 'manifest.json')
        with io.open(path, encoding='utf-8') as fh:
            manifest = json.load(fh)
        changed = []
        for entry in manifest['chunks']:
            with io.open(os.path.join(temp, entry['source_file']),
                         encoding='utf-8') as fh:
                body = fh.read()
            digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
            if digest != entry.get('source_hash'):
                entry['source_hash'] = digest
                changed.append(entry['id'])
        with io.open(path, 'w', encoding='utf-8', newline='') as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        print('%-14s %s' % (os.path.basename(temp),
                            ' '.join(changed) or 'nothing to re-hash'))
        if changed:
            print('   now record them, or the next run re-translates them:')
            print('   python scripts/run_state.py record "%s" %s'
                  % (temp, ' '.join(changed)))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split('\n')[1],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=('rehash', 'sidecar'))
    ap.add_argument('temp_dir', nargs='+')
    ap.add_argument('--apply', action='store_true',
                    help='write the changes (sidecar defaults to a dry run)')
    args = ap.parse_args()
    handler = {'rehash': cmd_rehash, 'sidecar': cmd_sidecar}[args.command]
    return handler([t.rstrip('\\/') for t in args.temp_dir], args.apply)


if __name__ == '__main__':
    sys.exit(main())
