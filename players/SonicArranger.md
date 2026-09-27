---
player: SonicArranger
template: 2
ideas:
  [
    in-place-waveform-effects,
    waveform-as-table,
    per-voice-wave-copy,
    sustain-rows,
    beam-noise,
  ]
---

# Sonic Arranger

Seventeen wave effects rewrite each voice's own copy of its wave.

## Context

| Fact      | Value                                                               |
| --------- | ------------------------------------------------------------------- |
| Player    | `SonicArranger`                                                     |
| Author    | Carsten Schlote, Branko Mikiç and Carsten Herbst                    |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/Sonic_Arranger` |
| Spec      | [specs/sonic_arranger.py](../specs/sonic_arranger.py)               |

## Key ideas

- Each voice plays its own copy of the wave. Effects change the copy, never the
  instrument. `:StartSynthWave`
  - Enables: one wave that changes differently on each voice.
  - Costs: 128 bytes per voice.
- Every N ticks, the instrument's effect changes a byte range of the copy. The
  changes add up until the next note. `:WaveEffect`
  - Enables: a timbre that moves during the note, from one wave and a few
    settings.
  - Costs: medium CPU. Most effects touch every byte of the range, up to 128
    bytes per voice.
- Several effects read a second wave. It serves as a morph target, a pulse width
  table or a limit table. `:Effect2` `:Effect9` `:Effect14`
  - Enables: new sounds from data, with no new code.
- Two effects take noise from the video beam position. `:Effect12` `:Effect16`
  - Enables: noise without a random number generator.
  - Costs: the noise depends on when the tick runs.
- A synth note does not stop the channel. It copies its wave over the playing
  copy. `:ReadVoiceRow`
  - Enables: synth notes with no restart and no busy-wait.
- A position gives each voice a start row in one shared list of rows.
  `:ReadPosition`
  - Enables: tracks that overlap or start inside another track.
  - Costs: one pattern length for all voices.

## Composer's view

The composer writes positions, rows and instruments. An instrument is a sample,
or a synth wave with one effect. Each instrument has a pitch table (the format's
`AMF`), a volume table and three arpeggios.

| Aspect   | Answer                                                                             | Source          |
| -------- | ---------------------------------------------------------------------------------- | --------------- |
| Notation | A row: note, instrument, flags and command, argument.                              | `:Row`          |
| Notation | A position: per voice, a start row, an instrument transpose and a note transpose.  | `:Track`        |
| Notation | An instrument: wave or sample, vibrato, portamento, two tables, effect, arpeggios. | `:Instrument`   |
| Notation | A row's flags pick one of the three arpeggios. Each row can pick another one.      | `:Arpeggio`     |
| Notation | The subsong sets the tick rate in Hz.                                              | `:SetTimer`     |
| Cost     | A held note needs `$80` on every row. A row without it starts the release.         | `:AdsrSustain`  |
| Cost     | A slide lasts one row.                                                             | `:RowCommand`   |
| Cost     | A larger vibrato depth gives a smaller vibrato.                                    | `:Vibrato`      |
| Cost     | Command 4 starts the vibrato. Its argument has no effect.                          | `:CmdVibrato`   |
| Cost     | Effect 10 takes its pitch step from the range's `start` field.                     | `:Effect10`     |
| Cost     | After a synth note, a sample starts only at the copy's next loop.                  | `:ReadVoiceRow` |

## What is unique

- While rows hold the note, the volume table waits at its sustain point. A
  sustain delay only slows it down. `:AdsrSustain`
- A volume table without a loop that ends on 0 silences the voice. It stays
  silent until the next note. `:AdsrStep`
- Portamento glides from the previous note and turns itself off at the target.
  `:Portamento`
- Effect 15 morphs to the second wave, then back to the first, forever.
  `:Effect15`
- Effect 2 builds a pulse from the wave. The second wave's bytes set the width,
  one per run. `:Effect2`

## Open questions

- What does `AMF` stand for?
- Is command 4's unused argument a bug of version 2.18 only?
