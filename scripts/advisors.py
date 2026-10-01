# -*- coding: utf-8 -*-
r"""Who was consulted, when, and what they said.

The referee could be fixed because it kept a store: `runs.json` sat at ten rows
while nine books were rebuilt, and that stalled number is what showed the
recording was never happening. The other three advisors keep nothing, so the
same question -- "has old-man ever been consulted?" -- cannot be answered from
the repository at all. Not by the operator, and not by the agent that is
supposed to be calling them.

A growth mechanism that cannot be audited cannot be known to be growing. This
module is the audit: an append-only log of consultations, and a `status` that
says plainly which advisors have never been asked anything.

Silence is a valid answer from an advisor. Silence from the LOG is not the
same thing, and the two were indistinguishable until this existed.
"""
from __future__ import unicode_literals

import argparse
import datetime
import io
import json
import os
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

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(SKILL_DIR, 'advisors')
STORE = os.path.join(STORE_DIR, 'consults.jsonl')

# The advisors this skill ships. Listing them here is what lets `status` report
# an advisor that has never been consulted -- a store alone can only show what
# DID happen, and the whole point is to see what did not.
KNOWN = ('old-man', 'question-monster', 'fast-finder', 'referee')


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


def load():
    """Every consultation ever recorded, oldest first."""
    if not os.path.isfile(STORE):
        return []
    rows = []
    with io.open(STORE, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue          # a torn line must not lose the rest
    return rows


def record(advisor, paper=None, asked=None, verdict=None, at=None):
    """Append one consultation. Returns the row written.

    Append-only on purpose: a consultation that turned out to be wrong is
    still evidence that the advisor was reached for, and rewriting history
    would hide exactly the pattern this is here to expose.
    """
    if advisor not in KNOWN:
        raise SystemExit('advisors: unknown advisor %r (known: %s)'
                         % (advisor, ', '.join(KNOWN)))
    row = {'advisor': advisor, 'at': at or _now()}
    for key, value in (('paper', paper), ('asked', asked),
                       ('verdict', verdict)):
        if value:
            row[key] = ' '.join(str(value).split())[:400]
    if not os.path.isdir(STORE_DIR):
        os.makedirs(STORE_DIR)
    with io.open(STORE, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    return row


def summary():
    """{advisor: {'count', 'last', 'papers'}} for every KNOWN advisor."""
    out = {name: {'count': 0, 'last': None, 'papers': set()}
           for name in KNOWN}
    for row in load():
        name = row.get('advisor')
        if name not in out:
            continue
        slot = out[name]
        slot['count'] += 1
        slot['last'] = row.get('at') or slot['last']
        if row.get('paper'):
            slot['papers'].add(row['paper'])
    return out


def installed_where(name):
    r"""Where a runtime would find this advisor, or None if nowhere.

    The advisors ship inside the skill, at `.claude/agents/` under the skill
    directory -- and that is NOT a location any runtime searches. It looks in
    the user's `~/.claude/agents/` and the project's `<cwd>/.claude/agents/`.
    So for the first ten papers the four advisors were not merely unused: they
    were unreachable, and nothing anywhere said so. "Never consulted" and
    "never installed" look identical from the log and need opposite fixes.
    """
    shipped = os.path.join(SKILL_DIR, '.claude', 'agents')
    candidates = [
        os.path.join(os.path.expanduser('~'), '.claude', 'agents',
                     '%s.md' % name),
        os.path.join(os.getcwd(), '.claude', 'agents', '%s.md' % name),
    ]
    for path in candidates:
        # The skill's OWN copy never counts. Running from the skill directory
        # makes `<cwd>/.claude/agents` the shipped folder itself, and reading
        # that as "installed" reported the precise state this is here to
        # catch as fine -- found in a clean room, where the only reason it
        # looked installed was that nothing had been installed.
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(shipped):
            continue
        if os.path.isfile(path):
            return path
    return None


def _referee_runs():
    """How many runs the referee SCRIPT has judged, or None if unknown.

    Being consulted as an advisor and tallying a run are different acts, and
    reporting `referee: never consulted` beside a runs.json holding thirteen
    rows reads as a contradiction. Say both.
    """
    path = os.path.join(SKILL_DIR, 'referee', 'runs.json')
    if not os.path.isfile(path):
        return None
    try:
        with io.open(path, 'r', encoding='utf-8') as fh:
            return len(json.load(fh).get('runs', []))
    except (ValueError, OSError):
        return None


def status_lines():
    """What `status` prints, as a list so the build can reuse it."""
    data = summary()
    never = [n for n in KNOWN if not data[n]['count']]
    uninstalled = [n for n in KNOWN if installed_where(n) is None]
    runs = _referee_runs()
    lines = []
    for name in KNOWN:
        slot = data[name]
        where = '' if installed_where(name) else '  [NOT INSTALLED]'
        if slot['count']:
            lines.append('   %-17s %3d consultation(s), %d paper(s), last %s%s'
                         % (name, slot['count'], len(slot['papers']),
                            slot['last'], where))
        else:
            note = ''
            if name == 'referee' and runs:
                note = ' as an advisor (its script has judged %d run(s))' % runs
            lines.append('   %-17s never consulted%s%s' % (name, note, where))
    if uninstalled:
        lines.append('')
        lines.append('%d advisor(s) are shipped but NOT INSTALLED: %s'
                     % (len(uninstalled), ', '.join(uninstalled)))
        lines.append('They live in the skill\'s own .claude/agents/, which no '
                     'runtime searches. Copy them to ~/.claude/agents/ (see '
                     'INSTALL.md) or they cannot be called at all.')
    if never:
        lines.append('')
        lines.append('%d advisor(s) have never been consulted: %s'
                     % (len(never), ', '.join(never)))
        lines.append('An advisor nobody calls is a document. Either it is '
                     'reached for on the next paper, or it should not ship.')
    return lines


def build_note():
    """One line for the end of a build, or None when there is nothing to say.

    The full table belongs to `status`; a build that printed it every time
    would be teaching the operator to skip the last seven lines of output.
    What a build must not let pass quietly is an advisor that has never been
    reached for -- that is the state nobody could see before this existed.
    """
    data = summary()
    never = [n for n in KNOWN if not data[n]['count']]
    uninstalled = [n for n in KNOWN if installed_where(n) is None]
    # Not installed is the louder of the two: an advisor nobody CAN call will
    # never be consulted no matter how willing the caller is, and for ten
    # papers that was the actual state.
    if uninstalled:
        return ('Advisors: %d of %d shipped but NOT INSTALLED (%s) — they '
                'cannot be called; see INSTALL.md'
                % (len(uninstalled), len(KNOWN), ', '.join(uninstalled)))
    if not never:
        return None
    return ('Advisors: %d of %d never consulted (%s) — '
            'python scripts/advisors.py status'
            % (len(never), len(KNOWN), ', '.join(never)))


def cmd_record(args):
    row = record(args.advisor, paper=args.paper, asked=args.asked,
                 verdict=args.verdict)
    print('Advisors: %s recorded (%d consultation(s) known)'
          % (row['advisor'], len(load())))
    return 0


def cmd_status(_args):
    print('Advisor consultations:')
    for line in status_lines():
        print(line)
    return 0


def cmd_history(args):
    rows = load()
    if args.advisor:
        rows = [r for r in rows if r.get('advisor') == args.advisor]
    if not rows:
        print('No consultation recorded%s.'
              % (' for %s' % args.advisor if args.advisor else ''))
        return 0
    for row in rows:
        print('%s  %-17s %s' % (row.get('at', '?'), row.get('advisor', '?'),
                                row.get('asked', '')[:90]))
        if row.get('verdict'):
            print('%s-> %s' % (' ' * 20, row['verdict'][:100]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd')

    rec = sub.add_parser('record', help='log one consultation')
    rec.add_argument('advisor', choices=list(KNOWN))
    rec.add_argument('--paper', default=None)
    rec.add_argument('--asked', default=None,
                     help='what the advisor was asked, in one line')
    rec.add_argument('--verdict', default=None,
                     help='what it answered, in one line')
    rec.set_defaults(func=cmd_record)

    st = sub.add_parser('status', help='who has and has not been consulted')
    st.set_defaults(func=cmd_status)

    hi = sub.add_parser('history', help='every consultation so far')
    hi.add_argument('--advisor', choices=list(KNOWN), default=None)
    hi.set_defaults(func=cmd_history)

    args = ap.parse_args()
    if not getattr(args, 'func', None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
