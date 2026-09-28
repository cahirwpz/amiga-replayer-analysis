---
player: JasonPage
template: 2
ideas:
  [
    instrument-programs,
    effect-priority,
    game-branch-markers,
    song-save-slots,
    per-voice-positions,
    wave-morph,
  ]
---

# Jason Page

Notes and game sound effects ask for the same instrument programs. A priority
decides which one gets the voice.

## Context

| Fact      | Value                                                          |
| --------- | -------------------------------------------------------------- |
| Player    | `JasonPage`                                                    |
| Author    | Jason Page                                                     |
| Year      | 1995                                                           |
| Game      | ViroCop                                                        |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/JasonPage` |
| Spec      | [specs/jason_page.py](../specs/jason_page.py)                  |

## Key ideas

- A pattern note and a game sound effect make the same request for an instrument
  program. A request below the voice's priority is dropped. `:NotePeriod`
  `:RequestProgram` `:OpEnd`
  - Enables: an important sound effect cuts the music, and a minor one waits.
  - Costs: a note is lost while a program of higher priority plays.
- Branch markers in a position list take a position that the game wrote. One
  marker loops until then, the other plays on. `:BranchLoop` `:BranchPass`
  - Enables: music that changes section on a game event, at a musical boundary.
  - Costs: every voice must reach its marker in the same row.
- The game can save the song's place in one of four slots, then restore it.
  `:SaveSong` `:RestoreSong`
  - Enables: a short tune interrupts the music, which then plays on.
- An instrument program runs word opcodes every tick. It sets sample, length,
  pitch and envelope, loops and waits. `:RunProgram`
- A program can move the sample's loop start and length every tick.
  `:OpMoveStart` `:OpAddOffset` `:WriteChannel`
  - Enables: sweeps through a long sample of many waves (inference).
- A program can copy one wave over another. It can also morph a wave towards
  another, one step per byte. `:OpCopyWave` `:OpMorph`
  - Enables: slow timbre changes from two stored waves.
  - Costs: the morph rewrites sample memory, so every voice that plays the wave
    hears it.

## Composer's view

The composer writes a position list per voice, patterns, and instrument
programs.

| Aspect   | Answer                                                             | Source                       |
| -------- | ------------------------------------------------------------------ | ---------------------------- |
| Notation | A position word: a pattern and a transpose.                        | `:ReadPosition`              |
| Notation | A position word may be a marker and its target instead.            | `:ReadPosition`              |
| Notation | Pattern bytes: note, row length, program number, rest, slide, cap. | `:ReadPattern`               |
| Notation | A program: word opcodes, most with one word argument.              | `:RunProgram`                |
| Cost     | A note lasts its voice's row length. A new length takes one byte.  | `:ReadPattern`               |
| Cost     | `SLIDE_TO_NOTE` slides to each note instead of starting a program. | `:NoteSlide`                 |
| Cost     | A program must start the sound itself, with a DMA opcode.          | `:OpDmaOn`                   |
| Cost     | The first voice that reaches its end marker ends the song.         | `:ReadPosition`              |
| Cost     | An arpeggio is a program loop of note offsets and waits.           | `:OpNoteOffset` `:OpLoopEnd` |

## What is unique

- The master volume caps each voice. It does not scale them, so a fade reaches
  loud voices first. `:WriteChannel`
- A pattern byte sets a volume cap. It acts only when the program asks, and only
  during sustain. `:OpCeiling` `:EnvelopeTick`
- The morph compares bytes unsigned. A byte that crosses 0 passes through +127
  and -128. `:OpMorph`

## Open questions

- Restoring a slot writes into later slots, and from slot 1 into sample
  pointers. Did a game use those slots? `:RestoreSong`
- Which games used the branch markers, and for what? `:BranchLoop`
- The header has room for eight position lists, and the Amiga uses four. Are the
  others for the format's versions on other machines (guess)? `:InitModule`
