# Referee ledger

What the sub-agents actually did, across chunks, across roles, across books,
and what was decided about it.

`verify_chunk` judges one chunk and rejects it. That is the right unit for
rejecting work and the wrong unit for noticing anything: a defect that fires
once is an accident, the same defect on a third of a run is a briefing fault,
and the same defect in three books is something nobody has fixed. This file
holds the second kind of finding. `scripts/referee.py` supplies the counts;
the `referee` agent supplies the judgement and writes here.

**Identity in this pipeline is the ROLE, not the instance.** Every chunk gets
a fresh sub-agent with its own context, so "the same agent again" can only
mean "the same role again", the eighteen chunk translators of one book are
eighteen instances of one role reading one prompt. Cards are raised against
roles. They are also keyed by DEFECT CLASS, so a card raised on the
table-caption role is found when the chunk role does the same thing: that is
how one role learns from another's history without anyone remembering it.

**A card is not a punishment and an unused card is not a saving.** The point
is that a role stops repeating itself, not that the ledger looks thorough. The
restraint rules are in `.claude/agents/referee.md` and they are as binding as
the rest: no card on a first occurrence, no card for a tool disagreement, no
card that says "be more careful", and cards clear when the role runs clean.

| situation | entry |
|---|---|
| a check fires and it is not clear whose fault it is | [R1](#r1) |
| evidence quotes that are not in the chunk | [R2](#r2) |
| most of a run gets the same schema wrong | [R3](#r3) |
| a chunk is rejected and the agent looks at fault | [R4](#r4) |
| an evidence quote fails on a character nobody can see | [R5](#r5) |
| a check name is chronic but the causes are not the same | [R6](#r6) |

---

### R1
**Establish whose fault it is before the card, not after.**
`meta_evidence` fired on 3 of 9 TinyVLA chunks, over the briefing-fault
threshold. Reading the six quotes: two matched the source once whitespace was
normalised and four did not match at all. So I went to fix the check for
comparing byte-exactly against a hard-wrapped source, and the check already
normalises (`' '.join(source.split())`). There was no tool defect; the four
were reconstructions, and the two never failed anything. Had the card gone
out first it would have named the wrong culprit twice over. In this pipeline
most surprises are the tools disagreeing rather than anyone erring (K57), so
the check comes before the card, always.
*Decided: no card. Confirm the mechanism in the code before attributing it.*
---

### R2
**~~The role reconstructs evidence quotes instead of copying them.~~**
Four quotes across three of TinyVLA's nine chunks were offered as evidence
and are not in the chunk, not paraphrase-close either: the longest matching
prefixes were 52 of 127 characters, 23 of 111, and 12 of 47. At three of nine
this is the BRIEF: the prompt asks for "a ≤200-char quote" without saying that
it is checked against the source.
*Decided: fix the brief, not the agents. No card, the agents did what they
were asked.*
**The decision was right and the diagnosis was wrong.** Reopened at [R5](#r5):
none of the four is a remembered sentence. Two dropped an injected token that
was part of the chunk text, and two are the same quote broken by an unescaped
backslash in JSON. The guidance this entry produced, "whitespace is the only
thing forgiven", addresses none of the three causes, and has been replaced.
---

### R5
**An evidence quote failed on a character nobody can see.**
Maynard's chunk0002 offered 166 characters of which 165 matched; the one that
did not was `Zhang’s` against the author's `Zhang's`. pandoc's reader smartens
the apostrophe and `_WRITER` ends in `-smart`, so the chunk carries a character
the paper does not and the agent had reproduced the paper. That is the TOOL,
and the fold in `verify_chunk._fold_typography` is the fix.
Two things about how it was evidenced are worth keeping. The corpus sweep
offered as proof globbed `output/batch*/`: 131 of 246 metas, and it had
excluded TinyVLA, which is 2409.12514v5, the very paper the chronic tally
named. Re-run whole, the count is 1694 exact and 4 absent, all TinyVLA, and
re-reading those four is what corrected [R2](#r2). And "all 11 chunks now pass"
proved nothing: the re-translation had left chunk0002's meta with no evidence
quote in it at all, so it passes with the fix reverted. The load-bearing
evidence is `tests/test_meta_evidence_typography.py` and the measurement that
the fold moves none of the four failing prefixes: 52, 23, 12, 12, folded or
not.
*Decided: no card, on this run or retroactively on TinyVLA. Four of the last
four `meta_evidence` fires belong to the pipeline or to JSON, not to a role
([K57](KNOWLEDGE.md#k57)). Note also that re-recording a paper clean deletes
its failing row from `referee/runs.json` by design, so an incident worth
keeping has to be written here.*
---

### R4
**Three rejections in two books; the agent was at fault in none of them.**
U-Net's first chunk failed `untranslated_block` on a wrapped code span it had
been told to leave alone. GAN's last failed `target_language` at 23% on a
chunk of author-affiliation footnotes where every translatable word had been
translated. The malformed metas of [R3](#r3) were the briefing's doing. So on
the running count the check or the brief was the culprit three times out of
three, which is what [K57](KNOWLEDGE.md#k57) says to expect: in this pipeline
nothing fails, it disagrees. A referee who had opened with cards would have
been wrong every time and would have taught three roles to hesitate.
*Decided: no cards. Read the check's code first; it is not a formality, it
is where the answer has been every time so far.*
---

### R3
**A schema shown only as empty arrays is not a schema.**
Four of five U-Net metas were quarantined: three for `new_entities` entries
with no `source`, one for `used_term_sources` holding dicts where the schema
wants strings. Four of five is far past the briefing threshold, and the cause
was in the dispatch prompt; it printed the meta as `{"new_entities": [], ...}`
and never once showed a POPULATED entry. Every agent then invented a
plausible shape, and they invented different ones. An empty container teaches
nothing about what goes in it; if a field has required keys, the brief has to
show one filled in.
*Decided: fix the brief, not the agents. No card. The translations themselves
passed the gate, only the metas were malformed, and quarantine held.*
---

### R6
**A chronic check name is not a chronic cause.**
ResNet: nine of ten metas quarantined on invented field names (`entity` for
`entity_source`, `name`/`type`/`translation` for the new-entity fields,
`confidence` absent) and `meta_evidence` on chunk0006. Reported as two
faults, the brief for one and the agent for the other. They are one.
`meta.py prompt-block` emits the field names and the verbatim-quote rule in a
SINGLE block; `brief_chunk0006.md` contains neither word in its 1,924
characters, because the orchestrator retyped the schema by hand as empty
arrays. The agent broke a rule it was never shown, and its ellipsis splice is
downstream of that same omission. This is [R3](#r3) a second time in a second
book, except R3's remedy has since SHIPPED: `SKILL.md:516` mandates the
command and `tests/test_meta_prompt_block.py` pins it. Attribution 1 is out,
the tool works; 2 is out, the brief is explicit. The card is the
orchestrator's: assemble the block, never retype it.
The tally read `meta_evidence`: 2 runs, 4 chunks, 2 papers. It is three
mechanisms: TinyVLA's two dropped markup tokens and its unescaped backslash
([K129](KNOWLEDGE.md#k129)), and here an ellipsis splice. A shared check name
is not a shared cause; read the recorded cause before joining two rows.
One more, no card. The repair agent reported 7 of 62 quotes failing on
U+00A0. `_SMART_FOLD` folds U+00A0 and `str.split()` eats it before the fold
is reached; the repaired store holds 81 checkable quotes, 8 of them carrying
U+00A0, and the check passes all 81. Wrong comparator, wrong denominator,
[R5](#r5)'s class again, within days. R5 carded nobody, so this does not
either; the next one does.
*Decided: one card, orchestrator. None to the chunk role, which was never
shown the rule it broke, and none to the repair role.*
---
