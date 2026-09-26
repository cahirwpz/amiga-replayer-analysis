---
player: SonixMusicDriver
control: { sequencer: commands, instrument: none }
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

| Stream | Scope | Role      | Carries                                         | Control   | Rate  |
| ------ | ----- | --------- | ----------------------------------------------- | --------- | ----- |
| Track  | voice | sequencer | note, velocity, instrument, volume, tempo, bend | wait, end | delta |

## Sequencer

| Aspect   | Value    | Label                     |
| -------- | -------- | ------------------------- |
| Time     | deltas   | `:WaitEvent`              |
| Unit     | tick     | `:ReadTracks`             |
| Note end | note-off | `:NoteEvent`              |
| Routing  | fixed    | `:ReadTracks`             |
| Reuse    | none     | `:RestartScore`           |
| Tempo    | timer    | `:TempoEvent` `:SetTempo` |

## Generators

| Generator  | Scope | States                          | Writes                 | Rate | Set by            | Note-on |
| ---------- | ----- | ------------------------------- | ---------------------- | ---- | ----------------- | ------- |
| Envelope   | voice | attack, decay, sustain, release | volume, filter         | tick | instrument, Track | restart |
| LFO        | voice | delay, run                      | period, volume, filter | tick | instrument        | restart |
| Portamento | voice | glide, done                     | period                 | tick | instrument        | restart |
| Wave mode  | voice | blend, stretch                  | wave data              | tick | instrument        | keep    |

## Channel outputs

| Output    | Writers, in tick order                                     |
| --------- | ---------------------------------------------------------- |
| Period    | Track (note), Portamento (add), LFO (scale), Track (scale) |
| Volume    | LFO (add), Envelope (scale), Track (scale)                 |
| Wave data | Envelope (edit), LFO (edit), Wave mode (edit)              |
| Sample    | Track (set)                                                |
| DMA       | Track (on)                                                 |

## Interactions

| From  | To       | Event                                             |
| ----- | -------- | ------------------------------------------------- |
| Track | Envelope | Velocity 0 starts the release `:NoteEvent`        |
| Track | Envelope | A note on a held voice keeps it running `:Legato` |

- Envelope and LFO write a filter index. It picks the copy that the tick writes
  into the voice's buffer. `:SelectFilter`
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
