---
player: SoundMon2.2
template: 3
ideas:
  [
    waveform-as-table,
    table-walkers,
    in-place-waveform-effects,
    partial-wave-inversion,
  ]
---

# SoundMon 2.2

Table walkers shape a synth note, and some of them rewrite its wave as it plays.

## Unique ideas

- One pool of 64-byte tables holds the waves and the walker tables. Any table
  can be either. `:InitSong` `:StartSynthNote`
  - Limits: a walker longer than 64 values reads on into the next tables.
- A synth note runs four table walkers. `ADSR` scales the volume, `LFO` offsets
  the period, and `EG` and `MOD` edit the wave. `:RunWalkers`
  - Limits: a value changes only at a step, with no interpolation.
- At each step, `EG`'s value N, from 0 to 31, inverts the wave's first N bytes.
  Sweeping N sounds like a pulse-width sweep, on any wave (inference).
  `:EgWalker`
- One effect per note edits the wave's first 32 bytes as it plays. `:WaveEffect`
  - Smoothing sets each byte to the mean of its two neighbours. `:SmoothWave`
  - A morph moves each byte towards the original wave, its mirror or the next
    table. `:MorphToSaved` `:MorphToMirror` `:MorphToNext`
  - A copy replaces the 32 bytes with the next table's, once. `:CopyNextTable`

## How it plays

The host's tick drives everything. There is no audio interrupt. Loops start by
[loop by reload](../docs/paula-techniques.md#loop-by-reload).

A tick runs the player, all voices and their walkers, in this order. Every
`speed` ticks, a row follows. `:PlayTick`

### Player

The player holds the position, row, tick counter and `speed`, the ticks per row.
It also holds the arpeggio phase and the vibrato phase. `:Module`

- Each tick, it advances both phases. `:PlayTick`
  - **Trap:** both phases are global. A note's arpeggio starts on whatever phase
    the song has reached.
- Each row, each voice reads its entry of the position. The entry holds a
  pattern, an instrument transpose and a transpose. `:ReadVoiceRow`
  - Voice 0 reads the last entry, voice 3 the first.
- After all four voices, it moves to the next row, or to a jump's position.
  `:NextRow`
- It restarts the new notes with a
  [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait) inside the
  tick. `:PlayRow`

### Voice

A voice holds its note, period, instrument, volume and loop. It holds the
command state, the effect, four walkers and its saved bytes. `:Voice`
`:SavedWave`

Each tick, it writes its registers: `:TickVoice`

1. It adds the auto slide, which `AUTO_SLIDE` sets, to the period. `AUDxPER`
   gets the period, plus the vibrato value divided by the vibrato argument.
   - A larger vibrato argument gives a smaller vibrato.
2. `AUDxLC` and `AUDxLEN` get the loop. Without a loop, they get a
   [silent loop](../docs/paula-techniques.md#silent-loop).
3. With an arpeggio, the period and `AUDxPER` get the note's period plus the
   phase's offset. `:Arpeggio`
   - The row's arpeggio and the auto arpeggio, which `AUTO_ARPEGGIO` sets, add
     up.
   - **Trap:** the period holds the base note and the slides. An arpeggio
     overwrites it, undoing the auto slide. `:SetArpPeriod`

Each row, it reads a note, an instrument, a command and its argument:

1. A note clears auto slide, auto arpeggio and vibrato. It adds the transpose
   and sets the period. `:NewNote`
2. `LEGATO`, `LEGATO_FLIP` and `LEGATO_KEEP_ADSR` stop here. Otherwise the
   instrument number, or the last one, gets the instrument transpose. `:NewNote`
3. A new instrument, or any sample note, turns DMA off for a restart. A synth
   note on the same instrument keeps DMA on. `:NewNote`
4. The command runs. `:Options`
   - **Trap:** the legato commands store their argument as the auto arpeggio,
     too. `:SetAutoArp`
   - **Trap:** `LEGATO_FLIP` swaps the effect for its pair. A morph away becomes
     the morph back to the original wave, and back again. `:SetAutoArp`
   - **Trap:** `AUTO_ARPEGGIO`, `LEGATO` and `LEGATO_FLIP` restart `ADSR`. They
     turn it on, even if the instrument has it off. `:SetAutoArp`
   - **Trap:** on a synth voice, `VOLUME` waits for an `ADSR` step. After `ADSR`
     ends, it is lost.
   - **Trap:** a row without a command ends the arpeggio. So do `SLIDE_UP` and
     `SLIDE_DOWN`.
   - **Trap:** `EFFECT` on a row with a note is lost. The note start sets the
     instrument's effect.

A note start writes `AUDxPER`, `AUDxLC`, `AUDxLEN` and `AUDxVOL` at once:

- A sample note plays the whole sample, or up to its loop end. Its loop follows
  at the next tick. `:StartNote`
  - **Trap:** a sample with its loop at 0 plays only its loop.
- A sample note's `AUDxVOL` is the instrument's volume, or the row's.
  `:StartNote`
- A synth note plays its wave, which is also its loop. It restarts all walkers,
  also when DMA stayed on. `:StartSynthNote`
- With `ADSR` on, the synth note's `AUDxVOL` is the first `ADSR` value × the
  voice volume / 64. `:StartSynthNote`

A sample without a loop ends on its silent loop. A synth note loops its wave
until the next note, with no note-off. `:StartNote`

### Walker

A walker holds a table, an index, a mode, a step interval and a countdown. It
steps to its next value when its countdown ends. `:Walker`

Each tick, a synth voice runs its walkers in this order: `:RunWalkers`

1. At an `ADSR` step, `AUDxVOL` gets the value × the voice volume / 64.
2. At an `LFO` step, `AUDxPER` gets the period + the value / its depth.
   - **Trap:** the offset sounds only at a step. On other ticks, the voice
     writes the plain period. `:LfoWalker`
3. At an `EG` step, `EG` edits the wave. `:EgWalker`
4. The effect runs. See the table pool.
5. At a `MOD` step, the value goes into wave byte 32. `:ModWalker`

- **Trap:** a walker reads its table live. If that table is also a wave, wave
  edits change the walker's values. `:StartSynthNote`

### Table pool

All voices share the pool. The replay edits its waves as
[live wave edits](../docs/paula-techniques.md#live-wave-edits). `:Score`

- A synth note with `EG`, `MOD` or an effect saves its wave's first 32 bytes.
  The voice's next note restores them. `:SaveWave` `:RestoreWaves`
  - **Trap:** two voices may play the same wave. If one saves it after the other
    edited it, its restore makes the edit stay.
  - **Trap:** without saved bytes, no effect runs. `EFFECT` and `LEGATO_FLIP`
    then change no wave. `:RunWalkers`
- **Trap:** no note restores `MOD`'s byte, which lies past the saved bytes. A
  wave of 16 words or less never plays it. `:ModWalker`
- **Trap:** `effect_speed` is ticks per pass for smoothing. For a morph, it is
  the change per tick. `:SmoothWave` `:MorphToNext`
- **Trap:** a morph ignores the effect delay, the ticks before the effect
  starts. `:MorphToNext`
- **Trap:** the morph to the next table and the copy read the next table. The
  sound depends on the order of tables. `:CopyNextTable`
