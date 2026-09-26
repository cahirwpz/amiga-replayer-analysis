---
player: Jochen_Hippel_ST
base: MugicianII
control: { sequencer: commands, instrument: tables }
themes: [mixing]
ideas: []
streams: {}
---

# Delta card fixture

It names streams and generators of its base card, `MugicianII.md`.

## Key ideas

- A delta card may skip Streams, Sequencer and State.

## Generators

| Generator | Scope | States | Writes    | Rate | Set by | Note-on |
| --------- | ----- | ------ | --------- | ---- | ------ | ------- |
| Echo      | song  | on     | wave data | tick | Track  | keep    |

## Channel outputs

| Output    | Writers, in tick order     |
| --------- | -------------------------- |
| Wave data | Mixer (edit), Echo (edit)  |

## Interactions

| From | To          | Event          |
| ---- | ----------- | -------------- |
| Echo | Portamento  | none, a test   |

## Open questions

- None.
