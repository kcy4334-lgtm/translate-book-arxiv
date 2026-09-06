# -*- coding: utf-8 -*-
r"""What went wrong across a whole run, and whether it went wrong before.

`verify_chunk` judges ONE chunk against its source and fails it. That is the
right unit for rejecting work and the wrong unit for noticing anything: a
defect that fires once is an accident, the same defect on five of eighteen
chunks is a briefing fault, and the same defect in three consecutive books is
something nobody has fixed.

None of those is visible from inside a chunk. This aggregates instead:

    python scripts/referee.py tally <temp_dir> --lang ko   # this run, judged
    python scripts/referee.py record <temp_dir> --lang ko  # and remember it
    python scripts/referee.py history                      # every run so far

The judgement it makes is deliberately narrow — counting and comparing, which
a script can do exactly. Everything that needs an opinion (is this the agent's
fault or the pipeline's? does it deserve a card?) belongs to the `referee`
agent, which reads this and `REFEREE.md`.

Stdlib only.
"""
import argparse
import io
import json
import os
import subprocess
import sys

if sys.platform == 'win32':
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(SKILL_DIR, 'referee', 'runs.json')

# Above this share of a run's chunks, a defect stops being a few agents
# slipping and becomes the brief being wrong. Every instance of a role reads
# the same prompt, so when most of them make one mistake, the prompt made it.
BRIEF_FAULT_SHARE = 0.30
# Fired in this many runs (including this one) and it is not a slip any more.
CHRONIC_RUNS = 3


def load():
    if not os.path.isfile(STORE):
        return {'version': 1, 'runs': []}
    try:
        with io.open(STORE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (ValueError, IOError):
        return {'version': 1, 'runs': []}
    data.setdefault('runs', [])
    return data


def save(data):
    folder = os.path.dirname(STORE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = STORE + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1,
                            sort_keys=True))
    if os.path.exists(STORE):
        os.remove(STORE)
    os.rename(tmp, STORE)


def paper_of(temp_dir):
    try:
        import corpus_census
        return corpus_census.paper_id(temp_dir)
    except Exception:
        return os.path.basename(os.path.abspath(temp_dir))


def collect(temp_dir, lang):
    """Run verify_chunk and fold its per-chunk report into per-check counts."""
    cmd = [sys.executable, os.path.join(SKILL_DIR, 'scripts',
                                        'verify_chunk.py'),
           temp_dir, '--lang', lang, '--json']
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        raise SystemExit('referee: verify_chunk gave no JSON.\n%s'
                         % (proc.stderr or proc.stdout)[:800])
    results = report.get('results', [])
    checks = {}
    for row in results:
        for finding in row.get('findings', []):
            key = finding.get('check', '?')
            slot = checks.setdefault(key, {'severity': finding.get('severity',
                                                                   'fail'),
                                           'chunks': []})
            if row['chunk'] not in slot['chunks']:
                slot['chunks'].append(row['chunk'])
    return {'paper': paper_of(temp_dir), 'lang': lang,
            'chunks': len(results),
            'failed': sum(1 for r in results if not r.get('ok', True)),
            'checks': checks}


def judge(run, history):
    """What this run's numbers mean, said in the few ways a count can mean."""
    lines, flags = [], []
    total = max(1, run['chunks'])
    seen_before = {}
    for old in history:
        for key in old.get('checks', {}):
            seen_before.setdefault(key, []).append(old.get('paper', '?'))

    if not run['checks']:
        lines.append('%s: %d chunk(s), nothing fired.'
                     % (run['paper'], run['chunks']))
        return lines, flags

    lines.append('%s: %d chunk(s), %d failed.'
                 % (run['paper'], run['chunks'], run['failed']))
    for key in sorted(run['checks'],
                      key=lambda k: -len(run['checks'][k]['chunks'])):
        slot = run['checks'][key]
        n = len(slot['chunks'])
        share = float(n) / total
        where = ', '.join(slot['chunks'][:6])
        if n > 6:
            where += ', +%d more' % (n - 6)
        note = ''
        if share >= BRIEF_FAULT_SHARE and n > 1:
            note = '  <-- %d of %d: read this as the BRIEF, not the agents' \
                   % (n, total)
            flags.append(('brief', key, n, total))
        papers = seen_before.get(key, [])
        if len(papers) + 1 >= CHRONIC_RUNS:
            note += '  <-- also in %s' % ', '.join(sorted(set(papers)))
            flags.append(('chronic', key, len(papers) + 1, total))
        elif papers:
            note += '  (seen before in %s)' % ', '.join(sorted(set(papers)))
        lines.append('   %-20s %-8s %d chunk(s): %s%s'
                     % (key, slot['severity'], n, where, note))
    return lines, flags


