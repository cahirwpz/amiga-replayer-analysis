---
player: SonicArranger
template: 3
ideas:
  [
    in-place-waveform-effects,
    waveform-as-table,
    per-voice-wave-copy,
    sustain-rows,
    beam-noise,
  ]
---

# Sonic Arranger

Each voice plays its own copy of a synth wave. One of 17 wave effects rewrites
that copy as it plays.

## Unique ideas

- A synth note copies its wave into the voice's record, in chip memory. Paula
  plays that copy, and the effect edits only it. `:StartSynthWave`
- Every N ticks, the instrument's one effect rewrites a byte range of the copy.
  The changes pile up until the next note. `:WaveEffect`
  - Limits: medium CPU. Most effects touch every byte of the range.
- Several effects read a second wave. It is a morph target, a pulse width table
  or a limit table. `:FreeNegator` `:Metamorph` `:LowPassFilter2`
- Two effects take noise from the video beam position. It depends on when the
  tick runs. `:NoiseGenerator1` `:NoiseGenerator2`
- A synth note after a synth note keeps DMA on. Its wave overwrites the playing
  copy, with no restart. `:ReadVoiceRow`
- A position gives each voice a start row in one shared list of rows. Tracks may
  overlap. `:ReadPosition`
  - Limits: one pattern length for all voices.

## How it plays

In the original, a [CIA timer](../docs/paula-techniques.md#cia-timer) interrupt
at the subsong's rate causes a software interrupt. That runs the tick.
`:SetTimer`

There is no audio interrupt. A tick writes last tick's sample loops, then a row
every `speed` ticks, then all voices. `:Play`

### Player

The player holds `speed`, the pattern length, the row and position counters and
the master volume. `:Module`

- After pattern length rows, it reads the next position. After the last one, it
  goes to the restart position. `:PlayRow`
- A position gives each voice a start row and two transposes. `:Track`
- **Trap:** pattern length, jump and break commands act on the shared row
  counter. One voice's row ends all tracks. `:CmdPatternBreak`

### Voice

The first 128 bytes of the voice's record are its wave copy. It also holds a
note, a previous note, instrument, volume, slides, pitch offset and silent flag.
`:Voice`

Each row, it reads a note, an instrument, flags, a command and its argument:
`:ReadVoiceRow`

1. A row without a note may name an instrument. Its tables restart, and the wave
   copy plays on. `:SetInstrument`
   - **Trap:** after silence, `AUDxLC` still holds the silent loop. The voice
     stays silent until a note. `:VoiceTick`
2. `HOLD` keeps the note. `NOTE_OFF` cuts the voice. `:VoiceOff`
3. A note gets the note transpose, its instrument number the instrument
   transpose. Row flags can skip either.
4. If the voice's last note was a sample, the channel stops. The adaptation
   waits for a [stop signal](../docs/paula-techniques.md#stop-signal).
   `:StopChannel`
   - **Trap:** after a synth note, a sample note keeps DMA on. The sample starts
     at the copy's next loop.
5. A new instrument sets volume, portamento, vibrato and tables. Otherwise, the
   old one restarts its tables. `:RestartInstrument`
   - **Trap:** a note with no instrument, on a voice with none, cuts the voice.
     Its command is lost.
6. `AUDxLC` and `AUDxLEN` get the sample or the copy. DMA goes on at the tick's
   end. `:StartSample` `:StartSynthWave`
7. The command runs, after clearing both slides. `:RowCommand`

A sample plays its first part and its loop once. The next tick writes the loop,
as a [loop by reload](../docs/paula-techniques.md#loop-by-reload). `:WriteLoop`

- A sample whose first pass is shorter than a tick plays twice.
- A loop of 1 ends on a [silent loop](../docs/paula-techniques.md#silent-loop).
  A loop of 0 loops the whole sample.

Each tick, a voice makes its period, then its volume: `:VoiceTick`

1. A silent voice writes `AUDxVOL` 0 and the silent loop, and stops.
2. The row's flags pick one of three arpeggios. Otherwise, `ROW_ARPEGGIO` plays
   the note, +x, +y. `:Arpeggio` `:RowArpeggio`
   - **Trap:** each tick reads the current row's flags. A row without them ends
     the arpeggio.
   - **Trap:** the arpeggio position runs on across rows, into another arpeggio.
3. Portamento glides from the previous note, until one step from its target.
   `:Portamento`
   - **Trap:** portamento replaces the arpeggio. The arpeggio moves only its
     target.
4. After its delay, vibrato adds the sine × 4 / depth, in periods. `:Vibrato`
   - A larger depth gives a smaller vibrato. `CmdVibrato`'s argument has no
     effect.
5. The pitch table subtracts its value. `AUDxPER` gets the period minus the
   pitch offset. `:PitchWalker` `:SetPitch`
   - The pitch offset starts at the fine tune. A slide adds to it each tick but
     the row's. The change stays until the next instrument start.
   - **Trap:** `Laser` adds `start` to the pitch offset, for `end` runs.
     `FmDrum` resets it to the fine tune, dropping slides. `:FmDrum`
6. A synth voice runs its wave effect. `:WaveEffect`
7. `AUDxVOL` gets volume × table value × master volume / 4096. The volume slide
   follows. `:VolumeWalker`

### Table walkers

Each voice walks a pitch table (the format's `AMF`) and a volume table (its
`ADSR`). Each walker holds a position and a wait. `:PitchWalker` `:AdsrStep`

- A table steps every `delay` ticks. Its first `length` bytes play once, then
  `repeat` bytes loop. Without a repeat, the last byte holds.
- While the row's note is `HOLD`, the volume table stops at its sustain point. A
  sustain delay only slows it down. `:AdsrSustain`
  - **Trap:** a held note needs `HOLD` on every row. Another row starts the
    release.
- A volume table without a repeat that ends on 0 sets the silent flag.
  `:AdsrStep`
  - **Trap:** the test reads the level after the master volume. Below 64, a last
    byte of 1 rounds to 0.

A voice falls silent by `NOTE_OFF`, its volume table or a missing sample. DMA
stays on.

### Wave effect

The instrument gives the effect, an argument, a delay and a byte range `start`
to `end`. The argument is a value or the second wave's number. `:Instrument`

The voice holds the effect position, a counter, a wait and three flags. `:Voice`

- Every `delay` ticks, the effect runs. The effect position moves one byte per
  run, from `start` to `end`, then back. `:EffectStep`
  - **Trap:** an instrument-only row restarts the effect state. The copy keeps
    its edits.
- `Metamorph` morphs the range to the second wave. `Oszilator` morphs to it and
  back, forever. `:Oszilator`
- `FreeNegator` rebuilds a pulse from the wave. The second wave's bytes set the
  width, one per run. `:FreeNegator`
- **Trap:** `RotateHorizontal` also rotates the byte after `end`. With `end`
  127, that is the high byte of the voice's note. `:RotateHorizontal`

## Open questions

- Is the unused argument of `CmdVibrato` a bug of version 2.18 only?
  `:CmdVibrato`
