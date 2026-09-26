---
player: FutureComposer1.4
control: commands
themes: [synthesis]
ideas: [pitch-list, volume-list, sample-pack, instrument-transpose]
streams: { song: 1, voice: 3 }
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

| Stream      | Scope | Carries                                         | Control               | Rate          |
| ----------- | ----- | ----------------------------------------------- | --------------------- | ------------- |
| Positions   | song  | pattern, transpose, instrument transpose; speed | loop                  | pattern end   |
| Pattern     | voice | note, instrument, portamento                    | end                   | row           |
| Pitch list  | voice | note offset, waveform, slide; own table         | loop, jump, wait, end | tick          |
| Volume list | voice | volume, slide; instrument                       | loop, wait, end       | every N ticks |

## Generators and interactions

- Vibrato starts after a delay. Depth grows per octave. `:vibrator`
- Portamento, pitch slides and volume slides step every second tick. `:DoSlide`
  `:do_VOLbend`
- Portamento speed comes from the next row's second byte. `:SlideSpeed`
- `E2` and `E9` restart the volume list; `E4` does not. `:RestartVolList`

## State

| Scope      | Fields                                                              |
| ---------- | ------------------------------------------------------------------- |
| Voice      | stream positions, waits, transposes, note, vibrato position, slides |
| Instrument | volume speed, pitch list, vibrato settings                          |
| Global     | speed, tick counter                                                 |

## Open questions

- Version 1.3 has built-in waveform series, likely for timbre sweeps
  (inference).
