---
player: MugicianII
source: wanted_team/MugicianII
code: uade
control: tables
themes: [synthesis, mixing]
ideas: [waveform-as-table, in-place-waveform-effects, swing]
related: [Mugician]
streams: { song: 1, voice: 4, instrument: 1 }
evidence: code
---

# Mugician II

One data type, the 128-byte waveform, serves as sound, volume envelope and
vibrato table.

## Key ideas

- Envelopes and vibrato read other waveforms as tables.
  `src/Mugician II_v8.asm:2360`
- Effects rewrite the waveform in place, e.g. crossfade two waves, smooth, shift
  by one sample. `:2506` [All 15 effects](../details/MugicianII-effects.md).
- Row length alternates between two speeds (swing). `:1849`
- Voices 4–7 are mixed into channel 0. `:4146`

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
  `:2264`
- Note-on copies a source waveform over the working one. `:2128`
- Command 9 toggles the audio filter every tick. `:2243`

## State

| Scope      | Fields                                                                               |
| ---------- | ------------------------------------------------------------------------------------ |
| Voice      | stream positions, delays, period, slide target, volume                               |
| Instrument | wave, length, table indices, effect number, its waves, speeds; effect step (runtime) |
| Global     | speed pair, row, position, pattern length                                            |

## Open questions

- Mixed voices seem to play samples only.
