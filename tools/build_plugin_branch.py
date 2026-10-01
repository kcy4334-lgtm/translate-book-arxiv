# -*- coding: utf-8 -*-
r"""Build the `claude-plugin` branch that Anthropic's plugin directory follows.

The directory installs a plugin folder as it stands in a GitHub branch, and it
holds the folder to limits this repository's main branch does not meet: no
file over 5 MiB (`tests/baselines/standard-alice.epub` is 10.6 MB, and a file
that size stops validation outright), binaries such as EPUB held for a human
reviewer, a `.claude-plugin/plugin.json` at the root. Main keeps all of that,
because the tests need it. This script writes a second branch from a release
tag: the files the skill runs on, plus the manifest, and nothing else.

It works on git objects only. The working tree, the index and the checked-out
branch are never touched, so it is safe to run with uncommitted work.

    python tools/build_plugin_branch.py              # newest tag -> claude-plugin
    python tools/build_plugin_branch.py --ref v0.4.3
    python tools/build_plugin_branch.py --export <dir> --no-commit
                                                     # look before committing

Then `git push origin claude-plugin`. The directory picks the commit up from
there; the version it shows is the tag's.

Why from a tag and not from main: the tag is the only version anchor in this
repository (see `.claude/commands/release.md`), and the directory asks for the
manifest's `version` to rise with every release. A build from an untagged
commit would have no honest version to give it.
"""
from __future__ import unicode_literals

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BRANCH = 'claude-plugin'
PLUGIN_NAME = 'translate-book-arxiv'
REPO_URL = 'https://github.com/kcy4334-lgtm/translate-book-arxiv'

# Development-only files. Everything else at the tag ships, so a new runtime
# file cannot be forgotten; a new development file has to be added here.
# PUBLISHING.md and .claude/commands/release.md stay in: the shipped test
# suite checks that both exist, and the plugin folder should pass its own
# tests (PUBLISHING.md is also where the fork's licence obligations live).
EXCLUDE_PREFIXES = (
    'tests/baselines/',      # test books; one is over the directory's 5 MiB limit
    '.github/',              # CI for this repository
    'tools/',                # this script
)
EXCLUDE_FILES = {'CLAUDE.md', 'AGENTS.md', 'finish_fork.py'}

# The directory's limits, from its pre-submission checklist.
MAX_FILE_BYTES = 5 * 1024 * 1024          # over this, validation stops
REVIEW_TEXT_BYTES = 256 * 1024            # over this, a version is held for a reviewer
MAX_FILES = 512                           # over this, held for a reviewer
IMAGE_OR_FONT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
                 '.ttf', '.otf', '.woff', '.woff2')
# Binaries the directory holds for a reviewer. None of them is needed to run
# the skill, so finding one is a mistake in EXCLUDE_*, not something to ship.
HELD_BINARIES = ('.epub', '.pdf', '.zip', '.ico', '.bin', '.docx', '.exe',
                 '.dll', '.so', '.dylib', '.pyc')
SYSTEM_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


