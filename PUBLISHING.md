# Publishing this fork

This tree is a fork of [deusyu/translate-book](https://github.com/deusyu/translate-book),
MIT-licensed, published as
[kcy4334-lgtm/translate-book-arxiv](https://github.com/kcy4334-lgtm/translate-book-arxiv).

The preparation below is **done**. This document stays because the reasoning is
what makes it re-doable, by you on the next fork, or by anyone who forks this.

---

## What the licence requires: do not remove

`LICENSE` says `Copyright (c) 2025 Rainman`. MIT keeps that line: *"The above
copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software."* Deleting it is the one thing that turns
a permitted fork into an infringing one. It now reads:

```
Copyright (c) 2025 Rainman
Copyright (c) 2026 kcy4334-lgtm
```

The original comes first. Do not replace it, do not merge the two into one
line, do not change its year. `tests/test_source_lint.py` fails if it goes
missing.

## Done

| | Why it was not optional |
|---|---|
| **`.github/FUNDING.yml` deleted** | It read `github: deusyu`. GitHub renders that as a **Sponsor** button on *your* repository, sending other people's money to someone who does not maintain it. |
| **Install commands repointed** to `kcy4334-lgtm/translate-book-arxiv` | A README that tells readers to `npx skills add deusyu/translate-book` installs someone else's copy; they get a build with none of this tree's work. `README.md`, `AGENTS.md`, `CLAUDE.md`, `SKILL.md` (the installer reads its `homepage`). |
| **Lines that CITE upstream keep the name** | `deusyu/translate-book` is an address in an install command and a *name* in "a fork of …". A blanket replace turned the second into "a fork of *yours*", a repository forked from itself. Exempt: the README lineage note, the `Forked from` block, the ClawHub paragraph in `.claude/commands/release.md`. |
| **The upstream issue link is left alone** | Issue #7 lives in deusyu's tracker. Substituting it would make it a dead link to an issue number this repository does not have. |
| **Sponsor section removed** | Same problem as FUNDING.yml, and there is no correct owner to swap in until sponsorship is set up. |
| **Star History repointed** | It plots this repository now, which is honest. It starts empty. |
| **Title** `# Rainman Translate Book` → `# Translate Book: arXiv` | The upstream author's name was in the title. |
| **`README.zh-CN.md` removed** | The rule was "sync every README change to both". Carrying a translation nobody here can review means every future doc edit costs double in a language you cannot check, and it goes stale on the first one. Upstream keeps its Chinese README and serves that audience better. |
| **`assets/poster/` removed** | The poster images are built artefacts and still showed the old install command; regenerating them needs a separate skill. Dropping them is cheaper than keeping a picture that lies. |
| **ClawHub dropped from the release flow** | `.claude/commands/release.md` is now `git push` + tag. Upstream publishes to ClawHub under the name `translate-book`; publishing a fork under a name someone else owns is not ours to do. |

`finish_fork.py` did the mechanical part and ships with the tree, so this
document is executable rather than a list of instructions. It names
`deusyu/translate-book` because that is the string it replaces, and it skips
itself, `tests/test_source_lint.py` and this file, substituting inside any of
them would replace the very string they search for, and a second run would find
nothing and report success.

Verified: 1497 tests pass afterwards, and the README keeps its non-ASCII
characters intact.

## Still yours to do

The repository is initialised, `origin` points at
`kcy4334-lgtm/translate-book-arxiv`, and the first commit is on `main`. What is
left is the one step that makes it public, which is yours to press:

```bash
cd ~/.claude/skills/translate-book
git push -u origin main
```

Before pushing, `git log --stat -1` shows exactly what goes out. `.gitignore`
keeps `*_temp/` and `advisors/consults.jsonl` out, and those are the two that
matter: the first is gigabytes of intermediate build state, the second is a
record of who consulted whom on this machine.

`.gitattributes` pins every text file to LF in the repository *and* in the
working copy. That is not tidiness. `normalize_newlines` in
`scripts/arxiv_backend.py` exists because a CRLF surviving into pandoc's output
is written back as `\r\r\n`, which reads as a blank line, and a blank line
inside `$$` display maths ends the formula, swallowing the prose after it. CI
runs on Ubuntu, so a Windows checkout that differed in line endings would be a
build nobody could reproduce.

## What is already correct

- `.gitignore` excludes `advisors/consults.jsonl`: who consulted whom on this
  machine. Shipping it would tell a recipient that old-man has been consulted
  once when they have consulted nobody, hiding the exact state
  `advisors.py status` exists to show.
- `corpus/shapes.json`, `referee/runs.json`, `KNOWLEDGE.md`, `KNOWHOW.md` and
  `REFEREE.md` DO ship: they are the growth stores, and a fork without them is
  the upstream skill again.
- `.github/workflows/ci.yml` runs `python -m unittest discover -s tests -p
  'test_*.py'` on stdlib only. No secrets, no network.
- No file names a personal absolute path, `tests/test_source_lint.py` enforces
  that, and it caught one in `finish_fork.py` while this was being written.
