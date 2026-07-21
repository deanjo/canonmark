# canonmark

> **Tell your AI agents which doc to trust.**

Your `docs/` folder is context now. AI coding agents (Claude Code, Cursor, Copilot)
read it as authoritative — including the doc you superseded three months ago, the
spec describing an endpoint you already deleted, and the two guidelines that flatly
contradict each other. Linters check formatting, prose, and links. **Nothing checks
whether a doc still counts.** canonmark does.

canonmark makes document authority a machine-checkable contract in the header of
each key doc: which doc is current, which is superseded, who wins a conflict, and
what a doc is allowed to decide. Then it breaks the build when your docs lie about it.

## Before / after

**Before** — nothing marks the old doc as dead, so the agent trusts it:

```
docs/
  api-design.md          # (no metadata) — describes deleted endpoint POST /v1/sync
  api-design-v2.md       # (no metadata) — the real, current design

Agent reads api-design.md → confidently writes a call to POST /v1/sync → build breaks.
```

**After** — one `superseded_by` pointer redirects the agent to the doc that counts:

```
docs/
  api-design.md          # status: superseded   superseded_by: [api-design-v2.md]
  api-design-v2.md       # status: current      current_authority: contract-current

Agent parses frontmatter first → follows superseded_by → reads api-design-v2.md.
The old body is never loaded as current fact.
```

## What it does

- Defines an **8-field authority contract** in each key doc's frontmatter
  (`status`, `applies_when`, `not_for`, `current_authority`, `supersedes`,
  `superseded_by`, `owner`, `last_reviewed`).
- Gives agents a **five-step decision protocol** — `superseded_by → status →
  not_for → applies_when → current_authority` — so they parse the header *before*
  the body and never treat a dead doc as live fact.
- **Fails closed.** Missing fields or contradictory metadata are flagged
  (`INSUFFICIENT_METADATA` / `METADATA_CONFLICT`) instead of silently trusting the
  stale body.
- Enforces it as a **gate**: `canon audit docs/` in pre-commit and CI, so the
  labels can't rot unnoticed.

## Why

Two things are true at once: stale and contradictory docs are the strongest
distractor in an LLM's context window, and a large share of docs are never updated
after they're written. Result: a `docs/` folder that passes every existing linter
can still walk an agent straight into wrong code — because no linter ever asks
*"does this doc still count?"* canonmark is that missing check: the **document
lifecycle layer** of the AI-context tooling stack.

## Where it fits (complements, doesn't replace)

| Tool | Governs |
|---|---|
| `llms.txt` | What your public **website** exposes to LLMs |
| `AGENTS.md` | **Instructions** you give the agent (how to work) |
| `Vale` / `markdownlint` / `lychee` | **Prose, formatting, and broken links** |
| **canonmark** | **Document authority & lifecycle** — which doc to trust, and for how long |

One line: **AGENTS.md tells the agent how to work; canonmark tells the agent which
doc to trust.**

## Quick start

> **Early development.** The CLI is not published yet — commands below are the
> intended P1 surface, shown so you can see where this is going.

```bash
pip install canonmark          # not on PyPI yet (P1)
canon init                     # scaffold canonmark.toml + a docs/ convention
canon audit docs/              # audit authority metadata; non-zero exit on conflicts
```

`canon audit` parses only the frontmatter of each key doc, checks it against the
authority contract, and reports every `INSUFFICIENT_METADATA` / `METADATA_CONFLICT`
with a file path — ready to wire into pre-commit and CI.

## Works with CJK docs

CJK documentation is a first-class citizen, not an afterthought. Field values,
`applies_when` / `not_for` scenarios, and audit output all support Chinese (and
other non-ASCII) content natively — so a Chinese-language `docs/` gets the same
authority guarantees as an English one. This is a deliberate differentiator: the
reference project canonmark was extracted from runs a large Chinese doc library.

## Docs

- [Roadmap](docs/roadmap.md) — the six phases (P0–P5) and what's built when.
- [Vision](docs/design/vision.md) — the problem, the value, and where canonmark
  differs from adjacent projects.
- [Protocol](docs/design/protocol.md) — the 8-field contract and the five-step
  decision protocol, specified in full.

## Status

**Early development (P0).** Foundations first: extract the auditor from its origin
project, parameterize it, and make canonmark audit its own docs. Public release is
deliberately the last step and is left to a human decision — this repo will not
publish itself.

## License

MIT — see [LICENSE](LICENSE).
