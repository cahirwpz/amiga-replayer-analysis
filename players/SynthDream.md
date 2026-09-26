---
player: SynthDream
control: { sequencer: commands, instrument: tables }
themes: [synthesis]
ideas: [pulse-width-table, soft-edge-pulse, run-length-tables, glide-to-fit]
streams: { voice: 6 }
---

# Synth Dream

A 16-byte pulse wave gets finer width steps from a soft edge sample.

## Key ideas

- A table picks the pulse width in sixteenths.
  `data/annot/SynthDream.yaml:PulseWalker`
- The edge sample takes an in-between value, for finer steps. `:PulseWalker`
- Tables are runs: count, repeat, then values. `:VolumeWalker`
- A glide can fit its slide rate to the note length. `:GlideToFit`
- A position can swap one instrument for another. `:LoadInstrument`

## Streams

| Stream     | Scope | Role       | Carries                                  | Control   | Rate        |
| ---------- | ----- | ---------- | ---------------------------------------- | --------- | ----------- |
| Positions  | voice | sequencer  | pattern, transpose, repeat, swap, volume | loop, end | pattern end |
| Pattern    | voice | sequencer  | note, length, volume, instrument, glide  | end       | note end    |
| Volume     | voice | instrument | volume; runs                             | loop      | tick        |
| Pitch      | voice | instrument | note offset; runs                        | loop      | tick        |
| Pitch fine | voice | instrument | pitch factor; runs                       | loop      | tick        |
| Wave       | voice | instrument | pulse width, edge amount; runs           | loop      | tick        |

## Sequencer

| Aspect   | Value           | Label                            |
| -------- | --------------- | -------------------------------- |
| Time     | lengths         | `:ReadEvent`                     |
| Unit     | tick            | `:VoiceTick`                     |
| Note end | length          | `:VoiceTick`                     |
| Routing  | fixed           | `:VoiceTick`                     |
| Reuse    | patterns, loops | `:ReadPosition` `:RepeatPattern` |
| Tempo    | none            | `:EventTable`                    |

## Generators

| Generator | Scope | States       | Writes | Rate | Set by  | Note-on |
| --------- | ----- | ------------ | ------ | ---- | ------- | ------- |
| Glide     | voice | delay, glide | period | tick | Pattern | restart |

## Channel outputs

| Output    | Writers, in tick order                                          |
| --------- | --------------------------------------------------------------- |
| Volume    | Volume (set), Pattern (add), Positions (add)                    |
| Period    | Pattern (note), Pitch (note), Pitch fine (scale), Glide (scale) |
| Wave data | Wave (edit)                                                     |
| Sample    | Pattern (set)                                                   |
| DMA       | Pattern (on), Pattern (off)                                     |

## Interactions

| From    | To         | Event                                               |
| ------- | ---------- | --------------------------------------------------- |
| Pattern | Volume     | Switches its table after N ticks `:SwitchVolTable`  |
| Pattern | Pitch fine | Switches its table after N ticks `:SwitchFineTable` |

- Legato keeps the channel running between notes. `:LegatoOn`

## State

| Scope      | Fields                                                             |
| ---------- | ------------------------------------------------------------------ |
| Voice      | position, repeats, event, ticks left, table positions, runs, glide |
| Instrument | four tables, or a sample                                           |
| Global     | none                                                               |

## Open questions

- Did any composers besides the authors use this format?
