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
- The `EG` walker's value sets how many leading wave bytes are negated, 0 to 31.
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

| Aspect   | Answer                                                                                  | Source             |
| -------- | --------------------------------------------------------------------------------------- | ------------------ |
| Notation | A row: note, instrument, command, argument.                                             | `:ReadVoiceRow`    |
| Notation | A position: pattern, instrument transpose and note transpose, per voice.                | `:ReadVoiceRow`    |
| Notation | A synth instrument: wave, then table, length, delay and speed per walker.               | `:SynthInstrument` |
| Notation | `NO_TRANSPOSE` skips the note transpose or the instrument transpose.                    | `:NewNote`         |
| Cost     | A row without a command ends a chord. So do `SLIDE_UP` and `SLIDE_DOWN`.                | `:Options`         |
| Cost     | `LEGATO_FLIP`, `LEGATO` and `LEGATO_KEEP_ADSR` change the note and keep the wave.       | `:NewNote`         |
| Cost     | Only `LEGATO_KEEP_ADSR` keeps the volume envelope. The others restart `ADSR`.           | `:SetAutoArp`      |
| Cost     | `LEGATO_FLIP` swaps the effect for its pair, e.g. `MorphToNext` for `MorphToSavedCopy`. | `:SetAutoArp`      |
| Cost     | An arpeggio sets the period each tick. It undoes the auto slide and vibrato.            | `:SetArpPeriod`    |
| Cost     | Vibrato and `LFO` add in periods. Low notes get a smaller pitch change.                 | `:TickVoice`       |
| Cost     | `EFFECT` on a row with a note is lost. The instrument sets the effect.                  | `:StartSynthNote`  |
| Cost     | `SLIDE_UP` and `SLIDE_DOWN` slide once per row.                                         | `:Options`         |
| Cost     | `AUTO_SLIDE` slides every tick.                                                         | `:Options`         |
| Cost     | A note with a period above 544 can start at the old sample's reload.                    | `:PlayRow`         |
| Cost     | With 6 bitplanes on, the limit rises to a period of 771.                                | `:PlayRow`         |

## What is unique

- One arpeggio step and one vibrato position serve all voices. Notes never reset
  them. `:PlayTick`
- Over 4 ticks, the arpeggio adds the high 4 bits, nothing, nothing, the low 4.
  The row's arpeggio and the auto arpeggio add up. `:Arpeggio`
- A larger vibrato argument gives a smaller vibrato. It divides the table value.
  `:TickVoice`
- The `LFO` offset sounds only on the ticks when the walker steps. On other
  ticks, the plain period is written. `:LfoWalker` `:TickVoice`
- A synth note on the same instrument does not restart the channel. Its walkers
  restart. `:NewNote` `:PlayRow`
- `MOD` writes the wave byte just past the saved bytes. The next note does not
  restore it. `:ModWalker`
- A sample with a loop at 0 plays only its loop, never the part after it.
  `:StartNote`

## Open questions

- `MorphToSaved` and `MorphToSavedCopy` run the same code. Does the editor treat
  them differently? `:MorphToSavedCopy`
