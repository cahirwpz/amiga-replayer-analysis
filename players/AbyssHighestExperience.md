---
player: AbyssHighestExperience
template: 2
ideas:
  [
    generated-waves,
    filter-bank,
    sweep-between-limits,
    performance-list,
    hard-cut,
    free-running-buffer,
  ]
---

# AHX

No samples: every sound comes from built-in waves and their filtered copies.

## Context

| Fact      | Value                                                                     |
| --------- | ------------------------------------------------------------------------- |
| Player    | `AbyssHighestExperience`                                                  |
| Code read | ira: `data/disasm/AbyssHighestExperience.cnf`                             |
| Spec      | [specs/abyss_highest_experience.py](../specs/abyss_highest_experience.py) |

## Key ideas

- The player builds 45 waves at start. They are triangles and saws in 6 lengths,
  32 pulse widths, and noise. `:MakeWaves`
  - Enables: modules with no sample data.
  - Costs: 412 kB of memory for all waves and their copies.
- Each wave gets 31 low-pass and 31 high-pass copies. A filter position picks
  one copy. `:MakeFilters`
  - Enables: filter sweeps with no filter work during play.
  - Costs: the copies fill most of the 412 kB.
- Each voice loops one 640-byte buffer, and DMA never restarts. A new wave
  refills the buffer with copies of itself. `:FillBuffer` `:WriteVoice`
  - Enables: wave changes with no DMA restart and no busy-wait.
  - Enables: the wave length picks the octave.
  - Costs: a square or noise wave copies 640 bytes every tick.
- Pulse width and filter position run up and down between two limits. `:Sweep`
  - Enables: a moving timbre from a few instrument bytes.
- Each instrument runs an instrument program, `Performance`. A step sets wave
  and note, and runs two commands. `:PerformanceStep` `:PerformanceCommand`
  - Enables: arpeggios and wave changes inside one instrument.
- A note ends a set number of ticks before the next row that starts an
  instrument. The player reads that row early. `:HardCut`
  - Enables: short gaps between notes, set once in the instrument.

## Composer's view

The composer writes positions, tracks and instruments. A position gives each
voice a track and a transpose. An instrument holds an envelope, the sweep
settings and its program.

| Aspect   | Answer                                                                        | Source                |
| -------- | ----------------------------------------------------------------------------- | --------------------- |
| Notation | A row: note, instrument, command and argument.                                | `:ReadRow`            |
| Notation | A position: a track and a transpose for each voice.                           | `:ReadPosition`       |
| Notation | A step: wave, note, fixed-note flag, two commands.                            | `:PerformanceStep`    |
| Cost     | A note with `TONE_SLIDE` or `TONE_SLIDE_VOLUME` slides from the last note.    | `:ReadRow`            |
| Cost     | Sweep limits are for the longest wave. Shorter waves have fewer pulse widths. | `:SetInstrument`      |
| Cost     | A note delay or note cut needs a value below the speed.                       | `:ReadRow`            |
| Cost     | Revision 0 modules lack `FILTER_SET` and `FILTER_POSITION`.                   | `:PerformanceCommand` |

## What is unique

- A new wave starts where Paula is in the buffer. A note never restarts the
  wave. `:WriteVoice`
- Paula gets each tick's period and volume at the start of the next tick.
  `:PlayTick`
- A square wave is rebuilt every tick from a 128-byte square. `:BuildSquare`
- Noise starts at a new random offset every tick. `:NoiseOffset`
- A sweep that starts outside its limits runs in first. It turns only at the
  second limit it meets. `:Sweep`
- A filter copy starts from the state that three passes leave, not from silence.
  The player stores these states as a table. `:MakeFilters`

## Open questions

- Does the small external replayer differ in sound from the tracker's code?
- Which tool writes the wave file that `ENV:EaglePlayer/ahx` names?
