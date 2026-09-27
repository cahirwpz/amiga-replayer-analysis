---
player: SoundMon2.2
template: 2
ideas:
  [
    waveform-as-table,
    table-walkers,
    in-place-waveform-effects,
    partial-wave-inversion,
  ]
---

# SoundMon 2.2

A synth voice runs four table walkers over one pool of 64-byte tables.

## Context

| Fact      | Value                                               |
| --------- | --------------------------------------------------- |
| Player    | `SoundMon2.2`                                       |
| Author    | Brian Postma                                        |
| Family    | SoundMon                                            |
| Grew from | `SoundMon2.0`                                       |
| Code read | original: `ext/uade/amigasrc/players/uade/soundmon` |
| Spec      | [specs/soundmon_22.py](../specs/soundmon_22.py)     |

## Key ideas

- Waves and walker tables share one pool. `:InitSong` `:StartSynthNote`
  - Enables: any table can be a wave or a control curve.
  - Costs: each table takes 64 bytes, used or not.
- Four walkers set volume (`ADSR`), period (`LFO`), negated samples (`EG`) and a
  wave byte (`MOD`). Each has its own mode, delay and speed. `:RunWalkers`
  - Enables: envelopes, vibrato and changes in timbre, all as data.
  - Costs: one value per step, with no interpolation.
- The `EG` walker's value sets how many leading samples are negated, 0 to 31.
  `:EgWalker`
  - Enables: a sweep like pulse width, on any wave.
  - Costs: it reaches only the first 32 bytes.
- An effect changes the wave's first 32 bytes in place. It smooths the wave, or
  moves it towards another wave, byte by byte. `:WaveEffect` `:SmoothWave`
  `:MorphToNext`
  - Enables: a timbre that changes during the note, without extra tables.
  - Costs: one effect at a time.
- A note that changes its wave saves the first 32 bytes. The next note writes
  them back. `:SaveWave` `:RestoreWaves`
  - Enables: edits in place, without a copy of the wave per voice.
  - Costs: voices that play the same wave change it together.

## Composer's view

The composer writes positions, patterns, instruments and the table pool. Each
row carries one command and its argument byte. The source calls it `option`.

| Aspect   | Answer                                                                    | Source             |
| -------- | ------------------------------------------------------------------------- | ------------------ |
| Notation | A row: note, instrument, command, argument.                               | `:ReadVoiceRow`    |
| Notation | A position: pattern, instrument transpose and note transpose, per voice.  | `:ReadVoiceRow`    |
| Notation | A synth instrument: wave, then table, length, delay and speed per walker. | `:SynthInstrument` |
| Notation | Command 10 skips the note transpose or the instrument transpose.          | `:NewNote`         |
| Cost     | A chord needs command 0 on every row. A row without it ends the chord.    | `:Options`         |
| Cost     | Commands 13 to 15 change the note and keep the sound running.             | `:NewNote`         |
| Cost     | Command 11 on a row with a note is lost: the instrument sets the effect.  | `:StartSynthNote`  |
| Cost     | Commands 4 and 5 slide once per row. Command 8 slides every tick.         | `:Options`         |

## What is unique

- One arpeggio step and one vibrato position serve all voices. Notes never reset
  them. `:PlayTick`
- The arpeggio cycles over 4 ticks: high nibbles, base note, base note, low
  nibbles. The row's arpeggio and the auto arpeggio add up. `:Arpeggio`
- A larger vibrato argument gives a smaller vibrato: it divides the table value.
  `:TickVoice`
- The `LFO` offset sounds only on the ticks when the walker steps. On other
  ticks, the plain period is written. `:LfoWalker` `:TickVoice`
- A synth note on the same instrument does not restart the channel. Its walkers
  restart. `:NewNote` `:PlayRow`
- `MOD` writes wave byte 32, which the next note does not restore. `:ModWalker`
- A sample with a loop at 0 plays only its loop, never the part after it.
  `:StartNote`

## Open questions

- The wait before DMA on is about 640 CCK (estimate). Does a note with a period
  above 320 then miss its restart (guess)? `:PlayRow`
- Effects 3 and 5 run the same code. Does the editor treat them differently?
  `:MorphToSavedCopy`
