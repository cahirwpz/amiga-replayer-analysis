---
player: AbyssHighestExperience
control: commands
themes: [synthesis]
ideas:
  [
    generated-waves,
    filter-bank,
    sweep-between-limits,
    performance-list,
    hard-cut,
  ]
streams: { song: 1, voice: 2 }
---

# AHX

No samples: every sound comes from built-in waves and their filtered copies.

## Key ideas

- The player generates triangle, saw, 32 pulse and noise waves.
  `loader.c:ahxInitWaves`
- It adds 31 low-pass and 31 high-pass copies of each wave.
  `:setUpFilterWaveForms`
- Filter and pulse width sweep back and forth between two limits.
  `replayer.c:ProcessFrame`
- Each instrument runs a performance list: wave, note, two commands per step.
  `:pListCommandParse`
- Wave length picks the octave. Copies of the wave fill a fixed buffer.
  `:CopyWaveformToPaulaBuffer`
- Hard cut: the player reads the next row and ends the note early.
  `:ProcessFrame`

## Streams

| Stream      | Scope | Carries                       | Control | Rate          |
| ----------- | ----- | ----------------------------- | ------- | ------------- |
| Positions   | song  | track and transpose per voice | jump    | pattern end   |
| Track       | voice | note, instrument, command     | none    | row           |
| Performance | voice | wave, note, two commands      | jump    | every N ticks |

## Generators and interactions

- ADSR: linear, counted in ticks. `:ProcessStep`
- Noise reads a long noise table at a new random offset each tick.
  `:ProcessFrame`

## State

| Scope      | Fields                                                          |
| ---------- | --------------------------------------------------------------- |
| Voice      | track, list step and wait, ADSR, filter and pulse positions     |
| Instrument | ADSR, wave length, filter and pulse limits and speeds, the list |
| Global     | position, row, tempo                                            |

## Open questions

- Does the small external replayer differ in sound from the tracker's code?
