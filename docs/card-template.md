# Player card template

Copy into `players/<name>.md`. Angle brackets mark placeholders.

```markdown
---
player: <binary name in ext/uade/players>
control: { sequencer: <level>, instrument: <level> }
themes: [synthesis, mixing, tricks, emulation]
ideas: [<idea slug>]
streams: { song: <n>, voice: <n>, instrument: <n> }
---

# <Player name>

<One sentence: what makes it different.>

## Key ideas

- <Idea, and what it costs.> `<file>:<Label>`

## Streams

| Stream | Scope   | Role   | Carries                    | Control      | Rate   |
| ------ | ------- | ------ | -------------------------- | ------------ | ------ |
| <name> | <scope> | <role> | <what it sets; data owner> | <vocabulary> | <rate> |

## Sequencer

| Aspect   | Value   | Label      |
| -------- | ------- | ---------- |
| Time     | <words> | `:<Label>` |
| Unit     | <words> | `:<Label>` |
| Note end | <words> | `:<Label>` |
| Routing  | <words> | `:<Label>` |
| Reuse    | <words> | `:<Label>` |
| Tempo    | <words> | `:<Label>` |

## Generators

| Generator | Scope   | States   | Writes   | Rate   | Set by    | Note-on  |
| --------- | ------- | -------- | -------- | ------ | --------- | -------- |
| <name>    | <scope> | <states> | <output> | <rate> | <streams> | <effect> |

## Channel outputs

| Output   | Writers, in tick order |
| -------- | ---------------------- |
| <output> | <Name (mode)>, …       |

## Interactions

| From   | To     | Event                     |
| ------ | ------ | ------------------------- |
| <name> | <name> | <what crosses> `:<Label>` |

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

## Roles

- A **sequencer** stream decides which note plays and when.
- An **instrument program** shapes one note. Test: a note-on starts or restarts
  it. A stream that an instrument program starts is `instrument` too.
- `control` gives one level per role: `tables`, `commands`, `program` or `none`.

## Tables

- Sequencer: how the score places notes in time, ends them and routes them to
  voices. Each value is one or more words from the aspect's glossary section.
- With `allocated` routing, add bullets below the Sequencer table. They give the
  voice allocation rules: free voice first, which voice gets stolen, priorities.
- Generators: a stateful process that is not a stream, e.g. an envelope.
  - Rate: how often its state changes.
  - Set by: the streams that set its parameters, or `instrument` for fixed
    instrument data. The parameters change at each setter's rate.
  - Note-on: what a note-on does to its state.
- Channel outputs: one row per output that applies. List the writers in the
  order one tick runs them. The mode says how each one writes.
- Interactions: events that cross between streams, generators, voices or the
  game. Quirks that are not events go in bullets below the table.

## Delta cards

A version with a distinct idea may share most of its model with the family's
card. Its delta card has `base: <player>`, naming that card.

- It may skip Streams, Sequencer and State.
- Its tables may name the base card's streams and generators.
- Channel outputs lists only the rows that change.
- `streams` counts only its own Streams table; `{}` if it has none.

## Rules

- Use plain English for terms not in [the glossary](glossary.md). Name
  operations plainly, e.g. "shift the wave by one sample".
- Add `track: <n>` to `streams` only when tracks are not bound to voices.
- Facts about the player go in `data/players.yaml`: provenance, lineage, author,
  links. A card needs a provenance there.
- Mark what you hear, if stated, as "(inference)".
- Anything that needs more than about 10 words goes to `details/`, linked.
- Skip Generators and Interactions when there is nothing to say.
- Cite by label, as [`AGENTS.md`](../AGENTS.md#evidence) says.
