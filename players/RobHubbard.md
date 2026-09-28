---
player: RobHubbard
template: 2
ideas:
  [replay-in-module, byte-write-sweep, sample-rate-tune, period-scaled-vibrato]
---

# Rob Hubbard

A tiny replay inside each module. One byte written per tick sweeps the pulse
width of a short wave.

## Context

| Fact      | Value                                                   |
| --------- | ------------------------------------------------------- |
| Player    | `RobHubbard`                                            |
| Author    | Rob Hubbard                                             |
| Year      | 1990                                                    |
| Game      | PGA Tour Golf                                           |
| Code read | ira: `ext/uade/amigasrc/players/wanted_team/RobHubbard` |
| Spec      | [specs/rob_hubbard.py](../specs/rob_hubbard.py)         |

## Key ideas

- The replay ships inside each module. Five `bra.w` entries start it; 830 bytes
  of code follow. `:Play` `:InitSong`
  - Enables: each game gets the replay its music was written for.
  - Costs: every module has its own copy. The two PGA Tour Golf modules differ.
    See [What is unique](#what-is-unique).
- A sweep writes one byte per tick into a 16-byte wave. So an edge moves between
  two bounds. `:Sweep` `:SweepDown`
  - Enables: a pulse-width sweep, as on the C64, for one byte write per tick.
  - Costs: the wave is shared, so every voice on the instrument hears it.
- Each sample stores its recording rate. The period is scaled by it.
  `:InitSamples` `:NoteOn`
  - Enables: samples at any rate play in tune.
- Vibrato adds a share of the period, not a fixed amount. `:Vibrato`
  - Enables: the vibrato has the same interval on every note.

## Composer's view

The composer writes a position list per voice and patterns of bytes.

| Aspect   | Answer                                                              | Source          |
| -------- | ------------------------------------------------------------------- | --------------- |
| Notation | A note: a length byte up to 127, then a note byte.                  | `:NoteOn`       |
| Notation | `$80`: instrument. `$81`: portamento step. `$82`: rest with length. | `:ReadStream`   |
| Notation | `$84`: pattern end. `$85`: stop.                                    | `:ReadStream`   |
| Notation | A position list of pattern offsets. Offset 0 wraps to the start.    | `:NextPosition` |
| Cost     | A length counts in units of the song's speed.                       | `:NoteOn`       |
| Cost     | Portamento lasts one note. The next event clears it.                | `:CountDown`    |
| Cost     | Volume is fixed per instrument. There is no envelope.               | `:NoteOn`       |
| Cost     | DMA goes off one tick before each event. Every note ends in a gap.  | `:CountDown`    |
| Cost     | Loop offset 0 plays once. A negative offset loops the whole sample. | `:QueueLoop`    |

## What is unique

- The sweep turns one byte past its upper bound. In `rh.GMUSIC` it writes into
  the first song's unused first byte. `:Sweep`
- `rh.GMUSIC` clears the song number, so it always plays song 0. `rh.FLYMUS`
  plays the song it is given. `:InitSong`
- `rh.GMUSIC` sets up 11 samples; `rh.FLYMUS` sets up 6. The rest of the code is
  the same. `:InitSamples`
- In PGA Tour Golf, only the three built-in waves use vibrato or the sweep. The
  samples use neither. `:InitWaves`

## Open questions

- Do other Rob Hubbard modules sweep samples, not only waves?
