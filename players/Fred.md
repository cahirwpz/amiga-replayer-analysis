---
player: Fred
template: 2
ideas: [replay-in-module, byte-write-sweep, in-place-waveform-effects]
---

# Fred

Each voice builds its own wave. A pulse moves an edge one byte per step. A morph
adds scaled deltas to a wave.

## Context

| Fact      | Value                                      |
| --------- | ------------------------------------------ |
| Player    | `Fred`                                     |
| Author    | Frederic Hahn                              |
| Game      | Fuzzball                                   |
| Code read | ira: `ext/uade/amigasrc/players/uade/fred` |
| Spec      | [specs/fred.py](../specs/fred.py)          |

## Key ideas

- A pulse wave holds low bytes below the edge and high bytes above it. Each step
  moves the edge by one byte, between two positions. `:Pulse` `:PulseInit`
  - Enables: a pulse-width sweep, as on the C64, for one byte write per step.
  - Costs: the wave is at most 64 bytes long.
- Each tick, a morph instrument rewrites 32 bytes. Each byte is the source plus
  the step times a delta. `:MorphStep` `:MorphWrite`
  - Enables: a wave morphs into a second shape and back.
  - Costs: medium CPU. It takes 32 multiplies per tick per voice, about 2% of a
    frame (estimate).
- Each voice owns its buffer. So two voices on one instrument sweep
  independently. `:Voice`
- Restart flags choose whether each note restarts the sweep. An `INSTRUMENT`
  command always restarts it. `:NoteOn`
  - Enables: one sweep can run through a whole phrase.
- A turn count can stop a sweep after N turns. `:Pulse` `:MorphStep`
- The ADSR is timed. The release starts after a set number of sustain ticks.
  `:Envelope` `:Sustain`
  - Costs: the note's length cannot end the sustain.

## Composer's view

The composer writes one track per voice. A track is a list of patterns. A
pattern is a stream of notes, waits and commands.

| Aspect   | Answer                                                           | Source           |
| -------- | ---------------------------------------------------------------- | ---------------- |
| Notation | A note byte lasts one row.                                       | `:NoteOn`        |
| Notation | A wait byte adds 1 to 123 rows.                                  | `:ReadStream`    |
| Notation | A wait after a note ties the note.                               | `:CountDown`     |
| Notation | `INSTRUMENT`, `SPEED`, `PORTAMENTO` come before a note.          | `:ReadStream`    |
| Notation | `REST` silences the voice for one row.                           | `:Rest`          |
| Notation | `PATTERN_END` goes to the track's next pattern.                  | `:NextPosition`  |
| Notation | A track word with `TRACK_JUMP` loops the track.                  | `:NextPosition`  |
| Notation | `TRACK_END` stops the song.                                      | `:SongEnd`       |
| Notation | Arpeggio, vibrato, ADSR, pulse and morph live in the instrument. | `:Instrument`    |
| Cost     | DMA goes off one tick before the next note or command.           | `:CountDown`     |
| Cost     | `SPEED` on one voice sets the speed of all voices.               | `:SetSpeed`      |
| Cost     | A glide's length is set before its note.                         | `:SetPortamento` |
| Cost     | A glide's target note is set before its note.                    | `:SetPortamento` |
| Cost     | A glide's delay is set before its note.                          | `:SetPortamento` |
| Cost     | Vibrato depth is in period units.                                | `:Vibrato`       |
| Cost     | Low notes get a smaller vibrato interval.                        | `:Vibrato`       |

## What is unique

- Effects run only while Paula reports the channel's DMA as on. So a `REST`
  freezes the envelope, arpeggio and sweep. `:Arpeggio`
- A glide adds its share on top of the arpeggio. At its end, the note becomes
  the target note. `:Portamento`
- A glide runs on across later notes. Only its first note sets its start and
  distance. `:NoteOn`
- A fade lowers the volume once per playing voice. Four voices fade four times
  as fast as one. `:Volume`
- Notes below 32 keep DMA on before them. The gap test compares signed bytes.
  `:CountDown`
- The loop offset moves the start in bytes. It shortens the length in words.
  `:QueueLoop`

## Open questions

- Which Fred Editor modules use morph instruments? The three Fuzzball modules
  use none.
- Is the missing gap before notes below 32 intended? (guess: a wrong branch)
- `fred.title`'s one sample runs 138 bytes past the end of the file. Is the file
  cut short?
