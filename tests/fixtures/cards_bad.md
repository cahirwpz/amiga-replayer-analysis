---
player: MugicianII
base: Nowhere
source: wanted_team/MugicianII
code: uade
control: bytecode
themes: [synthesis, dance]
ideas: []
related: []
streams: { song: 1, track: 0, voice: 2 }
evidence: code
---

# Cards fixture

## Streams

| Stream | Scope | Role | Carries | Control | Rate |
| --- | --- | --- | --- | --- | --- |
| Track | voice | conductor | notes | teleport | sometimes |
| Sequence | song | sequencer | patterns | loop | row |

## Sequencer

| Aspect | Value | Label |
| --- | --- | --- |
| Time | grid | x |
| Routing | magic | x |

## Generators

| Generator | Scope | States | Writes | Rate | Set by | Note-on |
| --- | --- | --- | --- | --- | --- | --- |
| Wobble | galaxy | a, b | period | often | Track, Ghost | maybe |

## Channel outputs

| Output | Writers, in tick order |
| --- | --- |
| Colour | Wobble (set), Track, Nobody (add), Track (twist) |

## Interactions

| From | To | Event |
| --- | --- | --- |
| Track | nowhere | note-on |

## Key ideas

- Sections are out of order.
