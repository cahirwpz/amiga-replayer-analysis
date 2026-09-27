---
player: TFMX-Pro
template: 2
ideas:
  [
    instrument-programs,
    tracks-not-voices,
    self-modifying-programs,
    resampling-synthesis,
    random-offset-loops,
  ]
---

# TFMX Pro

An instrument is a program that runs once per tick and shapes one note.

## Context

| Fact      | Value                                                      |
| --------- | ---------------------------------------------------------- |
| Player    | `TFMX-Pro`                                                 |
| Author    | Chris Hülsbeck                                             |
| Family    | TFMX                                                       |
| Code read | original: `ext/uade/amigasrc/players/wanted_team/TFMX-Pro` |
| Spec      | [specs/tfmx_pro.py](../specs/tfmx_pro.py)                  |

## Key ideas

- An instrument program has 52 opcodes. They include waits, loops, one call and
  branches on note, volume and note-off. `:MacroStep` `:SplitByNote`
  `:WaitNoteOff`
  - Enables: attack, sustain and release parts, each its own code.
  - Costs: each sound is written as code.
- Eight tracks share the voices; each note names its voice. `:TrackNote`
  `:NoteToVoice`
  - Enables: one track plays chords or moves a line across voices.
  - Costs: two tracks can take the same voice.
- A note restarts only the instrument program. Effects, volume and sample carry
  over. `:NoteToVoice`
  - Enables: a new note can keep a running vibrato or portamento.
  - Costs: a program must clear old effects itself. `:ClearEffects`
- An offset loop, TFMX's `riff`, plays another program's bytes as note offsets.
  It can jump at random and echo on the next voice. `:RiffTick` `:RiffRandom`
  `:RiffEcho`
  - Enables: generative melody from a few bytes.
  - Costs: every offset plays for the same number of ticks.
- [IMS](../details/TFMX-Pro-IMS.md) rebuilds a voice's wave every tick, as a
  hard sync with a slew limiter. `:ImsTick`
  - Enables: sync and filter sweeps from one short sample.
  - Costs: CPU high: up to 256 bytes per voice per tick.
- Programs rewrite programs. `:CopyToMacro` `:AddToMacro`
  - Enables: a sound that changes each time it plays.
  - Costs: every voice that plays the program sees the change.

## Composer's view

The composer writes patterns and instrument programs. TFMX calls an instrument
program a `macro`. Positions start one pattern per track.

| Aspect   | Answer                                                          | Source                          |
| -------- | --------------------------------------------------------------- | ------------------------------- |
| Notation | Pattern entry: note, instrument program, volume, voice, detune. | `:TrackNote`                    |
| Notation | Program step: an opcode and three argument bytes.               | `:MacroStep`                    |
| Notation | A note's wait or a wait opcode sets the rows to the next entry. | `:ReadPattern`                  |
| Cost     | A chord is several entries on one track, one per voice.         | `:ReadPattern`                  |
| Cost     | An arpeggio is a program loop of notes and waits.               | `:AddNote` `:MacroLoop`         |
| Cost     | ADSR: attack, wait, decay, note-off wait, release steps.        | `:MacroEnvelope` `:WaitNoteOff` |

## What is unique

- A program runs steps until a wait or a note opcode ends the tick.
  `:EndMacroTick`
- A delayed DMA off acts at the next tick's start. The program then restarts the
  sample in that tick. `:DmaOff` `:PlayTick`
- A program can wait for N passes of its sample. `:WaitLoops`
- A program can wait for an offset byte with bit 7 set. Its first pass there
  only arms the wait. `:MacroWait` `:RiffTick`
- Each envelope opcode ramps to a target and stops, so phases are opcodes.
  `:MacroEnvelope`
- During portamento, an offset loop sets only the target and stays on its
  offset. `:RiffTick`
- The fade counter moves once per voice, so four times per tick. `:FadeTick`

## Open questions

- Which songs use offset loops, byte checks and program rewrites?
- The source calls the offset loop code the Ballblazer routine. Is it modelled
  on Ballblazer's music (guess)?
