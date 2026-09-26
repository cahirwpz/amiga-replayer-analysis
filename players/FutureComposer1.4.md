---
player: FutureComposer1.4
source: defect/fc14
code: uade
control: commands
themes: [synthesis]
ideas: [pitch-list, volume-list, sample-pack, instrument-transpose]
related: [FutureComposer1.3]
streams: { song: 1, voice: 3 }
evidence: code
---

# Future Composer 1.4

Each instrument runs two command lists: volume, and pitch with waveform.

## Key ideas

- The pitch list also sets waveforms and bends. `FC1.4.s:568` `:648`
- A pitch step with bit 7 set is a fixed note, not an offset. `:726`
- The module carries up to 80 waveforms. `:203`
- `E9` picks one sample out of a sample pack. `:606`
- Positions can transpose instrument numbers. `:519`

## Streams

| Stream      | Scope | Carries                                         | Control               | Rate          |
| ----------- | ----- | ----------------------------------------------- | --------------------- | ------------- |
| Positions   | song  | pattern, transpose, instrument transpose; speed | loop                  | pattern end   |
| Pattern     | voice | note, instrument, portamento                    | end                   | row           |
| Pitch list  | voice | note offset, waveform, bend; own table          | loop, jump, wait, end | tick          |
| Volume list | voice | volume, bend; instrument                        | loop, wait, end       | every N ticks |

## Generators and interactions

- Vibrato starts after a delay. Depth grows per octave. `:744`
- Portamento, pitch bend and volume bend step every second tick. `:789` `:711`
- Portamento speed comes from the next row's info byte. `:508`
- `E2` and `E9` restart the volume list; `E4` does not. `:585`

## State

| Scope      | Fields                                                          |
| ---------- | --------------------------------------------------------------- |
| Voice      | stream positions, waits, transposes, note, vibrato phase, bends |
| Instrument | volume speed, pitch list, vibrato settings                      |
| Global     | speed, tick counter                                             |

## Open questions

- Version 1.3 has built-in waveform series, likely for timbre sweeps
  (inference).
