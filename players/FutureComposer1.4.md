---
player: FutureComposer1.4
template: 2
ideas: [pitch-list, volume-list, sample-pack, instrument-transpose]
---

# Future Composer 1.4

Each instrument runs two command lists: volume, and pitch with waveform.

## Context

| Fact      | Value                                                         |
| --------- | ------------------------------------------------------------- |
| Player    | `FutureComposer1.4`                                           |
| Family    | Future Composer                                               |
| Grew from | `FutureComposer1.3`                                           |
| Code read | original: `ext/uade/amigasrc/players/defect/fc14`             |
| Spec      | [specs/future_composer_14.py](../specs/future_composer_14.py) |

## Key ideas

- The pitch list sets waveforms, transposes, pitch slides and vibrato. It steps
  every tick. `:PitchListTick` `:ReadPitchList`
  - Enables: synth sounds and arpeggios as data, from 80 short waveforms.
  - Costs: at most one command and one transpose per tick.
- A pattern note only turns DMA off. The pitch list's wave command turns it on
  again. `:StartInstrument` `:SetWave` `:Play`
  - Enables: the instrument picks the wave and the moment its sound starts.
  - Costs: a pitch list that starts without a wave command leaves the note
    silent.
- The volume list steps every N ticks, with waits, loops and volume slides.
  `:VolumeListTick` `:ReadVolume`
  - Enables: envelopes of any shape, at their own speed.
  - Costs: at most 59 bytes per instrument.
- A pitch list byte with bit 7 set is a fixed note. `:LockedNote`
  - Enables: drums and effects that ignore the played note.
  - Costs: a fixed note ignores all transposes.
- `PACK` picks one sample out of a pack of up to 20. `:SampleFromPack`
  - Enables: many drum samples in one of the 10 sample slots.
  - Costs: the pack needs its own header.
- Positions transpose notes and instrument numbers per voice. `:NextPosition`
  `:AddInstrTranspose`
  - Enables: one pattern plays with other instruments.
  - Costs: a position takes 13 bytes.

## Composer's view

The composer writes positions, patterns, instruments and pitch lists. The source
calls a pitch list `FREQseq`. An instrument names its pitch list and holds its
volume list.

| Aspect   | Answer                                                              | Source             |
| -------- | ------------------------------------------------------------------- | ------------------ |
| Notation | A row: a note, and a byte with the instrument and portamento bits.  | `:ReadNote`        |
| Notation | A position: pattern, transpose, instrument transpose per voice.     | `:Position`        |
| Notation | An instrument: volume speed, pitch list, vibrato, then volume list. | `:StartInstrument` |
| Cost     | An arpeggio is a pitch list loop of transposes.                     | `:ReadTranspose`   |
| Cost     | Portamento takes its speed from the next row's instrument byte.     | `:SlideSpeed`      |
| Cost     | A pattern shorter than 32 rows ends with the note `PATTERN_END`.    | `:NewRow`          |

## What is unique

- The loop is written one tick after the wave starts, with no busy-wait.
  `:WriteLoops`
- Vibrato depth doubles for each octave down, so its width in semitones stays
  about the same. `:VibratoTick`
- Portamento, pitch slides and volume slides step every second tick. `:DoSlide`
  `:PitchBend` `:VolumeBend`
- Each voice steps to its next position at its own pattern end. `:NextPosition`
- Every fourth pattern end, counted over all voices, reads the speed. Position
  1's speed is never read. `:ReadSpeed`
- A volume slide past 127 drops the volume to 0. `:VolumeBend`

## Open questions

- Only the tick's own work separates DMA off and on. Does a low note then miss
  its restart (guess)? `:Play`
