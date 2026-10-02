---
player: MugicianII
template: 3
ideas: [waveform-as-table, in-place-waveform-effects, swing, voice-mixing]
---

# Mugician II

A 128-byte wave is a sound, a volume table or a vibrato table. Effects rewrite
it while it plays, and a mixer adds four sample voices.

## Unique ideas

- An instrument plays one wave and reads two more as tables. One sets the
  volume, one offsets the period. `:Instrument` `:VolumeFromWave`
  `:VibratoFromWave`
  - Limits: each table costs a whole wave.
- An effect rewrites the played wave in place, every N ticks. Its 15 handlers
  smooth, shift, negate or blend waves. `:RunEffect`
  - Limits: the effect belongs to the instrument. Voices on it share the wave.
- Rows alternate between two speeds, the nibbles of the speed byte.
  `:SwingSpeeds`
- Voices 3–6 are mixed into channel 0, at a mix rate the user sets. `:MixVoices`
  - Limits: they play samples only.
  - Limits: the sum of four voices is not scaled. It clips to one byte.
    `:BuildMixTables`
  - Limits: CPU is high. At 16 kHz, the mix takes about half of a 68000
    (estimate).

## How it plays

Channel 0's audio interrupt runs the replay, once per buffer, near 50 Hz
(estimate). It queues the other buffer and mixes into it. `:Interrupt`

A tick writes pending loops and reads all seven rows. Then it runs each voice,
mixes, counts the tick and turns DMA on. `:Play`

### Player

The player holds the position, row, tick counter, pattern length and filter. It
holds the speed pair, the two speeds of a swing. `:Module`

- Host song N plays subsongs 2N and 2N+1. Voices 0–2 read the first, voices 3–6
  the second.
  - **Trap:** both subsongs share one position. The first subsong's length,
    restart and speed rule both. `:NextTick`
- Each tick, the tick counter counts down. At 0, it reloads from the speed
  pair's low nibble, and the nibbles swap. `:NextTick` `:SwingSpeeds`
- After 64 rows, or the pattern length, the next position follows. After the
  subsong's length, its restart position follows. `:NextTick`
  - The pattern length is global. It holds for all later patterns.
    `:CmdPatternLength`

### Voice

A voice holds its pattern, transpose, note, instrument, command, argument,
period and volume. It holds a slide, its target, and two table walkers, the
volume and vibrato walkers. `:Voice`

Each tick, a voice first reads its row: `:ReadRow`

1. At a new position, it reads its pattern and transpose.
2. Between rows, and on a row without a note, the last command runs again.
   `:RowCommands`
   - **Trap:** `SPEED` runs every tick until the voice's next note. It undoes a
     `SWING` from any voice. `:CmdSpeed`
   - `FILTER_FLIP` flips the
     [audio filter](../docs/paula-techniques.md#audio-filter-switch) every tick
     until the next note. `:VoiceTick`
3. A note sets the note, instrument, command and argument. `PORTAMENTO` keeps
   the note and instrument. The row's note becomes its target.
   - **Trap:** an effect byte below `FIRST_COMMAND` is no command. It is the
     target note of a slide.
   - **Trap:** `ARPEGGIO` writes the instrument's arpeggio table number. Every
     voice on that instrument changes, for the rest of the song.
4. A wave note writes the wave to `AUDxLC` and `AUDxLEN`. It turns DMA off,
   except for `LEGATO`. `:StartWave`
   - With `LEGATO`, the new wave starts at the old wave's next reload.
   - Unless `KEEP_EFFECT` or `KEEP_BOTH`, the effect restarts. Its source wave,
     wave A, is copied over the played wave. `:CopyWaveA`
   - **Trap:** the copy and restart act on the instrument. They reset the wave
     for every voice on it.
5. A sample note on voices 0–2 writes the whole sample and turns DMA off. Its
   loop follows at the next tick, by
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). `:StartSample`
   `:WriteLoops`
   - Without a loop, a [silent loop](../docs/paula-techniques.md#silent-loop)
     follows.
6. The slide, vibrato and arpeggio restart. Unless `KEEP_VOLUME`, `KEEP_BOTH` or
   `PORTAMENTO`, the volume walker restarts too. `:RestartLists`
   - **Trap:** a slide counts from the note. After a `SLIDE`, a `PORTAMENTO`
     jumps back to the old note first.
7. After the mix, half a tick later, DMA goes on as a
   [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait). `:Play`

Then the voice runs, in this order: `:VoiceTick`

1. The instrument's effect runs. See the effect. `:RunEffect`
2. Every `volume_speed` ticks, the volume walker steps. `AUDxVOL` gets (127 −
   byte) / 4. `:VolumeFromWave`
   - A byte of −128 is loudest, +127 silent.
   - After byte 127, it loops if `VOLUME_LOOPS` is set. Otherwise the volume
     holds.
3. Every tick, the arpeggio adds the next of 32 offsets to the note. The period
   comes from the instrument's tuning, one of 16. `:ArpeggioStep`
4. `SLIDE` and `PORTAMENTO` add the slide. Past the target, the slide stops on
   it. `:Portamento`
   - The period past the target plays for one tick.
   - The slide adds to the arpeggio's period.
5. After its delay, the vibrato walker subtracts its byte from the period.
   `AUDxPER` gets the result. `:VibratoFromWave`
   - Vibrato steps in periods. Low notes get a smaller pitch change.
   - After byte 127, it loops to `vibrato_loop`. From 128 up, it reads the next
     wave.

No command ends a note. A voice falls silent through a +127 volume byte, or a
sample end without a loop.

### Effect

The instrument holds the effect, its speed, its step and wave A. Wave B is a
second source wave. `:Instrument`

- The effect runs once per tick per instrument. The first voice on it paces it
  with its effect delay. `:EffectOncePerTick` `:EffectDelay`
  - **Trap:** the check covers four instruments. A fifth can run twice in a
    tick.
  - **Trap:** voices 3–6 run their wave's effect, too. They never play that
    wave.
- The played wave changes as a
  [live wave edit](../docs/paula-techniques.md#live-wave-edits).
- Smoothing makes each byte a mean of its neighbours. `:SmoothForward`
  `:SmoothWeighted` `:SmoothNeighbours` `:SmoothThenOctave`
- Shifts rotate by a byte, or halve or double the cycle. `:RotateLeft`
  `:OctaveUp` `:OctaveDown`
- A negate sweep flips the sign of one byte, or two bytes, per step. It sounds
  like a pulse-width sweep (inference). `:NegateSweep` `:NegatePair`
- Blends mix wave A with wave B. `:PhaseWithB` `:CrossfadeSlow` `:AddWaveB`
  `:AddRamp`

### Mixer

A mixed voice is voice 3, 4, 5 or 6. The mixer holds its pointer, end, loop
length, stop flag and step. `:MixedVoice`

1. A sample note on a mixed voice sets its pointer, end and loop length. `:Play`
   - **Trap:** only a sample note sets the pointer. A wave note keeps the old
     sample, at the new volume and period.
2. A changed period gives a new step, in 8.8 fixed point. `:MixStep`
3. Per output byte, each voice's byte goes through its volume table. The sum
   goes through the clip table. `:MixVoices`
   - Fractions of the step restart at 0 every tick.
4. After the mix, a voice past its end steps back by its loop length. Without a
   loop, it stops. `:CheckSampleEnds`
   - Within a tick, a voice reads on past its end.
