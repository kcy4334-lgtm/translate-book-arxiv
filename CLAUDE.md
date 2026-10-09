# CLAUDE.md

## Project

translate-book is a Claude Code Skill that translates books (PDF/DOCX/EPUB) into any language using parallel subagents. Published on GitHub as `kcy4334-lgtm/translate-book-arxiv`.
A fork of [deusyu/translate-book](https://github.com/deusyu/translate-book); upstream also publishes on ClawHub, this fork does not.

## Structure

- `SKILL.md`: Skill definition, the orchestration logic that Claude Code / OpenClaw follows
- `KNOWLEDGE.md`: findings log: tool behaviour that surprised us, with the
  measurement that proved it. Read on unexpected output; append per SKILL.md
  Step 9. Anything a test now enforces is one line here pointing at the test
- `KNOWHOW.md` and `REFEREE.md`: what a way of working cost, and which
  repeated failures belong to a tool, a brief or a role
- Every script, with what it does, is in the README's
  [Project Structure](README.md#project-structure) table and only there.
  CLAUDE.md and AGENTS.md each kept a copy of that list, and each had lost
  a different dozen scripts
- `merge_and_build.py` was split into `latex_cleanup.py`, `numbering.py`,
  `latex_tables.py` and `build_common.py` to stay under 256 KiB. It imports
  back every name its callers and tests use, so those imports are not dead

## Testing changes

Test with a small PDF to verify the full pipeline:

```bash
python3 scripts/convert.py /path/to/small.pdf --olang zh
# then run translation via the skill
python3 scripts/merge_and_build.py --temp-dir <name>_temp --title "test"
```

Verify: all output_chunk*.md files exist, manifest validation passes, output formats generate.

## Conventions

- Only `chunk*.md` naming, no `page*` legacy support
- Pipeline output artifacts use the canonical names `book.html`, `book_doc.html`, `book.docx`, `book.epub`, `book.pdf`. Internal scripts and skip/cache logic depend on these names; if title-based filenames are added later they must be optional aliases/copies, not silent replacements
- SKILL.md frontmatter must stay single-line per field (OpenClaw parser requirement)
- Script paths in SKILL.md use `{baseDir}` not hardcoded paths
- Subagent instructions in SKILL.md must be platform-neutral (work on Claude Code, OpenClaw, Codex)
- There is ONE README. Upstream keeps a Chinese one; this fork dropped it rather than carry a translation nobody here can review; it would go stale on the first edit, and a stale translation is worse than none
- Releases follow `.claude/commands/release.md`, and only that file spells out the commands. The git tag is the only version anchor in the repo. ClawHub publishing is upstream's, not this fork's

## Do not

- Do not let a shipped text file grow past 256 KiB. Anthropic's plugin directory holds every release that has one for a human reviewer; `tests/test_plugin_skill_rules.py` fails first
- Do not put language font data or page geometry anywhere but `scripts/layout.py`. It used to be duplicated in `merge_and_build.py` and `calibre_html_publish.py` and the two copies had already drifted
- Do not list a variable font (`Noto Serif KR`, `Noto Sans KR`) in a CJK stack. Chromium cannot subset-embed one and falls back to a Type3 object per glyph, which bloats the PDF ~8x and stops it being real text. Use a static face. A CFF face (Noto Serif CJK, STIX Two Math, Latin Modern Math) prints as Type3 the same way, so a TrueType one goes ahead of it in any stack, and `layout.py`'s face lists, which `doctor.py` checks, name only TrueType faces
- Do not reintroduce `page*` file support; it was intentionally removed
- Do not hardcode `~/.claude/skills/` paths in SKILL.md, use `{baseDir}`
- Do not put platform-specific tool names (Agent, sessions_spawn) in `allowed-tools` as the only option, keep the whitelist cross-platform
- The build skips work by file time: `book_doc.html` is remade when `output.md` is newer than it, and each format when `book_doc.html`, an image or the cover is. A new title, template or print profile touches none of those files, so it needs `--force-html`
