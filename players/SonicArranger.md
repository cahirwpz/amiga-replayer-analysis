---
player: SonicArranger
control: tables
themes: [synthesis]
ideas:
  [
    in-place-waveform-effects,
    waveform-as-table,
    per-voice-wave-copy,
    sustain-rows,
    beam-noise,
  ]
streams: { song: 1, voice: 5 }
---

# Sonic Arranger

Seventeen wave effects rewrite each voice's own copy of its wave.

## Key ideas

- Each voice plays a copy; effects never touch the instrument.
  `data/annot/SonicArranger.yaml:StartSynthWave`
- Effects morph, smooth, negate or add noise. `:EffectTable`
  [All 17 effects](../details/SonicArranger-effects.md).
- Several effects read a second wave as a table or target. `:Effect2`
- Noise comes from the video beam position. `:Effect12`
- ADSR holds at its sustain point on rows marked `$80`. `:AdsrSustain`
- A pattern entry picks one of three arpeggio tables. `:Arpeggio`

## Streams

| Stream      | Scope | Carries                             | Control    | Rate          |
| ----------- | ----- | ----------------------------------- | ---------- | ------------- |
| Positions   | song  | pattern, transposes per voice       | loop       | pattern end   |
| Pattern     | voice | note, instrument, arpeggio, command | none       | row           |
| ADSR        | voice | volume; table                       | mode, wait | every N ticks |
| Pitch table | voice | pitch offset; table                 | mode       | every N ticks |
| Arpeggio    | voice | note offset; instrument             | loop       | tick          |
| Wave effect | voice | changes to the wave copy            | loop       | every N ticks |

## Generators and interactions

- Vibrato starts after a delay. `:Vibrato`
- An ADSR table that ends on 0 silences the voice. `:AdsrStep`

## State

| Scope      | Fields                                                            |
| ---------- | ----------------------------------------------------------------- |
| Voice      | wave copy, table positions, delays, effect position, pitch offset |
| Instrument | wave, volume, vibrato, two tables, sustain, effect, 3 arpeggios   |
| Global     | position, row, speed                                              |

## Open questions

- What does the program's name for the pitch table, `AMF`, stand for?
