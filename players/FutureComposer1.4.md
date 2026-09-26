---
player: FutureComposer1.4
control: { sequencer: commands, instrument: commands }
themes: [synthesis]
ideas: [pitch-list, volume-list, sample-pack, instrument-transpose]
streams: { voice: 4 }
---

# Future Composer 1.4

Each instrument runs two command lists: volume, and pitch with waveform.

## Key ideas

- The pitch list also sets waveforms and slides pitch.
  `data/annot/FutureComposer1.4.yaml:testnewsound` `:testpitchbend`
- A pitch step with bit 7 set is a fixed note, not an offset. `:lockednote`
- The module carries up to 80 waveforms. `:InitWaveforms`
- `E9` picks one sample out of a pack of samples. `:testE9`
- Positions can transpose instrument numbers. `:AddInstrTranspose`

## Streams

| Stream      | Scope | Role       | Carries                                         | Control               | Rate          |
| ----------- | ----- | ---------- | ----------------------------------------------- | --------------------- | ------------- |
| Positions   | voice | sequencer  | pattern, transpose, instrument transpose; speed | loop                  | pattern end   |
| Pattern     | voice | sequencer  | note, instrument, portamento                    | end                   | row           |
| Pitch list  | voice | instrument | note offset, waveform, slide; own table         | loop, jump, wait, end | tick          |
| Volume list | voice | instrument | volume, slide; instrument                       | loop, wait, end       | every N ticks |

## Sequencer

| Aspect   | Value     | Label      |
| -------- | --------- | ---------- |
| Time     | rows      | `:PLAY`    |
| Unit     | row       | `:PLAY`    |
| Note end | next note | `:samepat` |
| Routing  | fixed     | `:PLAY`    |
| Reuse    | patterns  | `:patend`  |
| Tempo    | speed     | `:notend`  |

## Generators

| Generator  | Scope | States          | Writes         | Rate          | Set by                  | Note-on |
| ---------- | ----- | --------------- | -------------- | ------------- | ----------------------- | ------- |
| Vibrato    | voice | delay, up, down | period         | tick          | instrument, Pitch list  | restart |
| Portamento | voice | on, off         | period         | every N ticks | Pattern                 | restart |
| Bends      | voice | bend, done      | period, volume | every N ticks | Pitch list, Volume list | keep    |

## Channel outputs

| Output | Writers, in tick order                                                          |
| ------ | ------------------------------------------------------------------------------- |
| Volume | Volume list (set), Bends (add)                                                  |
| Period | Pattern (note), Pitch list (note), Vibrato (add), Portamento (add), Bends (add) |
| Sample | Pitch list (set)                                                                |
| DMA    | Pattern (off), Pitch list (off), Pattern (on), Pitch list (on)                  |

## Interactions

| From       | To          | Event                                                     |
| ---------- | ----------- | --------------------------------------------------------- |
| Pitch list | Volume list | `E2` and `E9` restart it; `E4` does not `:RestartVolList` |

- Each voice steps its own position at its own pattern end. `:patend`
- Portamento and bends step every second tick. `:DoSlide` `:do_VOLbend`
- Portamento speed comes from the next row's second byte. `:SlideSpeed`
- 1.3's built-in waves form series, one sample apart (inference: sweeps).
  `ext/uade/amigasrc/players/defect/fc13/FutureComposer_1.3.s:WAVEFORMS`

## State

| Scope      | Fields                                                              |
| ---------- | ------------------------------------------------------------------- |
| Voice      | stream positions, waits, transposes, note, vibrato position, slides |
| Instrument | volume speed, pitch list, vibrato settings                          |
| Global     | speed, tick counter                                                 |

## Open questions

- None left.
