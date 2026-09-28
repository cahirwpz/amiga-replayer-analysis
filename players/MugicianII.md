---
player: MugicianII
template: 2
ideas: [waveform-as-table, in-place-waveform-effects, swing, voice-mixing]
---

# Mugician II

A 128-byte wave is a sound, a volume curve or a vibrato curve. Effects rewrite
it while it plays.

## Context

| Fact      | Value                                                              |
| --------- | ------------------------------------------------------------------ |
| Player    | `MugicianII`                                                       |
| Author    | Reinier van Vliet                                                  |
| Family    | Digital Mugician                                                   |
| Grew from | `Mugician`                                                         |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/MugicianII`    |
| Spec      | [specs/mugician_ii.py](../specs/mugician_ii.py)                    |
| Links     | [proofofconcept.nl](https://proofofconcept.nl/portfolio/mugician/) |

## Key ideas

- The volume curve and the vibrato read other waves as tables. `:VolumeFromWave`
  `:VibratoFromWave`
  - Enables: one pool of waves holds sounds and curves.
  - Costs: each curve takes 128 bytes.
- An effect rewrites the played wave, e.g. smooths, rotates or crossfades it.
  `:RunEffect`
  - Enables: a timbre that changes during the note.
  - Costs: voices that play one instrument share its wave and effect.
- Rows alternate between two speeds, one per nibble. `:SwingSpeeds`
  - Enables: swing without extra rows.
- Voices 3 to 6 are mixed into channel 0. `:MixVoices`
  - Enables: seven voices.
  - Costs: they play samples only.
  - Costs: CPU is high. At 16 kHz, the mix takes about half of a 68000.

## Composer's view

The composer writes subsongs, patterns, instruments and waves. A row carries a
note, an instrument, a command byte and an argument.

| Aspect   | Answer                                                                    | Source            |
| -------- | ------------------------------------------------------------------------- | ----------------- |
| Notation | A position: a pattern and a transpose per voice.                          | `:ReadRow`        |
| Notation | A 7-voice song takes two subsongs. Voices 3 to 6 play the second one.     | `:Play`           |
| Notation | An instrument: waves to play, for volume and vibrato, and for its effect. | `:Instrument`     |
| Cost     | A command byte below `FIRST_COMMAND` is a slide target note.              | `:ReadRow`        |
| Cost     | A command comes only with a note. It lasts until the next note.           | `:RowCommands`    |
| Cost     | A loud volume needs wave bytes near -128.                                 | `:VolumeFromWave` |
| Cost     | `LEGATO` changes the wave without a restart.                              | `:StartWave`      |
| Cost     | `ARPEGGIO` changes the instrument's arpeggio, for all voices.             | `:ReadRow`        |

## What is unique

- The volume curve reads its wave upside down: -128 is loudest, +127 silent.
  `:VolumeFromWave`
- An effect runs once per tick per instrument, paced by the first voice that
  plays it. `:EffectOncePerTick`
- A slide overshoots its target for one tick, then stays on it. `:Portamento`
- Channel 0's audio interrupt runs the replay, so the mixer sets the tick.
  `:Interrupt`
- The mixer checks sample ends once per tick. Within a tick, a voice reads past
  its end. `:CheckSampleEnds`

## Open questions

- In the last subsong, voices 3 to 6 have no next subsong. What do they play?
  `:Play`
