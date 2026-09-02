# -*- coding: utf-8 -*-
r"""Put the advisors where a runtime will actually find them.

The four advisor definitions ship inside this skill, at
`<skill>/.claude/agents/`. No runtime searches that path: sub-agents are
discovered in `~/.claude/agents/` and in `<project>/.claude/agents/`. Left
where they ship, the advisors cannot be called at all — which is the state the
first ten papers were translated in, with nothing anywhere reporting it.

Written as a script rather than a paragraph in INSTALL.md because the
paragraph is what was missing, and a step someone has to read and retype is a
step that gets skipped. Copying is deliberate over symlinking: a symlink into
a skill folder breaks the moment the skill is moved or upgraded, and it breaks
silently.

Safe to re-run. It never overwrites a file it did not put there.
"""
from __future__ import unicode_literals

import argparse
import filecmp
import io
import os
import shutil
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = os.path.join(SKILL_DIR, '.claude', 'agents')


def targets(project=None):
    """Where a runtime looks, most general first."""
    if project:
        return [os.path.join(os.path.abspath(project), '.claude', 'agents')]
    return [os.path.join(os.path.expanduser('~'), '.claude', 'agents')]


def shipped_agents():
    if not os.path.isdir(SHIPPED):
        return []
    return sorted(name for name in os.listdir(SHIPPED)
                  if name.endswith('.md'))


def _same(a, b):
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def install(dest, force=False, dry_run=False):
    """Returns (installed, up_to_date, conflicts) as lists of file names."""
    names = shipped_agents()
    if not names:
        raise SystemExit('install_advisors: nothing to install; %s is empty'
                         % SHIPPED)
    installed, up_to_date, conflicts = [], [], []
    for name in names:
        src = os.path.join(SHIPPED, name)
        dst = os.path.join(dest, name)
        if os.path.isfile(dst):
            if _same(src, dst):
                up_to_date.append(name)
                continue
            if not force:
                # Someone else's agent may already own this name. Overwriting
                # it silently would be a worse failure than not installing.
                conflicts.append(name)
                continue
        if not dry_run:
            if not os.path.isdir(dest):
                os.makedirs(dest)
            shutil.copyfile(src, dst)
        installed.append(name)
    return installed, up_to_date, conflicts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--project', default=None,
                    help='install into this project instead of the home '
                         'directory')
    ap.add_argument('--force', action='store_true',
                    help='replace a differing file of the same name')
    ap.add_argument('--dry-run', action='store_true',
                    help='say what would happen and change nothing')
    args = ap.parse_args()

    dest = targets(args.project)[0]
    installed, up_to_date, conflicts = install(dest, force=args.force,
                                               dry_run=args.dry_run)
    verb = 'would install' if args.dry_run else 'installed'
    print('Advisor definitions -> %s' % dest)
    for name in installed:
        print('   %s %s' % (verb, name))
    for name in up_to_date:
        print('   already current %s' % name)
    for name in conflicts:
        print('   CONFLICT %s already exists and differs — left alone; '
              'pass --force to replace it' % name)
    if not installed and not conflicts:
        print('   nothing to do')
    if conflicts:
        print()
        print('%d name(s) are already taken by a different agent. Rename or '
              'remove those, or re-run with --force.' % len(conflicts))
        return 1
    if installed and not args.dry_run:
        print()
        print('Restart Claude Code: sub-agents are read when a session starts.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
