---
player: MugicianII
control: tables
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
  [All 15 effects](../details/MugicianII-effects.md).
- Row length alternates between two speeds (swing). `:SwingSpeeds`
- Voices 4–7 are mixed into one channel. They play samples only. `:MixVoices`
  `:StartSample`

## Streams

| Stream      | Scope      | Carries                             | Control    | Rate          |
| ----------- | ---------- | ----------------------------------- | ---------- | ------------- |
| Positions   | song       | track and transpose per voice       | loop       | pattern end   |
| Track       | voice      | note, instrument, command           | none       | row           |
| Volume      | voice      | volume, read from a waveform        | mode       | every N ticks |
| Arpeggio    | voice      | note offset, instrument table       | loop       | tick          |
| Vibrato     | voice      | period offset, read from a waveform | wait, loop | tick          |
| Wave effect | instrument | new waveform                        | loop       | every N ticks |

## Generators and interactions

- Voices on one instrument share its effect. It still steps once per tick.
  `:EffectOncePerTick`
- Note-on copies a source waveform over the played one. `:CopyWaveA`
- Command 9 toggles the audio filter every tick. `:VoiceTick`

## State

| Scope      | Fields                                                                               |
| ---------- | ------------------------------------------------------------------------------------ |
| Voice      | stream positions, delays, period, slide target, volume                               |
| Instrument | wave, length, table indices, effect number, its waves, speeds; effect step (runtime) |
| Global     | speed pair, row, position, pattern length                                            |

## Open questions

- None left.
