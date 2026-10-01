# -*- coding: utf-8 -*-
r"""Look things up in KNOWLEDGE.md and KNOWHOW.md without reading them whole.

Together the two files are now over 110 KB across 130-odd entries, and they
only grow. Reading both to answer one question costs more than the answer is
worth, and "is there an entry about `_widen_to_float`?" cannot be asked of a
symptom index at all.

There is deliberately NO index file on disk. An index that is written down is
one more artifact that drifts from what it describes, and this pipeline has
paid for that mistake more than once (the symptom tables are hand-kept, which
is why `check` exists). Parsing both files takes milliseconds, so the index is
built fresh on every call and cannot be wrong.

    python scripts/kb.py list                  # id + title, one line each
    python scripts/kb.py find "<query>"        # the matching entries, in full
    python scripts/kb.py show K102 H26         # named entries, in full
    python scripts/kb.py check                 # index rows vs entries
    python scripts/kb.py stale                 # entries naming code that is gone
"""
import argparse
import io
import os
import re
import sys

if sys.platform == 'win32':
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# REFEREE.md is searched with the other two on purpose. A card raised on one
# role has to be findable when a DIFFERENT role does the same thing, and the
# only way that happens without someone remembering is if the ledger answers
# the same query the other logs answer.
SOURCES = (('KNOWLEDGE.md', 'K'), ('KNOWHOW.md', 'H'), ('REFEREE.md', 'R'))

_ENTRY_RE = re.compile(r'(?m)^### ([KHR]\d+)\s*$')
_INDEX_ROW_RE = re.compile(r'\[([KHR]\d+)\]\(#[khr]\d+\)')
# What an entry names that a searcher might come looking for: anything in
# backticks, plus bare \latexCommands, which the prose often writes unquoted.
_TOKEN_RE = re.compile(r'`([^`\n]{1,60})`|(\\[A-Za-z@]{2,})')
_WORD_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_.\\/-]{1,}')


def read(name):
    path = os.path.join(SKILL_DIR, name)
    if not os.path.isfile(path):
        return ''
    return io.open(path, encoding='utf-8', errors='replace').read()


def parse(text, source):
    """Every entry in one file: id, title, body, tokens."""
    entries = []
    marks = list(_ENTRY_RE.finditer(text))
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():stop]
        # An entry ends at its own `---`, not at the next heading: what
        # follows the rule belongs to the file, not to this entry.
        cut = body.find('\n---')
        if cut >= 0:
            body = body[:cut]
        body = body.strip('\n')
        title = ''
        for line in body.split('\n'):
            if line.strip():
                title = line.strip().strip('*').strip()
                break
        tokens = set()
        for tm in _TOKEN_RE.finditer(body):
            tokens.add((tm.group(1) or tm.group(2)).strip())
        entries.append({'id': m.group(1), 'source': source, 'title': title,
                        'body': body, 'tokens': tokens})
    return entries


def load():
    out = []
    for name, _prefix in SOURCES:
        out.extend(parse(read(name), name))
    return out


def index_rows(name):
    """The ids the file's own symptom/task table points at."""
    rows = []
    for line in read(name).split('\n'):
        if line.startswith('|'):
            rows.extend(_INDEX_ROW_RE.findall(line))
    return rows


def score(entry, terms):
    """How well one entry answers this query. 0 means it does not."""
    total = 0
    title = entry['title'].lower()
    body = entry['body'].lower()
    tokens = ' '.join(entry['tokens']).lower()
    for term in terms:
        hit = 0
        if term == entry['id'].lower():
            hit += 20
        if term in title:
            hit += 5
        if term in tokens:
            hit += 3
        if term in body:
            hit += 1
        total += hit
    return total


def render(entry, full=True):
    head = '### %s  [%s]' % (entry['id'], entry['source'])
    if not full:
        return '%-6s %-12s %s' % (entry['id'], '[%s]' % entry['source'],
                                  entry['title'][:96])
    return head + '\n' + entry['body']


def cmd_list(args):
    for entry in load():
        print(render(entry, full=False))
    return 0


