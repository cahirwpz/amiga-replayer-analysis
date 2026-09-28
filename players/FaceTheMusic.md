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

- Each track can run a track program: 4-byte lines of opcodes. It runs until a
  line waits. `:ScriptRun` `:ScriptWait`
  - Enables: sound design beside the notes, with loops, branches and calls into
    other programs. `:ScriptLoop` `:ScriptChain`
  - Costs: a loop without a wait hangs the player.
- A program sets handlers: lines that run when an event arrives. Events are a
  new pitch, volume or sample, a release, a portamento and a fade.
  `:ScriptEvent` `:PatternEvent`
  - Enables: one program serves every note, and reacts to the part of the note
    that changed.
- A program acts on a work track, which can be any track. It can read, copy or
  clone other tracks. `:SelectTrack` `:CopyPitch` `:CloneTrack`
  - Enables: one track steers another, e.g. an echo or a chord.
- Four LFOs per track. A target can be pitch, volume, or another LFO's speed or
  depth. `:Lfos`
  - Enables: modulation of modulation, even across tracks.
- Eight tracks share four channels, two per channel. `:MixPairs`
  - Enables: eight parts with one resampled track per channel. See
    [voice mixing](../ideas/voice-mixing.md).
  - Costs: high CPU: two reads, a table read and an add per output byte.

## Composer's view

The composer writes one event list per track and a set of programs.

| Aspect   | Answer                                                          | Source          |
| -------- | --------------------------------------------------------------- | --------------- |
| Notation | A note event: pitch, sample and volume in one word.             | `:PatternEvent` |
| Notation | A wait word holds the rows until the next event.                | `:TrackRow`     |
| Notation | A track without wait words spaces its events evenly.            | `:TrackRow`     |
| Notation | `START_SCRIPT` starts a program on the track.                   | `:PatternEvent` |
| Notation | `PORTAMENTO` slides to a pitch over N rows.                     | `:Portamento`   |
| Notation | `FADE` fades to silence over N rows.                            | `:Fade`         |
| Notation | A note without a sample keeps a looping sample playing: legato. | `:PatternEvent` |
| Cost     | A note event spans 34 semitones.                                | `:PatternEvent` |
| Cost     | Pitch moves in steps of 1/8 semitone.                           | `:SetPitch`     |
| Cost     | Volume nibble 3 gives 0, not about 14.                          | `:PatternEvent` |
| Cost     | A loud pair wraps around: nothing clips the sum.                | `:MixPair`      |
| Cost     | One loop counter per track: loops do not nest.                  | `:ScriptLoop`   |

## What is unique

- Within one row, a later event's handler replaces an earlier one. Pitch beats
  volume, and volume beats sample. `:PatternEvent`
- The lower track of a pair jumps to its loop start early, by its pitch ratio.
  `:MixPair`
- A clone copies the detune pointer too. So the clone's detune changes the
  source's pair. `:CloneTrack`
- Two ops that move the sample start store a leftover register.
  `:AddSampleStart` `:SubSampleStart`

## Open questions

- Which modules use handlers and cross-track programs?
- Do real modules keep samples at half level to avoid the wrap-around?
