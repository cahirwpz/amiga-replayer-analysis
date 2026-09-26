---
player: SonicArranger
control: { sequencer: commands, instrument: tables }
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

## Streams

| Stream      | Scope | Role       | Carries                             | Control    | Rate          |
| ----------- | ----- | ---------- | ----------------------------------- | ---------- | ------------- |
| Positions   | song  | sequencer  | pattern, transposes per voice       | loop       | pattern end   |
| Pattern     | voice | sequencer  | note, instrument, arpeggio, command | jump       | row           |
| ADSR        | voice | instrument | volume; table                       | mode, wait | every N ticks |
| Pitch table | voice | instrument | pitch offset; table                 | mode       | every N ticks |
| Arpeggio    | voice | instrument | note offset; instrument             | loop       | tick          |
| Wave effect | voice | instrument | changes to the wave copy            | loop       | every N ticks |

## Sequencer

| Aspect   | Value                        | Label                       |
| -------- | ---------------------------- | --------------------------- |
| Time     | rows                         | `:Play`                     |
| Unit     | row                          | `:PlayRow`                  |
| Note end | next note, note-off, program | `:ReadVoiceRow` `:AdsrStep` |
| Routing  | fixed                        | `:PlayRow`                  |
| Reuse    | patterns                     | `:PlayRow`                  |
| Tempo    | speed, timer                 | `:CmdSpeed` `:InitSong`     |

## Generators

| Generator  | Scope | States       | Writes         | Rate | Set by              | Note-on |
| ---------- | ----- | ------------ | -------------- | ---- | ------------------- | ------- |
| Portamento | voice | glide, done  | period         | tick | instrument, Pattern | restart |
| Vibrato    | voice | delay, swing | period         | tick | instrument, Pattern | restart |
| Slides     | voice | on, off      | period, volume | tick | Pattern             | restart |

## Channel outputs

| Output    | Writers, in tick order                                                                            |
| --------- | ------------------------------------------------------------------------------------------------- |
| Volume    | Pattern (set), ADSR (scale), Slides (add)                                                         |
| Period    | Pattern (note), Arpeggio (note), Portamento (set), Vibrato (add), Pitch table (add), Slides (add) |
| Sample    | Pattern (set)                                                                                     |
| Wave data | Pattern (edit), Wave effect (edit)                                                                |
| DMA       | Pattern (off), Pattern (on)                                                                       |

## Interactions

| From    | To       | Event                                                         |
| ------- | -------- | ------------------------------------------------------------- |
| Pattern | ADSR     | Rows marked `$80` hold it at its sustain point `:AdsrSustain` |
| Pattern | Arpeggio | The entry picks one of three tables `:Arpeggio`               |

- An ADSR table that ends on 0 silences the voice. `:AdsrStep`

## State

| Scope      | Fields                                                            |
| ---------- | ----------------------------------------------------------------- |
| Voice      | wave copy, table positions, delays, effect position, pitch offset |
| Instrument | wave, volume, vibrato, two tables, sustain, effect, 3 arpeggios   |
| Global     | position, row, speed, pattern length, master volume               |

## Open questions

- What does the program's name for the pitch table, `AMF`, stand for?
