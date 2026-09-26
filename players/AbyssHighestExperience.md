---
player: AbyssHighestExperience
control: { sequencer: commands, instrument: commands }
themes: [synthesis]
ideas:
  [
    generated-waves,
    filter-bank,
    sweep-between-limits,
    performance-list,
    hard-cut,
  ]
streams: { song: 1, voice: 2 }
---

# AHX

No samples: every sound comes from built-in waves and their filtered copies.

## Key ideas

- The player generates triangle, saw, 32 pulse and noise waves.
  `loader.c:ahxInitWaves`
- It adds 31 low-pass and 31 high-pass copies of each wave.
  `:setUpFilterWaveForms`
- Filter and pulse width sweep back and forth between two limits.
  `replayer.c:ProcessFrame`
- Each instrument runs a performance list: wave, note, two commands per step.
  `:pListCommandParse`
- Wave length picks the octave. Copies of the wave fill a fixed buffer.
  `:CopyWaveformToPaulaBuffer`
- Hard cut: the player reads the next row and ends the note early.
  `:ProcessFrame`

## Streams

| Stream      | Scope | Role       | Carries                       | Control | Rate          |
| ----------- | ----- | ---------- | ----------------------------- | ------- | ------------- |
| Positions   | song  | sequencer  | track and transpose per voice | loop    | pattern end   |
| Track       | voice | sequencer  | note, instrument, command     | jump    | row           |
| Performance | voice | instrument | wave, note, two commands      | jump    | every N ticks |

## Sequencer

| Aspect   | Value               | Label                          |
| -------- | ------------------- | ------------------------------ |
| Time     | rows                | `:tickReplayer`                |
| Unit     | row                 | `:tickReplayer`                |
| Note end | next note, note-off | `:ProcessStep` `:ProcessFrame` |
| Routing  | fixed               | `:tickReplayer`                |
| Reuse    | patterns            | `:tickReplayer`                |
| Tempo    | speed               | `:ProcessStep`                 |

## Generators

| Generator    | Scope | States                          | Writes         | Rate          | Set by                         | Note-on |
| ------------ | ----- | ------------------------------- | -------------- | ------------- | ------------------------------ | ------- |
| ADSR         | voice | attack, decay, sustain, release | volume         | tick          | instrument                     | restart |
| Vibrato      | voice | delay, swing                    | period         | tick          | instrument, Track              | restart |
| Slides       | voice | on, off                         | period, volume | tick          | Track, Performance             | restart |
| Square sweep | voice | up, down                        | wave data      | every N ticks | instrument, Performance, Track | restart |
| Filter sweep | voice | up, down                        | sample         | every N ticks | instrument, Performance, Track | restart |

## Channel outputs

| Output    | Writers, in tick order                                        |
| --------- | ------------------------------------------------------------- |
| Volume    | Track (set), ADSR (scale), Slides (add), Performance (scale)  |
| Period    | Track (note), Performance (note), Slides (add), Vibrato (add) |
| Sample    | Performance (set), Filter sweep (set)                         |
| Wave data | Square sweep (edit)                                           |

## Interactions

| From  | To           | Event                                                                 |
| ----- | ------------ | --------------------------------------------------------------------- |
| Track | Square sweep | Command 9 sets its position; the next `3xx` is ignored `:ProcessStep` |
| Track | Filter sweep | Command 4 sets its position `:ProcessStep`                            |

- Noise reads a long noise table at a new random offset each tick.
  `:ProcessFrame`

## State

| Scope      | Fields                                                          |
| ---------- | --------------------------------------------------------------- |
| Voice      | track, list step and wait, ADSR, filter and pulse positions     |
| Instrument | ADSR, wave length, filter and pulse limits and speeds, the list |
| Global     | position, row, tempo                                            |

## Open questions

- Every label here is from the C port. Does the 68k replayer agree?
- Does the small external replayer differ in sound from the tracker's code?
