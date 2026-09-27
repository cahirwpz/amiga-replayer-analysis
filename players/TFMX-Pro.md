---
player: TFMX-Pro
template: 2
ideas:
  [
    macro-instruments,
    tracks-not-voices,
    self-modifying-macros,
    resampling-synthesis,
    random-riffs,
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
- A note restarts only the macro. Effects, volume and sample carry over.
  `:NoteToVoice`
  - Enables: a new note can keep a running vibrato or glide.
  - Costs: a macro must clear old effects itself. `:ClearEffects`
- A riff plays a macro's bytes as note offsets. It can jump at random and echo
  on the next voice. `:RiffTick` `:RiffRandom` `:RiffEcho`
  - Enables: generative melody from a few bytes.
  - Costs: all riff steps have the same length.
- [IMS](../details/TFMX-Pro-IMS.md) rebuilds a voice's wave every tick, as a
  hard sync with a slew limiter. `:ImsTick`
  - Enables: sync and filter sweeps from one short sample.
  - Costs: CPU high: up to 256 bytes per voice per tick.
- Macros rewrite macros. `:CopyToMacro` `:AddToMacro`
  - Enables: a sound that changes each time it plays.
  - Costs: every voice that plays the macro sees the change.

## Composer's view

The composer writes patterns and macros. TFMX calls an instrument program a
`macro`. Positions start one pattern per track.

| Aspect   | Answer                                                           | Source                          |
| -------- | ---------------------------------------------------------------- | ------------------------------- |
| Notation | Pattern entry: note, macro, volume, voice, detune.               | `:TrackNote`                    |
| Notation | Macro statement: an opcode and three argument bytes.             | `:MacroStep`                    |
| Notation | A waiting note or a wait opcode sets the rows to the next entry. | `:ReadPattern`                  |
| Cost     | A chord is several entries on one track, one per voice.          | `:ReadPattern`                  |
| Cost     | An arpeggio is a macro loop of notes and waits.                  | `:AddNote` `:MacroLoop`         |
| Cost     | ADSR: attack, wait, decay, note-off wait, release statements.    | `:MacroEnvelope` `:WaitNoteOff` |

## What is unique

- A macro runs statements until a wait or a note opcode ends the tick.
  `:EndMacroTick`
- A delayed DMA off acts at the next tick's start, with the shortest period. The
  macro then restarts the sample in that tick. `:DmaOff` `:PlayTick`
- A macro can wait for N passes of its sample. `:WaitLoops`
- A macro can wait for a riff step with bit 7 set. `:MacroWait`
- Each envelope opcode ramps to a target and stops, so phases are opcodes.
  `:MacroEnvelope`
- During portamento, a riff sets only the glide's target and stays on its step.
  `:RiffTick`
- The fade counter moves once per voice, so four times per tick. `:FadeTick`

## Open questions

- Which songs use riffs, byte checks and macro rewrites?
- The source calls the riff code the Ballblazer routine. Is it modelled on
  Ballblazer's riff music (guess)?
