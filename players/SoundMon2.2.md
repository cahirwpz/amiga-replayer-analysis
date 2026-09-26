---
player: SoundMon2.2
control: tables
themes: [synthesis]
ideas:
  [
    waveform-as-table,
    table-walkers,
    in-place-waveform-effects,
    partial-wave-inversion,
  ]
streams: { song: 1, voice: 5 }
---

# SoundMon 2.2

A synth voice runs four table walkers over one pool of 64-byte tables.

## Key ideas

- Waves and control tables share the pool.
  `data/annot/SoundMon2.2.yaml:StartSynthNote` `:AdsrWalker`
- The EG walker negates the wave's first N samples. `:EgWalker`
- The MOD walker writes one table value into the wave. `:ModWalker`
- Six effects rewrite the wave in place.
  [Details](../details/SoundMon2.2-effects.md).

## Streams

| Stream    | Scope | Carries                                  | Control    | Rate          |
| --------- | ----- | ---------------------------------------- | ---------- | ------------- |
| Positions | song  | pattern, transpose, instrument transpose | loop, jump | pattern end   |
| Pattern   | voice | note, instrument, option                 | none       | row           |
| ADSR      | voice | volume scale; table                      | mode       | every N ticks |
| LFO       | voice | period offset; table                     | mode       | every N ticks |
| EG        | voice | negated sample count; table              | mode       | every N ticks |
| MOD       | voice | one wave sample; table                   | mode       | every N ticks |

## Generators and interactions

- Arpeggio cycles four ticks: two offsets, base note twice. `:Arpeggio`
- Vibrato uses one 8-step table and position for all voices. `:VibratoTable`
- The next note restores the original wave. `:RestoreWaveLoop`
- Options 13–15 change the note without restarting walkers. `:SetNotePeriod`

## State

| Scope      | Fields                                                           |
| ---------- | ---------------------------------------------------------------- |
| Voice      | period, note, volume, walker positions, delays, modes, effect    |
| Instrument | synth flag, wave, per walker: table, length, speed, mode; volume |
| Global     | position, row, speed, arpeggio step, vibrato position            |

## Open questions

- Two voices on one wave both change it (guess).
