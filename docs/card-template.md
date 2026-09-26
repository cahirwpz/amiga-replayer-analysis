# Player card template

Copy into `players/<name>.md`. Angle brackets mark placeholders.

```markdown
---
player: <binary name in ext/uade/players>
source: <path under ext/uade/amigasrc/players, or ext/...>
code: uade | module
control: tables | commands | program
themes: [synthesis, mixing, tricks]
ideas: [<idea slug>]
related: [<player>]
streams: { song: <n>, voice: <n>, instrument: <n> }
evidence: code | port | docs
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

- Terms not defined in `docs/glossary.md` must be plain English.
- Add `track: <n>` to `streams` only when tracks are not bound to voices.
- Name each operation in plain words, e.g. "shift the wave by one sample".
- Mark what you hear, if stated, as "(inference)".
- Anything that needs more than about 10 words goes to `details/`, linked.
- Skip "Generators and interactions" when there is nothing to say.
- Cite as `file:line`, relative to the card's `source`.
