# -*- coding: utf-8 -*-
r"""Run the corpus with one version of the skill, and compare two runs.

    python tools/corpus_compare.py run  <papers.json> <out_dir> [--ref v0.4.9] [--workers 3]
    python tools/corpus_compare.py diff <out_a> <out_b>

`run` converts every paper from its cached arXiv e-print (nothing is
downloaded), builds it with `tests/dry_run.py`, and runs the five probes on
the result. Each paper's logs land in `<out_dir>/<name>/`.

The code it runs is the version named by `--ref` (default HEAD), unpacked
with `git archive` into `<out_dir>/_tree`. Running from the working copy
instead would rewrite `corpus/shapes.json` and `referee/runs.json` there,
because every build records itself, and would test uncommitted edits.

`diff` prints, paper by paper, the lines of the probe logs that changed and
how many lines of `input.md` moved. Run the old version and the new one into
two folders and diff them; a paper reading `same` was not touched.

`papers.json` is a list of papers on this machine, so it is not in the
repository: the PDFs are other people's work.

    [{"name": "AlphaQ", "id": "2606.04980",
      "pdf": "/papers/AlphaQ.pdf",
      "eprint": "/papers/AlphaQ_temp/eprint_2606.04980.bin"}, ...]

`eprint` is the file the arXiv backend caches on its first run.

v0.5.0 was checked this way on 28 papers against v0.4.9 (KNOWLEDGE K229).
Development only; the plugin does not ship tools/.
"""
import argparse
import concurrent.futures
import difflib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBES = ('source_probe', 'table_probe', 'inventory_probe', 'leak_probe',
          'format_probe')
LOGS = ('convert', 'dry') + PROBES
# The lines of a log worth comparing: counts, verdicts and findings, not the
# progress chatter that changes with every run.
KEY = re.compile(r'^\s*(Sections|Figures|Tables|Equations|References|Authors?|'
                 r'WARNING|ERROR|BLOCKING|FAIL|PASS|warning|sections|equations|'
                 r'float numbers|tables compared|source tabulars|tokens carrying|'
                 r'\d+ finding|bibliography entries|figures |tables |numbered eq)')
ENV = dict(os.environ, PYTHONIOENCODING='utf-8')


def unpack(ref, target):
    """The tree at `ref`, written to `target`."""
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)
    data = subprocess.run(['git', 'archive', '--format=tar', ref], cwd=ROOT,
                          stdout=subprocess.PIPE, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        if hasattr(tarfile, 'data_filter'):
            tar.extractall(target, filter='data')
        else:
            tar.extractall(target)


def _run(cmd, cwd, log):
    with open(log, 'w', encoding='utf-8') as fh:
        return subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                              env=ENV, timeout=1800).returncode


def one(paper, tree, out):
    name = paper['name']
    work = os.path.join(out, name)
    os.makedirs(work, exist_ok=True)
    shutil.copy2(paper['pdf'], os.path.join(work, name + '.pdf'))
    temp = os.path.join(work, name + '_temp')
    os.makedirs(temp, exist_ok=True)
    shutil.copy2(paper['eprint'], os.path.join(
        temp, 'eprint_%s.bin' % paper['id'].replace('/', '_')))
    result = {'convert': _run(
        [sys.executable, os.path.join(tree, 'scripts', 'convert.py'),
         name + '.pdf', '--olang', 'ko', '--arxiv-id', paper['id'],
         '--allow-network'], work, os.path.join(work, 'convert.log'))}
    if result['convert']:
        return name, result
    result['dry'] = _run(
        [sys.executable, os.path.join(tree, 'tests', 'dry_run.py'), temp,
         '--lang', 'ko', '--keep'], work, os.path.join(work, 'dry.log'))
    built = os.path.basename(temp) + '_dryrun'
    for probe in PROBES:
        _run([sys.executable, os.path.join(tree, 'tests', probe + '.py'),
              built], work, os.path.join(work, probe + '.log'))
    return name, result


def cmd_run(args):
    papers = json.load(open(args.papers, encoding='utf-8'))
    out = os.path.abspath(args.out)
    tree = os.path.join(out, '_tree')
    unpack(args.ref, tree)
    results = {}
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        for name, res in pool.map(lambda p: one(p, tree, out), papers):
            results[name] = res
            print(name, res, flush=True)
    with open(os.path.join(out, 'results.json'), 'w') as fh:
        json.dump(results, fh, indent=1)
    return 0


def key_lines(path):
    if not os.path.exists(path):
        return ['<missing>']
    text = open(path, encoding='utf-8', errors='replace').read()
    # Each run lives in its own folder; its name is not a difference.
    text = re.sub(r'[\w.:\\/-]*_tree\b', '<tree>', text)
    return [line.rstrip() for line in text.splitlines() if KEY.match(line)]


def changed(a, b):
    return [d for d in difflib.unified_diff(a, b, lineterm='', n=0)
            if d[:1] in '+-' and not d.startswith(('+++', '---'))]


def cmd_diff(args):
    def papers(folder):
        return {n for n in os.listdir(folder)
                if os.path.isdir(os.path.join(folder, n)) and n != '_tree'}

    a, b = papers(args.a), papers(args.b)
    if a ^ b:
        print('in one run only: %s' % ', '.join(sorted(a ^ b)))
    for name in sorted(a & b):
        out = []
        for log in LOGS:
            lines = changed(key_lines(os.path.join(args.a, name, log + '.log')),
                            key_lines(os.path.join(args.b, name, log + '.log')))
            if lines:
                out.append('  [%s]' % log)
                out.extend('    ' + line[:170] for line in lines[:14])
        md = [os.path.join(d, name, name + '_temp', 'input.md')
              for d in (args.a, args.b)]
        moved = len(changed(*[open(p, encoding='utf-8', errors='replace')
                              .read().splitlines() if os.path.exists(p) else []
                              for p in md]))
        print('== %s  (input.md lines changed: %d)' % (name, moved))
        print('\n'.join(out) if out else '  same')
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='convert, build and probe every paper')
    r.add_argument('papers')
    r.add_argument('out')
    r.add_argument('--ref', default='HEAD', help='tag or commit to run')
    r.add_argument('--workers', type=int, default=3)
    d = sub.add_parser('diff', help='what changed between two runs')
    d.add_argument('a')
    d.add_argument('b')
    args = ap.parse_args(argv)
    return cmd_run(args) if args.cmd == 'run' else cmd_diff(args)


if __name__ == '__main__':
    raise SystemExit(main())