def git(*args, **kw):
    """Run git in the repository and return stdout as bytes."""
    env = kw.pop('env', None)
    data = kw.pop('input', None)
    proc = subprocess.run(('git',) + args, cwd=ROOT, input=data, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit('git %s failed:\n%s'
                         % (' '.join(args), proc.stderr.decode('utf-8', 'replace')))
    return proc.stdout


def git_text(*args, **kw):
    return git(*args, **kw).decode('utf-8').strip()


def resolve_tag(ref):
    if ref is None:
        ref = git_text('describe', '--tags', '--abbrev=0', 'HEAD')
    if not re.match(r'^v\d+\.\d+\.\d+$', ref):
        raise SystemExit('%s is not a release tag (vMAJOR.MINOR.PATCH)' % ref)
    git('rev-parse', '--verify', '-q', 'refs/tags/%s' % ref)
    return ref, ref[1:]


def tree_entries(ref):
    """(mode, sha, size, path) for every blob at `ref`."""
    out = git('ls-tree', '-r', '-z', '--long', ref).decode('utf-8')
    entries = []
    for record in out.split('\0'):
        if not record:
            continue
        meta, path = record.split('\t', 1)
        mode, kind, sha, size = meta.split()
        if kind != 'blob':
            raise SystemExit('%s is a %s; the directory accepts regular files only'
                             % (path, kind))
        entries.append((mode, sha, int(size), path))
    return entries


def is_excluded(path):
    return path in EXCLUDE_FILES or path.startswith(EXCLUDE_PREFIXES)


def check(entries):
    """Refuse what the directory would refuse; list what it would hold."""
    errors, held = [], []
    for mode, _sha, size, path in entries:
        name = path.rsplit('/', 1)[-1]
        ext = os.path.splitext(name)[1].lower()
        if mode == '120000':
            errors.append('%s is a symbolic link' % path)
        if name in SYSTEM_FILES or path.startswith('__MACOSX/'):
            errors.append('%s is a system file' % path)
        if size > MAX_FILE_BYTES:
            errors.append('%s is %s bytes, over the 5 MiB limit' % (path, format(size, ',')))
        if ext in HELD_BINARIES:
            errors.append('%s is a binary the directory would hold; exclude it' % path)
        elif ext not in IMAGE_OR_FONT and size > REVIEW_TEXT_BYTES:
            held.append('%s (%s bytes)' % (path, format(size, ',')))
    if len(entries) > MAX_FILES:
        held.append('%d files, over %d' % (len(entries), MAX_FILES))
    return errors, held


def skill_description(ref):
    text = git('show', '%s:SKILL.md' % ref).decode('utf-8')
    m = re.search(r'^description:\s*(.+?)\s*$', text, re.M)
    if not m:
        raise SystemExit('SKILL.md at %s has no description line' % ref)
    return m.group(1)


def manifest(version, description):
    data = {
        'name': PLUGIN_NAME,
        'displayName': 'Translate Book: arXiv',
        'version': version,
        'description': description,
        'author': {'name': 'kcy4334-lgtm', 'url': 'https://github.com/kcy4334-lgtm'},
        'homepage': REPO_URL,
        'repository': REPO_URL,
        # Read by Anthropic's directory, not by Claude Code (which strips
        # unknown keys). Without supportUrl the directory took the first
        # issues link in the README, which is the upstream project's.
        'supportUrl': REPO_URL + '/issues',
        'documentationUrl': REPO_URL + '#readme',
        # The README section that lists everything the skill reads, fetches,
        # sends and writes; the directory's compliance step asks the submitter
        # to confirm the privacy policy describes exactly that.
        'privacyPolicyUrl': REPO_URL + '#what-it-runs-fetches-and-writes',
        'license': 'MIT',
        'keywords': ['translation', 'arxiv', 'latex', 'pdf', 'epub',
                     'academic-papers', 'multilingual'],
    }
    return (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def build_tree(entries, manifest_bytes):
    """Write a tree object from `entries` plus the manifest, via a scratch index."""
    manifest_sha = git_text('hash-object', '-w', '--stdin', input=manifest_bytes)
    fd, index = tempfile.mkstemp(prefix='plugin-index-')
    os.close(fd)
    os.remove(index)        # git creates it; an empty file is not a valid index
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        git('read-tree', '--empty', env=env)
        lines = ['%s %s\t%s' % (mode, sha, path) for mode, sha, _size, path in entries]
        lines.append('100644 %s\t.claude-plugin/plugin.json' % manifest_sha)
        git('update-index', '--add', '--index-info',
            input=('\n'.join(lines) + '\n').encode('utf-8'), env=env)
        return git_text('write-tree', env=env)
    finally:
        if os.path.exists(index):
            os.remove(index)


def export(tree, target):
    os.makedirs(target, exist_ok=True)
    if os.listdir(target):
        raise SystemExit('%s is not empty' % target)
    data = git('archive', '--format=tar', tree)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        # 'data' refuses links and paths outside `target`; Pythons before 3.12
        # have no filters, and the archive is our own tree object.
        if hasattr(tarfile, 'data_filter'):
            tar.extractall(target, filter='data')
        else:
            tar.extractall(target)


def commit(tree, tag, tag_sha, version):
    parent = None
    probe = subprocess.run(('git', 'rev-parse', '--verify', '-q', 'refs/heads/%s' % BRANCH),
                           cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if probe.returncode == 0:
        parent = probe.stdout.decode('utf-8').strip()
        if git_text('rev-parse', '%s^{tree}' % parent) == tree:
            print('%s already holds this build (%s); nothing to commit' % (BRANCH, parent[:7]))
            return parent
    message = ('%s %s for the Claude plugin directory\n\n'
               'Built from %s (%s) by tools/build_plugin_branch.py.\n'
               % (PLUGIN_NAME, version, tag, tag_sha[:7]))
    args = ['commit-tree', tree, '-m', message]
    if parent:
        args[2:2] = ['-p', parent]
    new = git_text(*args)
    git('update-ref', 'refs/heads/%s' % BRANCH, new, *([parent] if parent else []))
    return new


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the claude-plugin branch from a release tag')
    ap.add_argument('--ref', help='release tag to build from (default: the newest tag)')
    ap.add_argument('--export', metavar='DIR', help='also write the plugin folder to an empty DIR')
    ap.add_argument('--no-commit', action='store_true', help='build and check, but leave the branch alone')
    args = ap.parse_args(argv)

    tag, version = resolve_tag(args.ref)
    tag_sha = git_text('rev-parse', '%s^{commit}' % tag)
    entries = [e for e in tree_entries(tag) if not is_excluded(e[3])]

    errors, held = check(entries)
    if errors:
        raise SystemExit('Not building; the directory would refuse this:\n  '
                         + '\n  '.join(errors))

    tree = build_tree(entries, manifest(version, skill_description(tag)))
    print('%s %s from %s: %d files + .claude-plugin/plugin.json'
          % (PLUGIN_NAME, version, tag, len(entries)))
    for item in held:
        print('  held for a reviewer: %s' % item)
    if args.export:
        export(tree, args.export)
        print('exported to %s' % args.export)
    if args.no_commit:
        print('tree %s (not committed)' % tree)
        return 0
    new = commit(tree, tag, tag_sha, version)
    print('%s -> %s. Push it with: git push origin %s' % (BRANCH, new[:7], BRANCH))
    return 0


if __name__ == '__main__':
    sys.exit(main())
