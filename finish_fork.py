# -*- coding: utf-8 -*-
r"""Finish the fork: one command, once the GitHub account name is known.

    python finish_fork.py <github-username> [--dry-run] [--root <dir>]

Decisions already made:
  repo name  translate-book-arxiv
  copyright  the GitHub account name, added BESIDE the upstream line

What it does, and why each one is not optional:

  * Every `deusyu/translate-book` becomes `<owner>/translate-book-arxiv` —
    install commands on your README that install someone else's copy are the
    worst of the lot, because a reader following them gets a build without any
    of this tree's work.
  * The upstream ISSUE link is put back. It points into deusyu's tracker and
    that is where issue #7 actually lives; substituting it would make it a
    dead link to an issue number your repository does not have.
  * The Sponsor section goes entirely. A badge keyed to `deusyu` on your
    repository sends other people's money to someone who does not maintain it,
    and there is no correct owner to swap in until you set sponsorship up.
  * The Star History chart is repointed rather than removed: it plots your
    repository, which is honest, and starts empty.
  * `# Rainman Translate Book` is the upstream author's name in your title.
  * LICENSE keeps `Copyright (c) 2025 Rainman` — that is MIT's one condition —
    and gains yours underneath.
  * A "Forked from" line goes at the top of both READMEs. GitHub shows the
    fork banner anyway; saying it in the text costs a sentence and makes the
    divergence legible to anyone comparing the two.

Both READMEs are edited together, because they are kept in sync.
"""
import argparse
import io
import os
import re
import sys

OLD = 'deusyu/translate-book'
REPO = 'translate-book-arxiv'
UPSTREAM_URL = 'https://github.com/deusyu/translate-book'

FORK_EN = (
    '> Forked from [deusyu/translate-book](%s). This fork develops the arXiv\n'
    '> LaTeX-source path: the numbering read from the paper itself, the\n'
    '> macro and float handling, and the knowledge, know-how and referee logs\n'
    '> that ship with it.\n' % UPSTREAM_URL)
FORK_ZH = (
    '> Fork 自 [deusyu/translate-book](%s)。本分支主要发展 arXiv LaTeX 源\n'
    '> 路径：从论文本身读取的编号、宏与浮动体处理，以及随包发布的\n'
    '> knowledge / know-how / referee 记录。\n' % UPSTREAM_URL)

SPONSOR_EN = re.compile(
    r'\n## Sponsor\n.*?(?=\n## )', re.DOTALL)
SPONSOR_ZH = re.compile(
    r'\n## 赞助\n.*?(?=\n## )', re.DOTALL)
ISSUE_RE = re.compile(r'https://github\.com/[^/\s)]+/%s/issues/' % REPO)
# A line that CITES upstream rather than addressing it. These keep the name.
_ATTRIBUTION_RE = re.compile(
    r'^\s*>?\s*(?:Lineage:|Forked from|Fork 自|谱系：)'
    r'|fork of|Upstream|upstream')


def edit(path, fn, changes, dry):
    if not os.path.isfile(path):
        return
    with io.open(path, encoding='utf-8') as fh:
        before = fh.read()
    after = fn(before)
    if after == before:
        return
    changes.append(os.path.relpath(path, ROOT).replace('\\', '/'))
    if not dry:
        with io.open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(after)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('owner')
    ap.add_argument('--dry-run', action='store_true')
    # The tree this script sits in. A resolved path would work on one machine
    # only, which `tests/test_source_lint.py` refuses for anything shipped.
    ap.add_argument('--root',
                    default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()

    global ROOT
    ROOT = args.root
    new = '%s/%s' % (args.owner, REPO)
    changes = []

    def substitute(text):
        # Line by line, because `deusyu/translate-book` is two different things
        # depending on where it stands. As an ADDRESS — an install command, a
        # clone URL, a homepage — it has to become yours, or the README tells
        # readers to install someone else's copy. As a NAME being cited, it is
        # attribution and must stay: a blanket replace turned "a fork of
        # deusyu/translate-book" into "a fork of <yours>", which says the
        # repository is a fork of itself.
        out = []
        for line in text.split('\n'):
            if _ATTRIBUTION_RE.search(line):
                out.append(line)
                continue
            out.append(line.replace(OLD, new))
        text = '\n'.join(out)
        # The issue tracker is upstream's too, and #7 lives there.
        return ISSUE_RE.sub('%s/issues/' % UPSTREAM_URL, text)

    for root, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in ('__pycache__', '.git') and not d.endswith('_temp')]
        for name in sorted(names):
            if not name.endswith(('.md', '.py', '.yml', '.yaml', '.page',
                                  '.json', '.txt')):
                continue
            path = os.path.join(root, name)
            # Never rewrite this file, the lint that guards it, or the document
            # that describes the change. Substituting inside the script would
            # replace the very string it searches for, so a second run — or a
            # re-fork — would find nothing and report success.
            # `test_source_lint.py` holds `_UPSTREAM = 'deusyu'` for the same
            # reason, and PUBLISHING.md is *about* upstream throughout.
            if os.path.abspath(path) == os.path.abspath(__file__) \
                    or name in ('test_source_lint.py', 'PUBLISHING.md'):
                continue
            edit(path, substitute, changes, args.dry_run)

    def readme_en(text):
        text = text.replace('# Rainman Translate Book\n',
                            '# Translate Book — arXiv\n', 1)
        if 'Forked from [deusyu/translate-book]' not in text:
            text = text.replace('\n---\n', '\n' + FORK_EN + '\n---\n', 1)
        return SPONSOR_EN.sub('\n', text)

    def readme_zh(text):
        text = text.replace('# Rainman Translate Book\n',
                            '# Translate Book — arXiv\n', 1)
        if 'Fork 自 [deusyu/translate-book]' not in text:
            text = text.replace('\n---\n', '\n' + FORK_ZH + '\n---\n', 1)
        return SPONSOR_ZH.sub('\n', text)

    edit(os.path.join(ROOT, 'README.md'), readme_en, changes, args.dry_run)
    edit(os.path.join(ROOT, 'README.zh-CN.md'), readme_zh, changes,
         args.dry_run)

    def licence(text):
        line = 'Copyright (c) 2026 %s\n' % args.owner
        if line in text:
            return text
        return text.replace('Copyright (c) 2025 Rainman\n',
                            'Copyright (c) 2025 Rainman\n' + line, 1)

    edit(os.path.join(ROOT, 'LICENSE'), licence, changes, args.dry_run)

    print('%s%d file(s)' % ('[dry run] ' if args.dry_run else '',
                            len(set(changes))))
    for rel in sorted(set(changes)):
        print('   %s' % rel)

    left = []
    for root, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in ('__pycache__', '.git') and not d.endswith('_temp')]
        for name in sorted(names):
            p = os.path.join(root, name)
            if not name.endswith(('.md', '.py', '.yml', '.page', '.json')):
                continue
            try:
                with io.open(p, encoding='utf-8', errors='replace') as fh:
                    body = fh.read()
            except OSError:
                continue
            for m in re.finditer(r'deusyu', body):
                ln = body[:m.start()].count('\n') + 1
                ctx = ' '.join(body[max(0, m.start() - 46):m.start() + 40].split())
                left.append('%s:%d %s'
                            % (os.path.relpath(p, ROOT).replace('\\', '/'),
                               ln, ctx))
    print()
    print('remaining mentions of the upstream owner: %d' % len(left))
    for line in left:
        print('   %s' % line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
