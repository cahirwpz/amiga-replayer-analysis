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

- Each module carries its own replay behind five jump entries. `:Play`
  `:InitSong`
  - Enables: each game gets the replay its music was written for.
  - Costs: every module repeats about 830 bytes of replay (estimate).
- A sweep writes one byte per tick into a short wave, like [Fred](Fred.md)'s
  pulse wave. `:Sweep` `:SweepDown`
  - Costs: every voice on the instrument shares the wave.
- Each sample stores its recording rate. The period is scaled by it.
  `:InitSamples` `:NoteOn`
  - Enables: samples at any rate play in tune.
- Vibrato adds a share of the period, not a fixed amount. `:Vibrato`
  - Enables: the vibrato has the same interval on every note.

## Composer's view

The composer writes a position list per voice and patterns of bytes.

| Aspect   | Answer                                                                   | Source                     |
| -------- | ------------------------------------------------------------------------ | -------------------------- |
| Notation | A note: a length byte up to `NOTE_MAX`, then a note byte.                | `:NoteOn`                  |
| Notation | `INSTRUMENT` picks the instrument.                                       | `:ReadStream`              |
| Notation | `PORTAMENTO` sets one pitch step per tick.                               | `:ReadStream`              |
| Notation | `REST` takes a length.                                                   | `:ReadStream`              |
| Notation | `PATTERN_END` ends the pattern.                                          | `:ReadStream`              |
| Notation | `STOP` on any voice stops the whole song.                                | `:ReadStream` `:StopSound` |
| Notation | A negative `INSTRUMENT` number plays the game's instrument for the song. | `:SetInstrument`           |
| Notation | A position list holds pattern offsets.                                   | `:NextPosition`            |
| Notation | Offset 0 wraps to the first position.                                    | `:NextPosition`            |
| Cost     | A length counts in units of the song's speed.                            | `:NoteOn`                  |
| Cost     | Portamento lasts one note. The next event clears it.                     | `:CountDown`               |
| Cost     | Volume is fixed per instrument, with no envelope.                        | `:NoteOn`                  |
| Cost     | DMA goes off one tick before each event. Every note ends in a gap.       | `:CountDown`               |
| Cost     | Loop offset 0 plays the sample once.                                     | `:QueueLoop`               |
| Cost     | A negative loop offset loops the whole sample.                           | `:QueueLoop`               |

## What is unique

- The sweep turns one byte past its upper bound. In `rh.GMUSIC` it writes into
  the first song's unused first byte. `:Sweep`
- `rh.GMUSIC` clears the song number and always plays song 0. `rh.FLYMUS` plays
  the song it is given. `:InitSong`
- `rh.GMUSIC` sets up 11 samples and `rh.FLYMUS` 6. The rest of the code is the
  same. `:InitSamples`
- In PGA Tour Golf, the three built-in waves carry vibrato and sweep settings.
  `:InitWaves` `:Instrument`

## Open questions

- Do other Rob Hubbard modules sweep samples, not only waves?
