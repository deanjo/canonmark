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

Just as important: agents **read the label before the body**. The five-step protocol
parses frontmatter first, and `canon_read` turns that habit into a mechanism — a
superseded doc returns its replacement pointer, never its text.

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

> **Early development.** The CLI works and is fully tested, but is not published
> to PyPI yet — install from source until then.

```bash
pip install canonmark          # not published yet; use `pip install -e .` from a clone
canon init                     # scaffold canonmark.toml + print the MCP wiring
canon audit docs/              # audit authority metadata; non-zero exit on conflicts
canon read docs/design/x.md    # read a doc through the contract (see below)
canon index --current-only     # compact label listing; on demand, never a prerequisite
canon mcp                      # run as an MCP server so agents get canon_read as a tool
```

`canon audit` parses only the frontmatter of each key doc, checks it against the
authority contract, and reports every `INSUFFICIENT_METADATA` / `METADATA_CONFLICT`
with a file path — ready to wire into pre-commit and CI.

### It won't turn your existing repo red on day one

Point canonmark at a years-old `docs/` where nothing has frontmatter yet and it
exits **0**. The rule is: **what you haven't done isn't a failure; what you did
wrong is.** Untagged docs and missing navigation are reported as notices that
point the way; only documents that *do* carry a label and get it wrong fail the
gate. So you can adopt one document at a time — tagging a stale design doc with
"superseded by v2" is a complete, useful step by itself, and it will not force
you to go tag v2 and everything v2 points at.

One nuance, so the promise above stays honest: a document whose very first line
is a `---` **horizontal rule** used to be misread as unterminated frontmatter and
failed the gate even in gradual mode. Fixed on 2026-07-29: gradual mode now looks
at what follows the `---` — if it doesn't look like a YAML key, the doc counts as
simply untagged (a notice, exit 0). A `---` followed by something that *does*
look like a YAML key still fails in every mode: a real label with a missing
terminator is an error worth catching. The honest cost of the leniency, recorded
in [docs/acceptance.md](docs/acceptance.md): a label starting with a YAML comment
line, or a typo like `status:current` with no space, now reads as "untagged" in
gradual rather than erroring.

Once a doc library is fully governed, switch it on properly with
`adoption_mode = "strict"` in `canonmark.toml`, and structural gaps fail again
(that is how canonmark audits itself).

### Going further: `canon_read`, the enforcement layer

The core of canonmark is the part above: **labels plus the audit gate.** In our
controlled experiment (see Status), labels alone did most of the work — agents
went from "plausible guess, please confirm" to a confident, correct call without
any tooling. `canon_read` builds on that for the cases navigation can't cover: a
README nobody updated, or an agent landing on a doc directly via search. A label
only helps if something acts on it. `canon_read` is the thing that acts:
point it at a retired doc and **the body is not returned at all** — you get its
status and where to go instead.

```
$ canon read docs/design/rate-limit.md
docs/design/rate-limit.md — 已作废（status: superseded）
本文档不再有效，正文按权威契约不予返回。
请改读以下现行文档：
  - docs/design/rate-limit-v2.md
```

Run `canon init` and it prints an `.mcp.json` snippet plus one line for your
`CLAUDE.md`/`AGENTS.md`. After that `canon_read` shows up in the agent's tool list
on every start — the capability lives in the tool surface, not in a convention the
agent has to read a document to discover.

The honest limit: this is filtering, not enforcement. The tool is in the list and
its description says "use this instead of reading files directly," but an agent can
still reach for its built-in file reader. Hard enforcement would need a host-side
hook that intercepts reads under `docs/`, which is outside this tool's scope.

What it does buy you, mechanically: a retired doc's body never enters the context
window, so it cannot be the thing the agent pattern-matches against later.

## Works with CJK docs

CJK documentation is a first-class citizen, not an afterthought. Field values,
`applies_when` / `not_for` scenarios, and audit output all support Chinese (and
other non-ASCII) content natively — so a Chinese-language `docs/` gets the same
authority guarantees as an English one. This is a deliberate differentiator: the
reference project canonmark was extracted from runs a large Chinese doc library.

## Docs

- [Roadmap](docs/roadmap.md) — the eight phases (P0–P7) and what's built when.
- [Vision](docs/design/vision.md) — the problem, the value, and where canonmark
  differs from adjacent projects.
- [Protocol](docs/design/protocol.md) — the 8-field contract and the five-step
  decision protocol, specified in full.

## Status

**Early development — P0–P6 complete; P0–P5 independently verified, and P6
accepted on re-review after an initial REJECT (see below).** The auditor has been
extracted from its origin project and fully parameterized. At extraction time (P1)
its default output was verified byte-identical to the original's — a dated fact,
not a standing promise: since P5 the default output intentionally diverges from
the original, because the origin project's leftover default values were cleared
and the new supersession-symmetry check reports issues the original never did
(see the A1/A2 notes in [docs/acceptance.md](docs/acceptance.md)). Invalid/valid
fixtures form a two-way oracle, and canonmark audits its own docs via
pre-commit and CI. P5 added the anti-rot checks — supersession pointers must be
symmetric, navigation must not list retired documents — plus the gradual adoption
mode described above. The suite passes green, including a two-way fixture oracle
wired into it, and the migrated tests keep their assertions unchanged — though the
supersession symmetry check is a breaking change: one fixture had to be corrected
because it contained a genuine one-sided declaration the new check now catches.

P6 added the reading path: `canon read` (contract-filtered delivery), `canon index`
(compact listing), and `canon mcp` (an MCP server, hand-written over stdio JSON-RPC
so the zero-dependency promise holds). P6 went through independent review twice:
the first round returned REJECT (nine findings); after fixes, the re-review
returned ACCEPT, with its mandatory follow-ups folded into commit `6e21f78`. The
matching acceptance rows (A17/A18) stayed `INSUFFICIENT_EVIDENCE` until a human
decided; on 2026-07-29 the user flipped both to PASS on the strength of that
re-review. A controlled experiment on the labelling
question is written up in [docs/acceptance.md](docs/acceptance.md) — including the
part it failed to show, which is that `canon_read`'s benefit *over labels alone*
remains unproven at the scale tested.

Not yet published to PyPI or GitHub. Public release is deliberately the last step
and is left to a human decision — this repo will not publish itself. See
[docs/acceptance.md](docs/acceptance.md) for the verification matrix and
[docs/progress.md](docs/progress.md) for the current state.

## License

MIT — see [LICENSE](LICENSE).
