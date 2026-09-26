---
player: MugicianII
control: { sequencer: commands, instrument: tables }
themes: [synthesis, mixing]
ideas: [waveform-as-table, in-place-waveform-effects, swing]
streams: { song: 1, voice: 4, instrument: 1 }
---

# Mugician II

The 128-byte waveform serves as played wave, volume envelope and vibrato table.

## Key ideas

- Envelopes and vibrato read other waveforms as tables.
  `data/annot/MugicianII.yaml:VolumeFromWave`
- Effects rewrite the waveform in place, e.g. crossfade two waves, smooth, shift
  by one sample. `:EffectTable`
  [All 15 effects](../../../details/MugicianII-effects.md).
- Row length alternates between two speeds (swing). `:SwingSpeeds`
- Voices 4–7 are mixed into one channel. They play samples only. `:MixVoices`
  `:StartSample`

## Streams

| Stream      | Scope      | Role       | Carries                             | Control    | Rate          |
| ----------- | ---------- | ---------- | ----------------------------------- | ---------- | ------------- |
| Positions   | song       | sequencer  | track and transpose per voice       | loop       | pattern end   |
| Track       | voice      | sequencer  | note, instrument, command           | none       | row           |
| Volume      | voice      | instrument | volume, read from a waveform        | mode       | every N ticks |
| Arpeggio    | voice      | instrument | note offset, instrument table       | loop       | tick          |
| Vibrato     | voice      | instrument | period offset, read from a waveform | wait, loop | tick          |
| Wave effect | instrument | instrument | new waveform                        | loop       | every N ticks |

## Sequencer

| Aspect   | Value     | Label          |
| -------- | --------- | -------------- |
| Time     | rows      | `:SwingSpeeds` |
| Unit     | row       | `:SwingSpeeds` |
| Note end | next note | `:ReadRow`     |
| Routing  | fixed     | `:Play`        |
| Reuse    | patterns  | `:ReadRow`     |
| Tempo    | speed     | `:CmdSpeed`    |

## Generators

| Generator  | Scope | States      | Writes    | Rate | Set by | Note-on |
| ---------- | ----- | ----------- | --------- | ---- | ------ | ------- |
| Portamento | voice | glide, done | period    | tick | Track  | restart |
| Mixer      | song  | mix         | wave data | tick | Track  | keep    |

## Channel outputs

| Output    | Writers, in tick order                                         |
| --------- | -------------------------------------------------------------- |
| Volume    | Volume (set)                                                   |
| Period    | Track (note), Arpeggio (note), Portamento (add), Vibrato (add) |
| Sample    | Track (set)                                                    |
| Wave data | Track (edit), Wave effect (edit), Mixer (edit)                 |
| DMA       | Track (on)                                                     |

## Interactions

| From        | To          | Event                                                                          |
| ----------- | ----------- | ------------------------------------------------------------------------------ |
| Track       | Wave effect | Note-on copies a source wave over the played one `:CopyWaveA`                  |
| Wave effect | other voice | Voices on one instrument share it; it steps once per tick `:EffectOncePerTick` |

- Command 9 toggles the audio filter every tick. `:VoiceTick`

## State

| Scope      | Fields                                                                               |
| ---------- | ------------------------------------------------------------------------------------ |
| Voice      | stream positions, delays, period, slide target, volume                               |
| Instrument | wave, length, table indices, effect number, its waves, speeds; effect step (runtime) |
| Global     | speed pair, row, position, pattern length                                            |

## Open questions

- None left.
