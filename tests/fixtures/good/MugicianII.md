---
player: MugicianII
control: tables
themes: [synthesis, mixing]
ideas:
  [
    waveform-as-table,
    in-place-waveform-effects,
    swing,
  ]
streams: { song: 1, voice: 4, instrument: 1 }
---

# Mugician II

One data type, the 128-byte waveform, serves as sound, volume envelope and
vibrato table.

## Key ideas

- Envelopes and vibrato read other waveforms as tables.
  `src/Mugician II_v8.asm:lbC01039A`
- Effects rewrite the waveform in place, e.g. crossfade two waves, smooth, shift
  by one sample. `:lbL0104E8` [All 15 effects](../../../details/MugicianII-effects.md).
- Row length alternates between two speeds (swing). `:lbC00FC10`
- Voices 4–7 are mixed into channel 0. `:lbC010982`

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
  `:lbC0102B0`
- Note-on copies a source waveform over the working one. `:lbC010146`
- Command 9 toggles the audio filter every tick. `:lbC01029E`

## State

| Scope      | Fields                                                                               |
| ---------- | ------------------------------------------------------------------------------------ |
| Voice      | stream positions, delays, period, slide target, volume                               |
| Instrument | wave, length, table indices, effect number, its waves, speeds; effect step (runtime) |
| Global     | speed pair, row, position, pattern length                                            |

## Open questions

- Mixed voices seem to play samples only.
