---
player: MED
control: { sequencer: commands, instrument: commands }
themes: [synthesis]
ideas:
  [volume-list, wave-list, cross-list-jumps, waveform-as-table, release-jump]
streams: { song: 2, voice: 3 }
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Key ideas

- Two opcode lists per instrument, each at its own speed.
  `data/annot/MED.yaml:SynthTick`
- Each list can set the other's position. `:VolJumpWaveList` `:WaveJumpVolList`
- Waveforms double as volume envelopes and vibrato shapes. `:VolEnvOnce`
  `:VibratoWave`
- Hybrid instruments run a sample through the same lists. `:StartSynthNote`

## Streams

| Stream      | Scope | Role       | Carries                         | Control         | Rate          |
| ----------- | ----- | ---------- | ------------------------------- | --------------- | ------------- |
| Positions   | song  | sequencer  | block number                    | loop            | pattern end   |
| Pattern     | song  | sequencer  | note, instrument, command       | loop, jump, end | row           |
| Volume list | voice | instrument | volume, slide, envelope         | jump, wait, end | every N ticks |
| Wave list   | voice | instrument | waveform, pitch slide, vibrato  | jump, wait, end | every N ticks |
| Arpeggio    | voice | instrument | note offsets from the wave list | loop            | tick          |

## Sequencer

| Aspect   | Value                       | Label                        |
| -------- | --------------------------- | ---------------------------- |
| Time     | rows                        | `:_IntHandler`               |
| Unit     | row                         | `:_IntHandler`               |
| Note end | next note, length, note-off | `:HoldAndFade` `:CmdNoteOff` |
| Routing  | fixed                       | `:plr_loop2`                 |
| Reuse    | patterns, loops             | `:NextPlaySeq` `:CmdLoop`    |
| Tempo    | speed, timer                | `:_SetTempo`                 |

- Length: the instrument's hold time. Each next row with only an instrument
  number adds a row. `:ExtendHold`

## Generators

| Generator    | Scope | States        | Writes         | Rate          | Set by                 | Note-on |
| ------------ | ----- | ------------- | -------------- | ------------- | ---------------------- | ------- |
| Hold         | voice | hold, release | volume         | tick          | instrument, Pattern    | restart |
| List slides  | voice | on, off       | volume, period | every N ticks | Volume list, Wave list | restart |
| List vibrato | voice | on, off       | period         | tick          | Wave list              | restart |

## Channel outputs

| Output | Writers, in tick order                                                                |
| ------ | ------------------------------------------------------------------------------------- |
| Volume | Pattern (set), Hold (add), List slides (add), Volume list (scale)                     |
| Period | Pattern (note), Arpeggio (note), List vibrato (add), List slides (add), Pattern (add) |
| Sample | Pattern (set), Wave list (set)                                                        |
| DMA    | Pattern (on), Pattern (off), Hold (off)                                               |

## Interactions

| From        | To          | Event                                        |
| ----------- | ----------- | -------------------------------------------- |
| Volume list | Wave list   | Sets its position `:VolJumpWaveList`         |
| Wave list   | Volume list | Sets its position `:WaveJumpVolList`         |
| Hold        | Volume list | Jumps it to the release part `:SynthRelease` |
| Pattern     | Wave list   | Command E sets its start `:CmdWaveListPos`   |

- A synth note after a synth note keeps the channel running. `:nostpdma`
- Pattern commands add effects like `ProTracker`'s. `:ChannelFX`
- Newer modules nest positions in two levels. `:NextSection`

## State

| Scope      | Fields                                                        |
| ---------- | ------------------------------------------------------------- |
| Voice      | list positions, counters, waits; volume, slide, vibrato, hold |
| Instrument | two lists, their speeds, up to 64 waveforms; hold, decay      |
| Global     | position, line, tempo, loop line and count                    |

## Open questions

- Which songs use the jumps between lists?
