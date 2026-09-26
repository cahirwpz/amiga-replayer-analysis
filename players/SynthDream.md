---
player: SynthDream
control: commands
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
- Events swap the volume or fine pitch table after N ticks. `:SwitchVolTable`
- A glide can fit its slide rate to the note length. `:GlideToFit`
- A position can swap one instrument for another. `:LoadInstrument`

## Streams

| Stream     | Scope | Carries                                  | Control   | Rate        |
| ---------- | ----- | ---------------------------------------- | --------- | ----------- |
| Positions  | voice | pattern, transpose, repeat, swap, volume | loop, end | pattern end |
| Pattern    | voice | note, length, volume, instrument, glide  | end       | note end    |
| Volume     | voice | volume; runs                             | loop      | tick        |
| Pitch      | voice | note offset; runs                        | loop      | tick        |
| Pitch fine | voice | pitch factor; runs                       | loop      | tick        |
| Wave       | voice | pulse width, edge amount; runs           | loop      | tick        |

## Generators and interactions

- Glide: the period scales by a factor each tick, after a delay. `:Glide`
- Legato keeps the channel running between notes. `:LegatoOn`

## State

| Scope      | Fields                                                             |
| ---------- | ------------------------------------------------------------------ |
| Voice      | position, repeats, event, ticks left, table positions, runs, glide |
| Instrument | four tables, or a sample                                           |
| Global     | none                                                               |

## Open questions

- Did any composers besides the authors use this format?
