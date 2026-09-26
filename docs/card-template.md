# Player card template

Copy into `players/<name>.md`. Angle brackets mark placeholders.

```markdown
---
player: <binary name in ext/uade/players>
source:
  <path under ext/uade/amigasrc/players, ext/..., or data/disasm/<player>.cnf>
code: uade | module | disasm
control: tables | commands | program
themes: [synthesis, mixing, tricks]
ideas: [<idea slug>]
related: [<player>]
streams: { song: <n>, voice: <n>, instrument: <n> }
evidence: code | port | docs | disasm
links: [<url>]
---

# <Player name>

<One sentence: what makes it different.>

## Key ideas

- <Idea, and what it costs.> `<file>:<line>`

## Streams

| Stream | Scope   | Carries                    | Control      | Rate   |
| ------ | ------- | -------------------------- | ------------ | ------ |
| <name> | <scope> | <what it sets; data owner> | <vocabulary> | <rate> |

## Generators and interactions

- <Generator: stateful process that is not a stream.>
- <Interaction: one stream acting on another.>

## State

| Scope      | Fields                          |
| ---------- | ------------------------------- |
| Voice      | <runtime fields>                |
| Instrument | <properties; mark runtime ones> |
| Global     | <fields>                        |

## Open questions

- <What reading did not settle.>
```

## Terms

[The glossary](glossary.md) defines all field values and table words.

## Rules

- Use plain English for terms not in `docs/glossary.md`. Name operations
  plainly, e.g. "shift the wave by one sample".
- Add `track: <n>` to `streams` only when tracks are not bound to voices.
- `links` is optional: first-hand pages, e.g. by the author. Omit if none.
- Mark what you hear, if stated, as "(inference)".
- Anything that needs more than about 10 words goes to `details/`, linked.
- Skip "Generators and interactions" when there is nothing to say.
- Cite as `file:line`, relative to the card's `source`.
