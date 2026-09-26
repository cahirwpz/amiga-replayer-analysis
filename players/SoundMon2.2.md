---
player: SoundMon2.2
control: { sequencer: commands, instrument: tables }
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

| Stream    | Scope | Role       | Carries                                  | Control | Rate          |
| --------- | ----- | ---------- | ---------------------------------------- | ------- | ------------- |
| Positions | song  | sequencer  | pattern, transpose, instrument transpose | loop    | pattern end   |
| Pattern   | voice | sequencer  | note, instrument, option                 | jump    | row           |
| ADSR      | voice | instrument | volume scale; table                      | mode    | every N ticks |
| LFO       | voice | instrument | period offset; table                     | mode    | every N ticks |
| EG        | voice | instrument | negated sample count; table              | mode    | every N ticks |
| MOD       | voice | instrument | one wave sample; table                   | mode    | every N ticks |

## Sequencer

| Aspect   | Value     | Label               |
| -------- | --------- | ------------------- |
| Time     | rows      | `:PlayTick`         |
| Unit     | row       | `:PlayRow`          |
| Note end | next note | `:StartNoteLoop`    |
| Routing  | fixed     | `:ReadRowVoiceLoop` |
| Reuse    | patterns  | `:ReadRowVoiceLoop` |
| Tempo    | speed     | `:OptSpeed`         |

## Generators

| Generator | Scope | States  | Writes    | Rate          | Set by              | Note-on |
| --------- | ----- | ------- | --------- | ------------- | ------------------- | ------- |
| Slide     | voice | on, off | period    | tick          | Pattern             | restart |
| Vibrato   | song  | 8 steps | period    | tick          | Pattern             | keep    |
| Arpeggio  | song  | 4 steps | period    | tick          | Pattern             | keep    |
| Effect    | voice | on, off | wave data | every N ticks | instrument, Pattern | restart |

## Channel outputs

| Output    | Writers, in tick order                                                 |
| --------- | ---------------------------------------------------------------------- |
| Period    | Slide (add), Vibrato (add), Arpeggio (note), LFO (add), Pattern (note) |
| Volume    | ADSR (scale), Pattern (set)                                            |
| Wave data | EG (edit), Effect (edit), MOD (edit), Pattern (edit)                   |
| Sample    | Pattern (set)                                                          |
| DMA       | Pattern (off), Pattern (on)                                            |

## Interactions

| From    | To          | Event                                                            |
| ------- | ----------- | ---------------------------------------------------------------- |
| Pattern | ADSR        | Options 13–15 change the note without a restart `:SetNotePeriod` |
| EG      | other voice | Voices on one wave change it together `:EgWalker`                |

- One arpeggio step and one vibrato position serve all voices. `:Arpeggio`
  `:VibratoTable`
- The next note restores the original wave. `:RestoreWaveLoop`

## State

| Scope      | Fields                                                           |
| ---------- | ---------------------------------------------------------------- |
| Voice      | period, note, volume, walker positions, delays, modes, effect    |
| Instrument | synth flag, wave, per walker: table, length, speed, mode; volume |
| Global     | position, row, speed, arpeggio step, vibrato position            |

## Open questions

- None left.
