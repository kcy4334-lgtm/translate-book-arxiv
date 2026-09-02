# CLAUDE.md

## Project

translate-book is a Claude Code Skill that translates books (PDF/DOCX/EPUB) into any language using parallel subagents. Published on GitHub as `kcy4334-lgtm/translate-book-arxiv`.
A fork of [deusyu/translate-book](https://github.com/deusyu/translate-book); upstream also publishes on ClawHub, this fork does not.

## Structure

- `SKILL.md` — Skill definition, the orchestration logic that Claude Code / OpenClaw follows
- `KNOWLEDGE.md` — findings log: tool behaviour that surprised us, with the
  measurement that proved it. Read on unexpected output; append per SKILL.md
  Step 9. Anything a test now enforces is one line here pointing at the test
- `scripts/convert.py` — PDF/DOCX/EPUB → Markdown chunks (via Calibre HTMLZ)
- `scripts/arxiv_backend.py` — the arXiv LaTeX-source path: fetch, flatten, sanitize, pandoc
- `scripts/paper_macros.py` — resolves the paper's own `\newcommand`s from the `.sty` files it ships, before pandoc reads the source. A `.sty` is never `\input`, so pandoc never sees the definition and the name prints at the reader. Refuses rather than guesses, and reports what it refused
- `scripts/manifest.py` — SHA-256 chunk tracking and merge validation
- `scripts/glossary.py` — Term-consistency glossary; per-chunk term tables injected into sub-agent prompts
- `scripts/chunk_context.py` — Read-only previous/next chunk excerpts injected into sub-agent prompts
- `scripts/meta.py` — Per-chunk sub-agent observation file schema
- `scripts/merge_meta.py` — Merges sub-agent observations into the canonical glossary as each chunk lands
- `scripts/run_state.py` — Selective re-translation planner and run_state.json recorder
- `scripts/merge_and_build.py` — Merge translated chunks → HTML/DOCX/EPUB/PDF
- `scripts/layout.py` — Language font tables and print profiles (page size, margins, body size); the single source of truth both merge_and_build.py and calibre_html_publish.py read
- `scripts/chromium_pdf.py` — Headless-Chromium PDF renderer and PyMuPDF page-number stamping
- `scripts/calibre_html_publish.py` — Calibre format conversion wrapper (EPUB, and DOCX fallback)
- `scripts/template.html`, `scripts/template_ebook.html` — HTML templates

## Testing changes

Test with a small PDF to verify the full pipeline:

```bash
python3 scripts/convert.py /path/to/small.pdf --olang zh
# then run translation via the skill
python3 scripts/merge_and_build.py --temp-dir <name>_temp --title "test"
```

Verify: all output_chunk*.md files exist, manifest validation passes, output formats generate.

## Conventions

- Only `chunk*.md` naming — no `page*` legacy support
- Pipeline output artifacts use the canonical names `book.html`, `book_doc.html`, `book.docx`, `book.epub`, `book.pdf`. Internal scripts and skip/cache logic depend on these names; if title-based filenames are added later they must be optional aliases/copies, not silent replacements
- SKILL.md frontmatter must stay single-line per field (OpenClaw parser requirement)
- Script paths in SKILL.md use `{baseDir}` not hardcoded paths
- Subagent instructions in SKILL.md must be platform-neutral (work on Claude Code, OpenClaw, Codex)
- There is ONE README. Upstream keeps a Chinese one; this fork dropped it rather than carry a translation nobody here can review — it would go stale on the first edit, and a stale translation is worse than none
- Releases follow `.claude/commands/release.md` — `git push origin main`, then `git tag vX.Y.Z && git push --tags`. Do not skip the git tag; it's the only version anchor in the repo. ClawHub publishing is upstream's, not this fork's

## Do not

- Do not put language font data or page geometry anywhere but `scripts/layout.py`. It used to be duplicated in `merge_and_build.py` and `calibre_html_publish.py` and the two copies had already drifted
- Do not list a variable font (`Noto Serif KR`, `Noto Sans KR`) in a CJK stack. Chromium cannot subset-embed one and falls back to a Type3 object per glyph, which bloats the PDF ~8x and stops it being real text. Use a static face
- Do not reintroduce `page*` file support — it was intentionally removed
- Do not hardcode `~/.claude/skills/` paths in SKILL.md — use `{baseDir}`
- Do not put platform-specific tool names (Agent, sessions_spawn) in `allowed-tools` as the only option — keep the whitelist cross-platform
- Do not add mtime-based incremental rebuild for HTML/format generation — the current skip logic is intentionally simple (existence check). Metadata/template changes require manual cleanup. This is documented in the README.
