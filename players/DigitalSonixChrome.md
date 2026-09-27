---
player: DigitalSonixChrome
template: 2
ideas:
  [counted-loops, fixed-pitch-instruments, effects-steal-voices, stop-signal]
---

# Digital Sonix & Chrome

Audio interrupts count how often each instrument loops, so the tick only reads
rows.

## Context

| Fact      | Value                                                                   |
| --------- | ----------------------------------------------------------------------- |
| Player    | `DigitalSonixChrome`                                                    |
| Author    | Andrew E. Bailey and David M. Hanlon                                    |
| Year      | 1990                                                                    |
| Game      | Dragon's Breath                                                         |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/DigitalSonixChrome` |
| Spec      | [specs/digital_sonix_chrome.py](../specs/digital_sonix_chrome.py)       |

## Key ideas

- An instrument fixes the period. A row names only an instrument per voice.
  `:SetFixedPeriod` `:ReadRow`
  - Enables: a row takes one byte per voice.
  - Costs: every pitch of a sound takes its own instrument.
- An instrument plays its loop a set number of times, then silence. The audio
  interrupt counts the passes. `:SetLoopCount` `:CountLoopPass`
  - Enables: note lengths with no work in the tick.
  - Costs: a note's length is set in sample passes, not in rows.
- A game sound effect takes a voice until its loops end. `:SfxClaimVoice`
  `:ReadRow` `:LoopsDone`
  - Enables: music and sound effects share four channels.
  - Costs: the voice's music notes are lost while the sound effect plays.
- A note start waits for the channel's own
  [signal that it stopped](../docs/paula.md). `:StartNote` `:WaitAudioIrq`
  - Enables: DMA on restarts the channel, with no fixed wait.
  - Costs: the CPU busy-waits up to two periods of the old word per note.

## Composer's view

The composer writes positions, patterns and instruments. A pattern holds one
instrument number per voice per row. Nothing changes a note once it plays.

| Aspect   | Answer                                                  | Source            |
| -------- | ------------------------------------------------------- | ----------------- |
| Notation | A row: one instrument number per voice, or none.        | `:ReadRow`        |
| Notation | A position: a pattern, its rows and its repeat count.   | `:Position`       |
| Notation | The module's tempo sets the ticks per row.              | `:LoadModule`     |
| Cost     | A melody takes one instrument per pitch.                | `:SetFixedPeriod` |
| Cost     | A shorter note is an instrument with fewer loops.       | `:SetLoopCount`   |
| Cost     | A repeated pattern is one position with a repeat count. | `:CountRepeats`   |

## What is unique

- Speed = 1500 / tempo, rounded, once per module. No command changes it.
  `:LoadModule`
- Subsongs follow each other in one position list. A position with 0 repeats
  ends each one. `:StartSubsong` `:NextPosition`
- A lower sound effect number wins. A request of $80 or more is ignored.
  `:SfxClaimVoice`
- After the last pass, a 2-word silent loop plays. Its interrupt frees the
  voice. `:CountLoopPass` `:LoopsDone`

## Open questions

- Did any other game use this format?
- Wanted Team's interrupt handlers first wait for the next scanline. Did the
  original do this too?
