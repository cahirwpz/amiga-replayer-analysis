# One driver core, three formats

[Rob Hubbard](../players/RobHubbard.md),
[David Whittaker](../players/DavidWhittaker.md) and [Fred](../players/Fred.md)
share a small core of replay code. Their formats differ, so each keeps its own
card. They are `related` in [`data/players.yaml`](../data/players.yaml), not a
`family`: no player grew from another.

## Shared code

Found with [`tools/codecompare.py`](../tools/codecompare.py), then read in each
listing.

| Routine             | Rob Hubbard   | David Whittaker | Fred |
| ------------------- | ------------- | --------------- | ---- |
| `QueueLoop`         | yes           | yes             | yes  |
| `CountDown`         | yes           | yes             | yes  |
| Period in `NoteOn`  | yes           | yes             | yes  |
| Period table        | one octave up | yes             | yes  |
| `Vibrato`           | no            | yes             | yes  |
| Sample record order | yes           | yes             | yes  |

- `QueueLoop`: a voice flag delays the loop start to the tick after a note.
  `data/disasm/RobHubbard.cnf:QueueLoop`
- `CountDown`: DMA goes off one tick before the next event. Each version adds
  its own exception. `data/disasm/DavidWhittaker.cnf:CountDown`
- The period is the table value × the tune >> 10. Fred's table equals David
  Whittaker's, and Rob Hubbard's starts 12 notes later.
  `data/disasm/Fred.cnf:PeriodTable`
- `Vibrato`: the same triangle, with other offsets and branch sizes.
  `data/disasm/Fred.cnf:Vibrato`
- All three store a sample as start, loop, length and tune, in that order. The
  field widths differ. `data/disasm/DavidWhittaker.cnf:Samples`
- Rob Hubbard and David Whittaker keep the loop flag at the same voice offset.
  `data/disasm/RobHubbard.cnf:Voices`

The tool's other runs are generic: register clears in `StopSound`, zero loads in
`Sweep`.

## Shares

| Pair                         | Instructions in shared runs |
| ---------------------------- | --------------------------- |
| Rob Hubbard, David Whittaker | 36 of Rob Hubbard's 235     |
| Rob Hubbard, Fred            | 30 of Rob Hubbard's 235     |
| David Whittaker, Fred        | 50 of David Whittaker's 369 |

## What differs

| Aspect      | Rob Hubbard                  | David Whittaker                        | Fred                             |
| ----------- | ---------------------------- | -------------------------------------- | -------------------------------- |
| Note timing | A length byte in each note   | A length byte that stays until changed | One row per note, plus wait rows |
| Volume      | Fixed per instrument         | Volume list                            | Timed ADSR                       |
| Pitch       | Vibrato scaled by the period | Pitch list, slide, vibrato             | Arpeggio table, glide, vibrato   |
| Synthesis   | Sweep in a shared wave       | None                                   | Pulse and morph per voice        |
| Game sound  | None                         | Sound effects, register shadows        | `VoiceMask` only                 |

So the streams, the instruments and the synthesis are separate designs. No card
can be a delta of another.

## Origin

UADE's David Whittaker player credits "David Whittaker & Rob Hubbard". So both
may have used one driver (guess). Fred's replay may build on the same driver
(guess).
