# Installing this skill

This turns a folder into a Claude Code skill by placing it where Claude Code
looks for skills, then confirms your machine can actually reproduce the
output (same layout, same fonts, same page count) not just run the scripts
without crashing.

## 1. Unpack

Unzip this archive. You get one folder: `translate-book/`.

## 2. Place it

Move (don't copy, one location is enough) the `translate-book/` folder into
your Claude Code skills directory:

| OS | Path |
|---|---|
| Windows | `%USERPROFILE%\.claude\skills\translate-book\` |
| macOS / Linux | `~/.claude/skills/translate-book/` |

If `skills` doesn't exist yet, create it. The result should be
`~/.claude/skills/translate-book/SKILL.md` (not
`~/.claude/skills/translate-book/translate-book/SKILL.md`: unzip one level,
don't nest it).

To use it in one specific project instead of everywhere, place it under that
project's `.claude/skills/translate-book/` instead of the home directory.

## 2b. Install the advisors; they do NOT travel with the skill

Four advisor sub-agents ship inside this folder at
`translate-book/.claude/agents/`. **No runtime searches that path.** Claude
Code looks for sub-agents in your home directory and in the project you are
working in (never inside a skill) so left where they are, the four cannot be
called at all. Copy them out:

From the skill folder, run:

```
python scripts/install_advisors.py
```

It copies the four definitions into `~/.claude/agents/`, is safe to re-run,
and refuses to overwrite a file of the same name it did not put there: if you
already have an agent called `referee`, it says so and leaves yours alone
rather than silently replacing it. `--force` overrides that; `--dry-run` shows
what would happen; `--project <path>` installs into one project instead of your
home directory.

Then confirm:

```
python scripts/advisors.py status
```

It names any advisor it cannot find, and every build prints the same warning
until they are installed. This step was missing from earlier versions of these
instructions, and the cost was invisible rather than loud: ten papers were
translated with `old-man`, `question-monster` and `fast-finder` unreachable,
and nothing anywhere reported it; an advisor that is never installed and one
that is simply never called leave exactly the same trace, which is none.

A newly copied agent is picked up when a session starts, so restart Claude
Code before expecting to call them.

## 3. Install the external tools

This skill's own code is the smallest part of what decides its output. It
converts files with **pandoc**, prints PDFs with **Chromium**, produces EPUB
with **Calibre**, and measures its own output with **PyMuPDF**: none of
which travel inside a zip. Install:

- **Python 3.8+**: <https://www.python.org/downloads/>
- **Pandoc**: <https://pandoc.org/installing.html>
- **Chromium, Google Chrome, or Microsoft Edge**: any one; the skill finds
  whichever is installed. Set the environment variable
  `TRANSLATE_BOOK_CHROME` to a browser binary's path if you have one
  installed somewhere unusual.
- **Calibre** (for the `ebook-convert` command), <https://calibre-ebook.com/>
- Two Python packages:
  ```bash
  pip install pymupdf pypandoc
  ```
- Optional: `pip install beautifulsoup4` (a better table of contents)

**Fonts matter more than they look like they should.** The Korean output is
tuned against a specific pair, and a missing font is not cosmetic, the
fallback face has different letter spacing, so lines break in different
places and the page count of the finished book changes, even though nothing
errors:

| For | Install |
|---|---|
| Korean body text and headings | [Noto Serif KR and Noto Sans KR](https://fonts.google.com/noto) |
| Formulas | any font with an OpenType MATH table: Cambria Math ships with Microsoft Office; [STIX Two Math](https://www.stixfonts.org/) is the free alternative |

Translating into a different language calls for that language's own fonts;
the two above are what the Korean pipeline was tuned and measured against.

## 4. Check the install

From inside the skill folder, run:

```bash
python scripts/doctor.py --strict
```

This uses the exact same lookup logic the pipeline itself uses to find
pandoc, Chromium, and Calibre (not a generic `which` check) so it won't
tell you something is missing when the pipeline would have found it fine.
It reports every required and recommended piece, explains what each one is
for, and exits with an error only if something REQUIRED is missing. A
missing font is flagged as "recommended", because the pipeline still runs
without it; it just won't produce the same pages.

If it reports everything present, don't stop there, a report of what's
*installed* is not proof of what *comes out*. Prove the output itself:

```bash
python -m unittest discover -s tests -p "test_*.py"
python tests/layout_probe.py --strict
```

The second command builds an actual PDF from a test document and measures
it (page size, margins, type size, line count, and the exact fonts that got
embedded) against the profile this skill was designed to. `PASS` there
means your machine will produce the same book someone else's machine did,
which `doctor.py` alone cannot promise.

## 5. Use it

Open Claude Code in any project and either mention translating a book, or
invoke the skill by name. See `SKILL.md` in this folder for what it does and
`README.md` for the full option list.

## If something doesn't match

- `doctor.py` says something required is missing → install it, from the
  table in step 3, and run `doctor.py` again.
- `doctor.py` passes but `layout_probe.py --strict` fails → almost always a
  font problem. Re-check step 3's font table; `layout_probe.py`'s output
  names the font it expected and the one it actually got embedded.
- Both pass, but a specific translated book still doesn't look right → that
  book's problem, not the install. `AGENTS.md` in this folder has a "How this
  pipeline breaks" section written for exactly that.
