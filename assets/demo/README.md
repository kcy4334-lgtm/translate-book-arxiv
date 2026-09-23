# Demo comparison strips

Each image puts one page of the source paper next to the page of the Korean
book built from it, at the same scale. They are rendered, not composed by
hand: `01-title.png` is page 1 against page 1, `02-math.png` is the Background
section, `03-table.png` is Table 1.

| File | Source page | Book page | What it shows |
|---|---|---|---|
| `01-title.png` | 1 | 1 | Title, authors and abstract |
| `02-math.png` | 3 | 5 | Equations stay equations, and keep the paper's numbers |
| `03-table.png` | 7 | 12 | Table 1, every number and every `±` unchanged |

## Source and licence

The paper is **arXiv:2609.11801v1, "Thinking with Looped Flows"** by Ayhan
Suleymanzade, Chanhyuk Lee, Floor Eijkelboom, Nicholas M. Boffi, Ismail Ilkan
Ceylan and Jinwoo Kim, published under **CC BY 4.0**
(<https://creativecommons.org/licenses/by/4.0/>). The left half of each strip
is that paper, reproduced under that licence; the right half is the Korean
translation this skill produced from its LaTeX source. The translation is a
derivative work and is offered under the same licence.

arXiv records a paper's licence in its OAI-PMH metadata, not in the Atom API:

```
https://export.arxiv.org/oai2?verb=GetRecord&metadataPrefix=arXiv
    &identifier=oai:arXiv.org:2609.11801
```

The Atom API returns no licence field at all, so a survey built on it reports
every paper as unlicensed. Check OAI-PMH before assuming a paper cannot be
redistributed.