def cmd_find(args):
    terms = [t.lower() for t in _WORD_RE.findall(args.query)] or \
        [args.query.lower()]
    scored = [(score(e, terms), e) for e in load()]
    scored = [(s, e) for s, e in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    if not scored:
        print('No entry mentions %r.' % args.query)
        print('That is an answer: nothing here has met it yet. Say so rather '
              'than reading both files to be sure.')
        return 1
    shown = scored[:args.limit]
    if args.ids_only:
        print(' '.join(e['id'] for _s, e in shown))
        return 0
    for n, (s, entry) in enumerate(shown):
        if n:
            print()
        print(render(entry))
    if len(scored) > len(shown):
        print()
        print('%d more entry(ies) match more weakly: %s'
              % (len(scored) - len(shown),
                 ' '.join(e['id'] for _s, e in scored[args.limit:])))
    return 0


def cmd_show(args):
    wanted = [w.upper() for w in args.ids]
    by_id = dict((e['id'], e) for e in load())
    missing = [w for w in wanted if w not in by_id]
    for n, w in enumerate([w for w in wanted if w in by_id]):
        if n:
            print()
        print(render(by_id[w]))
    for w in missing:
        print('No entry %s.' % w)
    return 1 if missing else 0


def cmd_check(args):
    problems = []
    entries = load()
    by_source = {}
    for entry in entries:
        by_source.setdefault(entry['source'], []).append(entry['id'])
    for name, _prefix in SOURCES:
        have = set(by_source.get(name, []))
        rows = index_rows(name)
        for entry_id in sorted(have - set(rows)):
            problems.append('%s: %s has no index row — nobody will find it'
                            % (name, entry_id))
        for entry_id in sorted(set(rows) - have):
            problems.append('%s: index row points at %s, which does not exist'
                            % (name, entry_id))
        # An entry under SEVERAL rows is the index working, not a fault: one
        # cause shows up as more than one symptom, and K1 is reached both from
        # "content is in output.md but not the PDF" and from "a step prints OK
        # while the output is visibly wrong". Only never-indexed and
        # nothing-to-land-on are faults.
    print('%d entry(ies): %s'
          % (len(entries), ', '.join('%d in %s' % (len(v), k)
                                     for k, v in sorted(by_source.items()))))
    if not problems:
        print('PASS: every entry is reachable from its index, and every row '
              'lands on an entry.')
        return 0
    for line in problems:
        print('   %s' % line)
    return 1


_PATH_RE = re.compile(r'^(?:scripts|tests)/[A-Za-z_][A-Za-z0-9_]*\.(?:py|html)$')
_SYMBOL_RE = re.compile(r'^_?[a-z][a-z0-9_]{4,}(?:\(\))?$')


def cmd_stale(args):
    """Entries naming a file or function the repo no longer has.

    A log that names code is only useful while the code answers to the name.
    Reported, never fixed here: an entry may describe something deliberately
    removed, and that is history worth keeping — but it should say so.
    """
    haystack = []
    for folder in ('scripts', 'tests'):
        base = os.path.join(SKILL_DIR, folder)
        for root, _dirs, files in os.walk(base):
            if '__pycache__' in root:
                continue
            for f in files:
                if f.endswith(('.py', '.html')):
                    haystack.append(io.open(os.path.join(root, f),
                                            encoding='utf-8',
                                            errors='replace').read())
    blob = '\n'.join(haystack)
    findings = []
    for entry in load():
        gone = []
        for token in sorted(entry['tokens']):
            if _PATH_RE.match(token):
                if not os.path.isfile(os.path.join(SKILL_DIR, token)):
                    gone.append(token)
            elif _SYMBOL_RE.match(token):
                if token.rstrip('()') not in blob:
                    gone.append(token)
        if gone:
            findings.append((entry, gone))
    if not findings:
        print('PASS: every file and function these entries name still exists.')
        return 0
    print('%d entry(ies) name code that is not in the repo:' % len(findings))
    for entry, gone in findings:
        print('   %-6s %-40s %s' % (entry['id'], entry['title'][:40],
                                    ', '.join(gone)))
    print()
    print('Each is either a rename to follow up or history worth keeping. '
          'Decide per entry; do not bulk-edit.')
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('list', help='id and title for every entry')
    f = sub.add_parser('find', help='the entries matching a query, in full')
    f.add_argument('query')
    f.add_argument('--limit', type=int, default=5)
    f.add_argument('--ids-only', action='store_true')
    s = sub.add_parser('show', help='named entries, in full')
    s.add_argument('ids', nargs='+')
    sub.add_parser('check', help='index rows against entries')
    sub.add_parser('stale', help='entries naming code that no longer exists')
    args = ap.parse_args()

    handlers = {'list': cmd_list, 'find': cmd_find, 'show': cmd_show,
                'check': cmd_check, 'stale': cmd_stale}
    if args.cmd in handlers:
        return handlers[args.cmd](args)
    ap.print_help()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
