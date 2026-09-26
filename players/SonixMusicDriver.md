---
player: SonixMusicDriver
control: commands
themes: [synthesis]
ideas:
  [
    event-scores,
    instrument-drivers,
    filter-bank,
    subtractive-synth,
    tempo-independent-rates,
  ]
streams: { voice: 1 }
---

# Sonix Music Driver

A synth instrument works like an analog synth: wave, low-pass filter, envelope,
LFO.

## Key ideas

- Scores hold events: note with velocity, release, wait. No rows.
  `data/annot/SonixMusicDriver.yaml:ReadEvent`
- Each instrument type is a driver with its own tick routine. `:TickInstruments`
- Loading a synth builds 64 low-pass copies of its wave. `:OneFilter`
- Envelope and LFO pick one copy per tick: a filter sweep. `:SelectFilter`
- Two wave modes: blend with a moving copy, or stretch one half. `:BlendCopy`
  `:StretchHalves`
- Rates scale with tick length, so tempo does not change them. `:Envelope`

## Streams

| Stream | Scope | Carries                                         | Control   | Rate |
| ------ | ----- | ----------------------------------------------- | --------- | ---- |
| Track  | voice | note, velocity, instrument, volume, tempo, bend | wait, end | tick |

## Generators and interactions

- Envelope: attack, decay, sustain, release; a level and rate each. `:Envelope`
- LFO: a 256-byte table; drives pitch, volume and filter. `:Lfo`
- High notes skip samples to keep the period in range. `:OctaveShift`
- `TINY` and `SMUS` notes carry a length; they release after 3/4 of it.
  `:PlayTINY`

## State

| Scope      | Fields                                                               |
| ---------- | -------------------------------------------------------------------- |
| Voice      | track position, wait, note state, envelope, LFO phase, two buffers   |
| Instrument | type; synth: wave, 64 filtered copies, LFO table, levels and amounts |
| Global     | tempo, tick length                                                   |

## Open questions

- None left.