def edition_of(run):
    r"""What counts as the same run coming round again.

    The paper alone did, and one paper's two language editions then shared a
    single row. DeeR-VLA was translated into Korean and then Chinese in one
    session; the Chinese row replaced the Korean one, and what it erased was
    the Korean run's `meta_evidence` firing on five chunks of eight -- past
    BRIEF_FAULT_SHARE, the exact shape this store exists to remember.

    A second edition is not a re-run. It has its own brief, its own glossary
    and its own agents, so it votes on its own. And a defect that appears in
    BOTH editions of one paper is the most useful repeat there is: it says
    the fault is in the brief or the tool rather than in the language.
    """
    return (run.get('paper'), run.get('lang'))


def cmd_tally(args):
    run = collect(args.temp_dir, args.lang)
    data = load()
    # This edition's own earlier row is not history: comparing a run against
    # itself reports every defect as a repeat, which is the one thing a
    # repeat-detector must never do. Another edition of the same paper is
    # history, and the most informative kind.
    history = [r for r in data['runs'] if edition_of(r) != edition_of(run)]
    lines, flags = judge(run, history)
    for line in lines:
        print(line)
    if flags:
        print()
        for kind, key, n, total in flags:
            if kind == 'brief':
                print('BRIEF: `%s` fired on %d of %d chunks. Every instance '
                      'of a role reads the same prompt; fix the prompt before '
                      'you fault the agents.' % (key, n, total))
            else:
                print('CHRONIC: `%s` has now fired in %d runs. Whatever it is, '
                      'nobody has fixed it — it belongs in KNOWLEDGE, not in '
                      'another re-translation.' % (key, n))
    if args.json:
        print(json.dumps(run, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


def cmd_record(args):
    run = collect(args.temp_dir, args.lang)
    data = load()
    # One row per paper AND language: a re-run replaces its own row rather
    # than voting twice, or a book re-translated five times would look like an
    # epidemic. A different language edition is not a re-run and keeps its own
    # row -- see `edition_of`.
    data['runs'] = [r for r in data['runs']
                    if edition_of(r) != edition_of(run)]
    data['runs'].append(run)
    save(data)
    print('Referee: %s recorded (%d run(s) known, %d check(s) this run)'
          % (run['paper'], len(data['runs']), len(run['checks'])))
    return 0


def cmd_history(args):
    data = load()
    if not data['runs']:
        print('No run recorded yet.')
        return 0
    print('%d run(s): %s' % (len(data['runs']),
                             ', '.join(sorted(r.get('paper', '?')
                                              for r in data['runs']))))
    tally = {}
    for run in data['runs']:
        for key, slot in run.get('checks', {}).items():
            row = tally.setdefault(key, {'runs': [], 'chunks': 0})
            row['runs'].append(run.get('paper', '?'))
            row['chunks'] += len(slot['chunks'])
    if not tally:
        print('Nothing has ever fired.')
        return 0
    print()
    print('%-20s %6s %8s  %s' % ('check', 'runs', 'chunks', 'papers'))
    for key in sorted(tally, key=lambda k: (-len(tally[k]['runs']), k)):
        row = tally[key]
        print('%-20s %6d %8d  %s' % (key, len(row['runs']), row['chunks'],
                                     ', '.join(sorted(set(row['runs'])))))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd')
    for name, helptext in (('tally', 'judge this run without recording it'),
                           ('record', 'judge it and remember it')):
        p = sub.add_parser(name, help=helptext)
        p.add_argument('temp_dir')
        p.add_argument('--lang', default='ko')
        if name == 'tally':
            p.add_argument('--json', action='store_true')
    sub.add_parser('history', help='every check that has ever fired')
    args = ap.parse_args()

    handlers = {'tally': cmd_tally, 'record': cmd_record,
                'history': cmd_history}
    if args.cmd in handlers:
        return handlers[args.cmd](args)
    ap.print_help()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
