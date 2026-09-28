---
player: VoodooSupremeSynthesizer
template: 2
ideas:
  [
    voice-streams,
    chunk-pitch-shift,
    double-buffered-waves,
    volume-list,
    pitch-list,
  ]
---

# Voodoo Supreme Synthesizer

Each audio interrupt plays the next 128-byte chunk of a long sample.

## Context

| Fact      | Value                                                                         |
| --------- | ----------------------------------------------------------------------------- |
| Player    | `VoodooSupremeSynthesizer`                                                    |
| Author    | Tomas Partl                                                                   |
| Year      | 1993                                                                          |
| Code read | ira: `data/disasm/VoodooSupremeSynthesizer.cnf`                               |
| Spec      | [specs/voodoo_supreme_synthesizer.py](../specs/voodoo_supreme_synthesizer.py) |

## Key ideas

- In chunk mode, each audio interrupt starts the next chunk. It then moves a
  pointer by a step. `:NextChunk`
  - Enables: the sample advances at the base note's speed at every pitch. The
    step is 128 × period ÷ the base note's period. `:ChunkStep`
  - Enables: a table can move the pointer to any place in the sample.
    `:ChunkTable`
  - Costs: one audio interrupt per chunk and voice.
- The other modes fill the idle half of a 2 × 32-byte buffer every tick. Paula
  plays the other half. `:SetHardware`
  - Enables: changes never tear a wave in the middle of a pass.
  - Enables: three ways to combine two samples. Mix averages them, exclusive or
    flips bits, morph moves one toward the other. `:MixWaves` `:XorWaves`
    `:MorphWave`
- Exclusive or and morph read the playing half, not the samples. So their
  changes add up from tick to tick. `:XorWaves` `:MorphWave`
- Each voice reads its own byte stream. Calls and loops share one small stack
  per voice. `:CmdCall` `:CmdLoopStart` `:CmdLoop`
  - Enables: a stream reuses parts and repeats them N times, nested.
  - Costs: 80 bytes per voice. Nothing checks for overflow.
- Three table walkers run per note: volume, period and wave. A keep flag leaves
  a walker running across notes. `:ReadStream` `:CmdKeepFlags`
- An interval command multiplies the period by a small fraction, e.g. 107/101
  for a semitone. `:Interval`
  - Enables: pitch steps without a period table for every note.

## Composer's view

The composer writes one stream per voice and draws tables. The format calls the
wave walker's table a `waveform command table`.

| Aspect   | Answer                                                      | Source            |
| -------- | ----------------------------------------------------------- | ----------------- |
| Notation | A note: a note byte, then its length in ticks.              | `:ReadStream`     |
| Notation | `$81` calls another stream.                                 | `:CmdCall`        |
| Notation | `$82` returns from it.                                      | `:CmdReturn`      |
| Notation | `$83` starts a loop with a count.                           | `:CmdLoopStart`   |
| Notation | `$84` closes the loop.                                      | `:CmdLoop`        |
| Notation | `$8B` jumps to another stream.                              | `:CmdGoto`        |
| Notation | `$85` picks two samples.                                    | `:CmdSamples`     |
| Notation | `$88` picks a wave table and its mode.                      | `:CmdWaveTable`   |
| Notation | `$89` slides between two notes, and plays as a note.        | `:CmdPortamento`  |
| Notation | `$FF` cuts the note, then waits.                            | `:NoteCut`        |
| Notation | A volume entry sets a level, or adds a delta for N ticks.   | `:VolumeEnvelope` |
| Notation | A period entry shifts octaves, steps an interval or slides. | `:PeriodCommand`  |
| Cost     | Period and volume reach Paula one tick late.                | `:SetHardware`    |
| Cost     | Volume wraps: an envelope must stop its own delta.          | `:VolumeEnvelope` |
| Cost     | A slide between equal notes crashes: it divides by zero.    | `:CmdPortamento`  |
| Cost     | The song ends only when four gotos run in the same tick.    | `:Tick`           |

## What is unique

- Past the sample's end, a voice plays silence until the next chunk table entry
  or note. `:NextChunk`
- The mix mode sets bits in each byte's magnitude. This adds distortion that
  keeps the sign. `:MixWaves`
- The period table's lowest B is `$4519`, not `$4280`. It plays about 66 cents
  flat. `:NotePeriod`

## Open questions

- Which modules use chunk mode with the step that follows the period?
- Does the lowest octave ever play? On a 32-byte wave, its notes are below 7 Hz.
