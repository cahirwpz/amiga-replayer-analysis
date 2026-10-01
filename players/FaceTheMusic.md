---
player: FaceTheMusic
template: 2
ideas: [track-programs, voice-mixing, tracks-not-voices]
---

# Face The Music

Track programs react to events and steer any of eight mixed tracks.

## Context

| Fact      | Value                                                 |
| --------- | ----------------------------------------------------- |
| Player    | `FaceTheMusic`                                        |
| Author    | J. Schmidt                                            |
| Year      | 1991                                                  |
| Code read | ira: `data/disasm/FaceTheMusic.cnf`                   |
| Spec      | [specs/face_the_music.py](../specs/face_the_music.py) |

## Key ideas

- Each track can run a track program of 4-byte opcode lines. It runs until a
  line waits. `:ScriptRun` `:ScriptWait`
  - Enables: sound design beside the notes, with loops, branches and jumps into
    other programs. `:ScriptLoop` `:ScriptChain`
  - Costs: a loop without a wait hangs the player.
- A program sets handlers: lines that run when an event arrives. Events are a
  new pitch, volume or sample, a release, a portamento and a fade.
  `:ScriptEvent` `:PatternEvent`
  - Enables: one program serves every note. It reacts to the part of the note
    that changed.
- A program acts on a work track, which can be any track. It can read, copy or
  clone other tracks. `:SelectTrack` `:CopyPitch` `:CloneTrack`
  - Enables: one track steers another, e.g. an echo or a chord.
- Four LFOs per track. A target can be pitch, volume, or another LFO's speed or
  depth. `:Lfos`
  - Enables: modulation of modulation, even across tracks.
  - Enables: LFOs stack. Each adds only its wave's change since the last tick.
- Eight tracks share four channels, two per channel. `:MixPairs`
  - Enables: eight parts with one resampled track per channel. See
    [voice mixing](../ideas/voice-mixing.md).
  - Costs: high CPU. Each output byte takes two reads, a table read and an add.

## Composer's view

The composer writes one event list per track and a set of programs.

| Aspect   | Answer                                                              | Source                            |
| -------- | ------------------------------------------------------------------- | --------------------------------- |
| Notation | A note event: pitch, sample and volume in one word.                 | `:PatternEvent`                   |
| Notation | A wait word holds the rows until the next event.                    | `:TrackRow`                       |
| Notation | A track without wait words spaces its events evenly.                | `:TrackRow`                       |
| Notation | `START_SCRIPT` starts a program on the track.                       | `:PatternEvent`                   |
| Notation | `PORTAMENTO` slides to a pitch over N rows.                         | `:Portamento`                     |
| Notation | `FADE` fades to silence over N rows.                                | `:Fade`                           |
| Notation | A note without a sample plays a looping sample on, legato.          | `:PatternEvent`                   |
| Notation | `REPEAT` with a count opens a repeat.                               | `:Repeat`                         |
| Notation | `REPEAT` without a count closes a repeat.                           | `:Repeat`                         |
| Notation | Opcodes set, add to or subtract from the loop length during a note. | `:SetLoopLength` `:AddLoopLength` |
| Cost     | A release event does nothing without a release handler.             | `:PatternEvent`                   |
| Cost     | A note event spans 34 semitones.                                    | `:PatternEvent`                   |
| Cost     | Pitch moves in steps of 1/8 semitone.                               | `:SetPitch`                       |
| Cost     | Volume value 3 gives 0 (guess: a typo for 14).                      | `:PatternEvent`                   |
| Cost     | Nothing clips a pair's sum. A loud pair wraps around.               | `:MixPair`                        |
| Cost     | Program loops do not nest. A track has one loop counter.            | `:ScriptLoop`                     |

## What is unique

- At the end of a repeat's measure, every track seeks back. Repeats nest.
  `:Repeat`
- Within one note event, a later part's handler replaces an earlier one. Pitch
  beats volume, and volume beats sample. `:PatternEvent`
- The lower track of a pair jumps to its loop start early, by its pitch ratio.
  `:MixPair`
- A clone copies the detune pointer too. The clone's detune changes the source's
  pair. `:CloneTrack`
- Two opcodes that move the sample start have bugs. They use the wrong register.
  `:AddSampleStart` `:SubSampleStart`

## Open questions

- Which modules use handlers and cross-track programs?
- Do real modules keep samples at half level to avoid the wrap-around?
