---
player: SonixMusicDriver
template: 2
ideas:
  [
    event-scores,
    instrument-drivers,
    filter-bank,
    subtractive-synth,
    tempo-independent-rates,
  ]
---

# Sonix Music Driver

A synth instrument works like an analog synth: wave, low-pass filter, envelope,
LFO.

## Context

| Fact      | Value                                                                 |
| --------- | --------------------------------------------------------------------- |
| Player    | `SonixMusicDriver`                                                    |
| Author    | Mark Riley                                                            |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/SonixMusicDriver` |
| Spec      | [specs/sonix_music_driver.py](../specs/sonix_music_driver.py)         |

## Key ideas

- Scores hold events: note with velocity, wait, instrument, volume, tempo, bend.
  There are no rows. `:ReadEvent`
  - Enables: timing like a MIDI sequencer.
  - Costs: no patterns, so every note is stored.
- Each instrument type is a driver with two entry points: a tick, then a
  register write. `:TickInstruments`
  - Enables: synths, `.ss` samples and 8SVX samples in one score.
- Loading a synth builds 64 low-pass copies of its wave. `:SetFilter`
  `:OneFilter`
  - Enables: filter sweeps for the cost of one copy per tick.
  - Costs: 8 kB per synth instrument.
- Envelope and LFO pick one copy per tick: a filter sweep. `:SelectFilter`
- High notes play fewer bytes of the wave. The period stays between 214 and 428.
  `:OctaveShift`
  - Enables: every note plays at 8 to 16.5 kHz.
  - Costs: the top octave plays a 4-byte wave.
- Two wave modes: blend with a moving copy, or stretch one half. `:BlendCopy`
  `:StretchHalves`

## Composer's view

The composer writes four tracks of events and picks instruments by number. A
synth instrument sets its wave, filter, envelope, LFO and wave mode.

| Aspect   | Answer                                                                 | Source             |
| -------- | ---------------------------------------------------------------------- | ------------------ |
| Notation | An event word: a note and velocity, a wait, or a setting.              | `:ReadEvent`       |
| Notation | A synth: wave, LFO table, envelope, amounts for volume, pitch, filter. | `:SynthInstrument` |
| Cost     | A note ends with the same note at velocity 0.                          | `:NoteEvent`       |
| Cost     | A note on a held synth voice keeps its envelope: legato.               | `:Legato`          |
| Cost     | Every synth note glides from the last pitch, over the portamento time. | `:Portamento`      |
| Cost     | Synth notes outside 36 to 107 are dropped.                             | `:SynthTick`       |
| Cost     | Without envelope-to-volume, a release silences the note at once.       | `:OctaveShift`     |

## What is unique

- Rates and times scale with the tick's length. A tempo change keeps envelopes,
  LFOs and glides at their speed. `:SetTempo`
- A synth voice fills a new wave buffer every tick. Paula takes it at the loop's
  end, so the timbre changes with no restart. `:SynthWrite`
- After the score loops, the last tempo event still holds. `:RestartScore`
- Sample notes set period 2 with DMA off, to end the word fast (guess).
  `:SampledTick`
