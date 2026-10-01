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

- A request below the voice's priority is dropped. `:NotePeriod`
  `:RequestProgram` `:OpEnd`
  - Enables: an important sound effect cuts the music. A minor one is dropped.
  - Costs: a note is lost while a program of higher priority plays.
- Branch entries in a position list take a position that the game wrote. One
  entry loops until then, the other plays on. `:BranchLoop` `:BranchPass`
  - Enables: music that changes part on a game event, at a musical boundary.
  - Costs: every voice must reach its branch entry in the same row.
- The game can save the song's place in one of four slots. It can restore it
  later. `:SaveSong` `:RestoreSong`
  - Enables: a short tune interrupts the music. Then the music plays on.
- An instrument program runs word opcodes every tick. It sets sample, length,
  pitch and envelope, loops and waits. `:RunProgram`
- A program can move the sample's loop start and length every tick.
  `:OpMoveStart` `:OpAddLength` `:OpAddOffset` `:WriteChannel`
  - Enables: sweeps through a long sample of many waves (inference).
- A program can copy one wave over another. It can also morph a wave towards
  another, one step per byte. `:OpCopyWave` `:OpMorph`
  - Enables: slow timbre changes from two stored waves.
  - Costs: the morph rewrites sample memory. Every voice that plays the wave
    hears it.

## Composer's view

The composer writes a position list per voice, patterns, and instrument
programs.

| Aspect   | Answer                                                              | Source                       |
| -------- | ------------------------------------------------------------------- | ---------------------------- |
| Notation | A position word: a pattern and a transpose.                         | `:ReadPosition`              |
| Notation | A position word may be a branch entry and its target instead.       | `:ReadPosition`              |
| Notation | Pattern bytes: note, note length, program number, rest, slide, cap. | `:ReadPattern`               |
| Notation | A program: word opcodes, most with one word argument.               | `:RunProgram`                |
| Cost     | A note lasts its voice's note length, in rows.                      | `:ReadPattern`               |
| Cost     | A new note length takes one byte.                                   | `:ReadPattern`               |
| Cost     | `SLIDE_TO_NOTE` slides to each note instead of starting a program.  | `:NotePeriod` `:NoteSlide`   |
| Cost     | A program number from `FIRST_TIE` up plays the note legato.         | `:NotePeriod`                |
| Cost     | The release starts after a set number of ticks. No note-off does.   | `:EnvelopeTick`              |
| Cost     | A program must start the sound itself, with a DMA opcode.           | `:OpDmaOn`                   |
| Cost     | The first voice that reaches its end entry ends the song.           | `:ReadPosition`              |
| Cost     | An arpeggio is a program loop of note offsets and waits.            | `:OpNoteOffset` `:OpLoopEnd` |

## What is unique

- The master volume caps each voice instead of scaling it. A fade reaches loud
  voices first. `:WriteChannel`
- A pattern byte sets a volume cap. It acts only during sustain, when the
  program asks for it. `:OpCeiling` `:EnvelopeTick`
- The morph compares bytes unsigned. A byte that crosses 0 passes through +127
  and -128. `:OpMorph`

## Open questions

- Restoring a slot writes into later slots, and from slot 1 into sample
  pointers. Did a game use those slots? `:RestoreSong`
- Which games used the branch entries, and for what? `:BranchLoop`
- The Amiga uses four of the header's eight position lists. Are the others for
  the format's versions on other machines (guess)? `:InitModule`
