---
player: FutureComposer1.3
source: defect/fc13
code: uade
control: commands
themes: [synthesis]
ideas: [pitch-list, volume-list, waveform-series, sound-transpose]
related: [FutureComposer1.4, SoundMon2.2]
streams: { song: 1, voice: 3 }
evidence: code
---

# Future Composer 1.3

Each instrument runs two short command lists: one for volume, one for pitch and
waveform.

## Key ideas

- The pitch list also switches waveforms. `FutureComposer_1.3.s:551`
- A pitch step with bit 7 set is a fixed note, not an offset. `:673`
- Built-in waveforms form series that differ by one sample. `:884`
- Sound transpose in the song is added to the instrument number. `:503`

## Streams

| Stream      | Scope | Carries                                    | Control               | Rate          |
| ----------- | ----- | ------------------------------------------ | --------------------- | ------------- |
| Sequence    | song  | pattern, transpose, sound transpose; speed | loop                  | pattern end   |
| Pattern     | voice | note, instrument, portamento on or off     | none                  | row           |
| Pitch list  | voice | note offset, waveform, vibrato; own table  | loop, jump, wait, end | tick          |
| Volume list | voice | volume; instrument                         | loop, wait, end       | every N ticks |

## Generators and interactions

- Vibrato moves up and down after a delay. Depth grows per octave. `:690`
- Portamento adds a fixed step each tick. `:733`
- Portamento speed comes from the next row's info byte. `:490`
- Pitch command `E2` restarts the volume list. `E4` does not. `:581`

## State

| Scope      | Fields                                                                 |
| ---------- | ---------------------------------------------------------------------- |
| Voice      | stream positions, waits, transposes, note, vibrato phase, slide offset |
| Instrument | volume speed, pitch list number, vibrato speed, depth, delay           |
| Global     | speed, tick counter                                                    |

## Open questions

- Waveform series seem built for timbre sweeps (inference).
