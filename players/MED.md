---
player: MED
template: 2
ideas:
  [volume-list, wave-list, cross-list-jumps, waveform-as-table, release-jump]
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Context

| Fact      | Value                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ |
| Player    | `MED`                                                                                            |
| Author    | Teijo Kinnunen                                                                                   |
| Code read | original: `ext/uade/amigasrc/players/uade/med`                                                   |
| Spec      | [specs/med.py](../specs/med.py)                                                                  |
| Links     | [archive.org](https://archive.org/details/OctaMED_Professional_v3.00_1992_RBF_Software_CU_Amiga) |

## Key ideas

- Two command lists per instrument, each at its own speed. `:SynthTick`
  - Enables: a slow volume shape beside fast wave changes.
  - Costs: 256 bytes of lists per synth sound (estimate).
- Each list can set the other's position. `:VolJumpWaveList` `:WaveJumpVolList`
  - Enables: a volume phase can start a new wave phrase.
  - Costs: a jump has no condition.
- Waveforms double as volume envelopes and vibrato shapes. `:VolEnvOnce`
  `:VibratoWave`
  - Enables: drawn envelope and vibrato shapes, with no new data type.
  - Costs: an envelope uses one of the 64 waveform slots.
- A synth sound can play a sample through the same lists. MED calls it a
  `hybrid`. `:StartSynthNote`
  - Enables: list envelopes and pitch on a sampled sound.
  - Costs: the sample takes the first of the 64 waveform slots.
- When the gate time runs out, the volume list jumps to its release part.
  `:HoldAndFade` `:SynthRelease`
  - Enables: the list itself shapes the release.
  - Costs: a note-off command is a hard stop. It skips the release part.

## Composer's view

The composer writes notes into patterns, one track per voice. MED calls a
pattern a `block` and a row a `line`. A section names a list of positions.

| Aspect   | Answer                                                                      | Source                         |
| -------- | --------------------------------------------------------------------------- | ------------------------------ |
| Notation | A tracker grid: one column per track.                                       | (manual)                       |
| Notation | Synth sounds: a volume list and a wave list.                                | `:SynthSound`                  |
| Notation | Gate time: an instrument setting, `hold`, in ticks.                         | `:Instrument`                  |
| Notation | `CMD_HOLD_DECAY` sets gate time and decay for later notes.                  | `:CmdHoldDecay`                |
| Notation | `CMD_WAVE_LIST_POS` sets where the next synth note starts in its wave list. | `:CmdWaveListPos`              |
| Notation | `TRIPLET_FIRST` plays the row's note a third into the row.                  | `:MiscTick`                    |
| Notation | `TRIPLET_SECOND` plays the row's note two thirds into the row.              | `:MiscTick`                    |
| Cost     | A synth arpeggio is one wave-list opcode.                                   | `:ArpeggioStart`               |
| Cost     | A pattern arpeggio needs its command on every row.                          | `:ArpeggioTick`                |
| Cost     | A drawn envelope is one waveform and one opcode.                            | `:VolEnvOnce`                  |
| Cost     | The gate time starts the release. It needs no pattern data.                 | `:SynthRelease`                |
| Cost     | A sample's release lowers the volume by a set step each tick.               | `:SynthRelease` `:HoldAndFade` |
| Cost     | Synth vibrato depth is in periods. Low notes get a smaller pitch change.    | `:SynthVibrato`                |

## What is unique

- A list's wait counts list visits, not ticks. `:VolWait`
- A jump cancels the other list's wait. That list keeps its clock.
  `:VolJumpWaveList`
- The next row extends gate time with an instrument number and no note, or with
  portamento. `:ExtendHold`
- A volume-list value overwrites the envelope, which overwrites the volume
  slide. `:SynthTick`
- A new waveform starts at the channel's next loop, with no restart.
  `:ReadWaveList`
- Synth arpeggio replaces the period. Pattern portamento then has no effect.
  `:SynthArpeggio`
- A synth note after a synth note is legato. `:KeepSynthChannel`

## Open questions

- Which songs use the jumps between lists?
