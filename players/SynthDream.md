---
player: SynthDream
template: 2
ideas: [pulse-width-table, soft-edge-pulse, run-length-tables, glide-to-fit]
---

# Synth Dream

A 16-byte pulse wave gets finer width steps from a soft edge byte.

## Context

| Fact      | Value                                                           |
| --------- | --------------------------------------------------------------- |
| Player    | `SynthDream`                                                    |
| Author    | Laurens Tummers and John Tonnard                                |
| Year      | 1991                                                            |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/SynthDream` |
| Spec      | [specs/synth_dream.py](../specs/synth_dream.py)                 |

## Key ideas

- The pulse table picks the width in sixteenths. It also lowers the first high
  byte by an amount, for widths in between. `:PulseWalker`
  - Enables: smooth pulse-width sweeps from one 16-byte wave.
  - Costs: the wave is rebuilt every tick.
- Each table is runs: a count, a repeat number, then the values. `:Runs`
  - Enables: long envelopes from a few bytes.
  - Costs: every note restarts all four tables.
- Events carry their own length in ticks. Each voice reads its own positions.
  `:ReadEvent` `:NoteEvent`
  - Enables: voices that loop at their own lengths, with no rows and no speed.
- A glide can fit its rate to the note. The rate is the interval divided by the
  ticks after its delay. `:GlideToFit`
  - Enables: a glide that ends as the note ends.
- The fine table, the glide and the instrument's shift scale the period. Each
  steps by about 1/4 cent. `:FineWalker` `:Glide` `:ShiftPitch`
  - Enables: detune and slides that sound the same in every octave.
- A position can swap one instrument for another. `:LoadInstrument`
  - Enables: one pattern with other sounds.

## Composer's view

The composer writes, for each voice, positions and patterns of events. An
instrument names four tables, or a sample.

| Aspect   | Answer                                                                   | Source          |
| -------- | ------------------------------------------------------------------------ | --------------- |
| Notation | An event: a word opcode, then length, note, volume, instrument or glide. | `:NoteEvent`    |
| Notation | A position: pattern, transpose, repeats, instrument swap, volume offset. | `:ReadPosition` |
| Notation | An instrument: fixed note, pitch shift, four tables, or a sample.        | `:Instrument`   |
| Cost     | An event without a length repeats the last length.                       | `:NoteEvent`    |
| Cost     | Volume offsets are subtracted from the volume table's value.             | `:VolumeWalker` |
| Cost     | A note is silent on its last tick, unless legato is on.                  | `:WriteChannel` |
| Cost     | A rest stops all four tables.                                            | `:VoiceTick`    |

## What is unique

- A switched table plays, then returns to the instrument's own table at its end.
  `:SwitchTables`
- A glide has no target. It multiplies the pitch ratio every tick until the
  event ends. `:Glide`
- A note's first tick writes the sample, the second its loop. There is no
  busy-wait. `:WriteChannel`
- Each voice ends on its own. `LOOP_POSITIONS` loops its positions and
  `STOP_VOICE` stops it. `:NextPosition`

## Open questions

- Did any composers besides the authors use this format?
