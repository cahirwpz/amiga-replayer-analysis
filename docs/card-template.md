# Player card template

Copy into `players/<name>.md`. Angle brackets mark placeholders.

```markdown
---
player: <binary name in uade/players>
source: <path under uade/amigasrc/players, or ext/...>
code: uade | module
control: tables | commands | program
themes: [synthesis, mixing, tricks]
ideas: [<idea slug>]
related: [<player>]
streams: { song: <n>, track: <n>, voice: <n>, instrument: <n> }
evidence: code | port | docs
---

# <Player name>

<One sentence: what makes it different.>

## Key ideas

- <Idea, and what it costs.> `<file>:<line>`

## Streams

| Stream | Scope   | Carries                    | Control      | Rate          |
| ------ | ------- | -------------------------- | ------------ | ------------- |
| <name> | <scope> | <what it sets; data owner> | <vocabulary> | <tick, speed> |

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

## Fields

- **code**: where the replay logic lives. `module` means it ships inside the
  music file.
- **control**: `tables` are walked in order. `commands` add opcodes. `program`
  adds conditions or calls.
- **evidence**: `code` is original or disassembled source. `port` is a port of
  the original.

## Streams

- A **stream** is an independent position in some data, stepped by the player.
- **Scope** is where the position lives: song, track, voice or instrument.
- **Control** uses a fixed vocabulary: `loop`, `jump`, `call`, `wait`, `cond`,
  `end`, `mode`.
- **Rate** is how often the stream steps.

## Rules

- Skip "Generators and interactions" when there is nothing to say.
- Cite as `file:line`, relative to the card's `source`.
