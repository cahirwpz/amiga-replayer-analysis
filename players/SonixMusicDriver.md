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

- Scores hold events, not rows. `:ReadEvent`
  - Enables: timing like a MIDI sequencer.
  - Costs: no patterns. Every note is stored.
- Each instrument type is a driver with two entry points. One runs each tick,
  the other writes the registers. `:TickInstruments`
  - Enables: synths, `.ss` samples and 8SVX samples in one score.
- Loading a synth builds 64 low-pass copies of its wave. `:SetFilter`
  `:OneFilter`
  - Enables: filter sweeps for the cost of one copy per tick.
  - Costs: 8 kB per synth instrument.
- Envelope and LFO pick one copy per tick. That sweeps the filter.
  `:SelectFilter`
- High notes play fewer bytes of the wave. The period stays between 214 and 428.
  `:OctaveShift`
  - Enables: every note plays at 8 to 16.5 kHz.
  - Costs: the top octave plays a 4-byte wave.
- A synth blends its wave with a moving copy, or stretches one half.
  `:BlendCopy` `:StretchHalves`

## Composer's view

The composer writes four tracks of events and picks instruments by number. A
synth instrument sets its wave, filter, envelope, LFO and wave mode.

| Aspect   | Answer                                                                     | Source             |
| -------- | -------------------------------------------------------------------------- | ------------------ |
| Notation | An event word: a note and velocity, a wait, or a setting.                  | `:ReadEvent`       |
| Notation | A synth: wave, LFO table, envelope, amounts for volume, pitch, filter.     | `:SynthInstrument` |
| Cost     | A note ends with the same note at velocity 0.                              | `:NoteEvent`       |
| Cost     | A note on a held synth voice is legato. It keeps its envelope.             | `:Legato`          |
| Cost     | A synth note after a release attacks from the current level.               | `:SynthStart`      |
| Cost     | A synth note does not stop the channel. Its wave enters at the loop's end. | `:SynthWrite`      |
| Cost     | A multi-octave sample stores one copy per octave, each twice as long.      | `:SampledTick`     |
| Cost     | Every synth note glides from the last pitch, over the portamento time.     | `:Portamento`      |
| Cost     | Synth notes outside 36 to 107 are dropped.                                 | `:SynthTick`       |
| Cost     | Without envelope-to-volume, a release silences the note at once.           | `:OctaveShift`     |

## What is unique

- Rates and times scale with the tick's length. A tempo change keeps envelopes,
  LFOs and glides at their speed. `:SetTempo`
- A synth voice fills a new wave buffer every tick. Paula takes it at the loop's
  end, with no restart. `:SynthWrite`
- After the score loops, the last tempo event still holds. `:RestartScore`
- Sample notes set period 2 with DMA off. That may end the current sample word
  fast (guess). `:SampledTick`
