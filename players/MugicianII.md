---
player: MugicianII
source: wanted_team/MugicianII
themes: [synthesis, mixing]
ideas: [waveform-as-envelope, in-place-waveform-effects, shuffle-speed]
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
- Per-instrument effects rewrite the waveform in place: morph, filter, rotate,
  moving sign flip. `:2506`
- Row speed alternates between two values, giving a shuffle. `:1849`
- Voices 4–7 are mixed into channel 0 by lookup tables. `:4146`

## Streams

| Stream      | Scope      | Carries                       | Control           | Rate    |
| ----------- | ---------- | ----------------------------- | ----------------- | ------- |
| Positions   | song       | track and transpose per voice | loop              | row end |
| Track       | voice      | note, instrument, command     | none              | speed   |
| Volume      | voice      | volume from a waveform        | loop or stop      | N ticks |
| Arpeggio    | voice      | note offset                   | loop of 32        | tick    |
| Vibrato     | voice      | period offset from a waveform | delay, loop point | tick    |
| Wave effect | instrument | new waveform                  | cyclic            | N ticks |

## State

| Scope      | Fields                                                                              |
| ---------- | ----------------------------------------------------------------------------------- |
| Voice      | stream positions, delay, period, slide target, volume                               |
| Instrument | wave, length, three table indices, effect type, two source waves, speeds, loop flag |
| Global     | speed pair, row, position, pattern length                                           |

## Open questions

- Mixed voices seem to play samples only.
