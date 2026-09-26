---
player: MED
control: commands
themes: [synthesis]
ideas:
  [volume-list, wave-list, cross-list-jumps, waveform-as-table, release-jump]
streams: { song: 1, voice: 4 }
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Key ideas

- Two opcode lists per instrument, each at its own speed.
  `data/annot/MED.yaml:SynthTick`
- Each list can set the other's position. `:VolJumpWaveList` `:WaveJumpVolList`
- When the hold time ends, the volume list jumps to its release part.
  `:SynthRelease`
- Waveforms double as volume envelopes and vibrato shapes. `:VolEnvOnce`
  `:VibratoWave`
- Hybrid instruments run a sample through the same lists. `:StartSynthNote`
- Pattern command E sets where the wave list starts. `:CmdWaveListPos`

## Streams

| Stream      | Scope | Carries                         | Control         | Rate          |
| ----------- | ----- | ------------------------------- | --------------- | ------------- |
| Positions   | song  | pattern number                  | jump            | pattern end   |
| Pattern     | voice | note, instrument, command       | none            | row           |
| Volume list | voice | volume, slide, envelope         | jump, wait, end | every N ticks |
| Wave list   | voice | waveform, pitch slide, vibrato  | jump, wait, end | every N ticks |
| Arpeggio    | voice | note offsets from the wave list | loop            | tick          |

## Generators and interactions

- A synth note after a synth note keeps the channel running. `:nostpdma`
- Newer modules nest positions in two levels. `:NextSection`

## State

| Scope      | Fields                                                        |
| ---------- | ------------------------------------------------------------- |
| Voice      | list positions, counters, waits; volume, slide, vibrato, hold |
| Instrument | two lists, their speeds, up to 64 waveforms; hold, decay      |
| Global     | position, line, tempo                                         |

## Open questions

- Which songs use the jumps between lists?
