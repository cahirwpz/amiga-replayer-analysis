---
player: AbyssHighestExperience
template: 3
ideas:
  [
    generated-waves,
    filter-bank,
    sweep-between-limits,
    performance-list,
    hard-cut,
    free-running-buffer,
  ]
---

# AHX

There are no samples. Each voice loops one buffer, refilled from built-in waves
and their filtered copies.

## Unique ideas

- At start, the replay builds 45 waves. They are triangles and saws in 6
  lengths, 32 squares of rising pulse width, and noise. `:MakeWaves`
- Each wave gets 31 low-pass and 31 high-pass copies. A filter position picks
  one copy. `:MakeFilters`
  - A filter sweep costs no filter work during play.
  - Each copy starts from the state of three passes over its wave. It loops
    without a jump at its end.
  - Limits: the waves and their copies take 412 kB of memory (estimate).
- Each voice loops one 640-byte buffer, forever. A new wave refills it with
  copies of itself, with no DMA restart. `:FillBuffer`
  - The wave length picks the octave. The buffer holds 160 copies of 4 bytes, up
    to 5 copies of 128.
  - CPU: medium. A square or noise wave copies 640 bytes per voice every tick
    (estimate).
- Pulse width and filter position are sweeps between two limits. `:Sweep`
  - A sweep that starts outside its limits runs in first. It turns only at the
    second limit it meets.
- Each instrument runs an instrument program, `Performance`. A step sets a wave
  and a note, and runs two commands. `:PerformanceStep`
- An instrument can end its note some ticks before the next row that starts an
  instrument. The replay reads that row early. `:HardCut`
  - An instrument flag turns this note cut into a release over the ticks left.

## How it plays

A [CIA timer](../docs/paula-techniques.md#cia-timer) runs the tick at the
module's rate, 50 to 200 Hz. There is no audio interrupt. `:SetTickRate`

DMA goes on once at start, on four silent buffers. `:StartChannels`

A tick first writes each voice's results of the last tick to Paula. Then come
the rows, if due, and each voice's tick work. `:PlayTick`

### Player

The player holds the position, row, `speed` and a row countdown. It holds the
jump target, the host's volume and the noise seed. `:Player`

- At a new position, each voice takes its track and transpose. It also takes the
  next position's track, for the instrument's note cut. `:ReadPosition`
- After `speed` ticks, the player moves to the next row, or to the jump target.
  After the last position comes the restart position. `:AdvanceRow`
- **Trap:** `SET_VOLUME` on one track can set the track volume of all four
  voices. `:ReadRow`

### Voice

A voice holds its track, transpose, track note, step note, wave and buffer.
Track slides move its slide offset, and the program its program slide, both
period offsets. `:Voice`

Its volume multiplies five parts, each out of 64. They are the envelope, note
volume, step volume, track volume and host's volume. `:VoiceVolume`

- The note volume starts at the instrument's volume.

Each row, the voice reads a note, an instrument, a command and its argument:
`:ReadRow`

1. `CUT` and `DELAY` act first. `DELAY` reads the whole row again after its
   ticks, song commands too.
   - Both need an argument below `speed`. Otherwise they do nothing.
2. Song commands act: jumps and `speed`. The volume slide takes its rates.
3. An instrument number starts the instrument. It restarts the envelope,
   vibrato, sweeps and program, and clears the slide offset. `:SetInstrument`
   - **Trap:** a new instrument keeps the last wave, step note and pulse width.
     Until a step sets a wave, the buffer keeps the old wave.
4. `SQUARE_SET` sets the pulse width. `FILTER_SET` sets the filter position, or
   the argument of the program's next `FILTER_POSITION`.
   - **Trap:** `SQUARE_SET` makes the program skip its next `SQUARE_POSITION`.
5. A note sets the track note. With `TONE_SLIDE` or `TONE_SLIDE_VOLUME`, the
   slide offset slides towards it instead. `:Portamento`
   - **Trap:** a note without an instrument changes only the pitch. It keeps the
     slide offset.
6. Slides, fine slides, vibrato depth and volume commands act.

Each tick, in this order: `:VoiceFrame`

1. The note cut runs. Without the release flag, it sets the note volume to 0.
   `:HardCut`
   - **Trap:** the note cut reads the next row in track order. It misses jumps,
     and wraps to position 0, not to the restart.
2. Envelope phases last set tick counts. No note-off starts the release.
   `:Envelope`
3. The volume slide, the slide and the vibrato run. `:Portamento` `:Vibrato`
   - Vibrato depth is in periods. Low notes get a smaller pitch change.
4. The program runs. Then the sweeps move, and the square wave is rebuilt.
5. The voice picks the filter position's copy of its wave. `:SelectWave`
6. The period is the table period of track note, transpose and step note. It
   adds the slide offset, the program slide and vibrato. `:VoicePeriod`
   - A fixed note plays the step note alone, without the slide offset.

At the next tick's start, the voice writes Paula: `:WriteVoice`

1. `AUDxPER` gets the period, if it changed.
2. The buffer gets copies of the wave, if it changed. `:FillBuffer`
   - The copy runs while Paula plays the buffer. A new wave starts wherever
     Paula is, as a
     [live wave edit](../docs/paula-techniques.md#live-wave-edits).
3. `AUDxVOL` gets the volume, every tick.

No note writes `AUDxLC`, `AUDxLEN` or DMA. There is no note-off and no rest. A
voice falls silent only through its volumes.

### Instrument program

The program holds its step, step speed and countdown, in the voice. `:Voice`

- Every step speed ticks, one step runs. A wave in it refills the buffer and
  clears the program slide. `:PerformanceStep`
- Its two commands run next. Then a note in it sets the step note and the fixed
  note flag. `:PerformanceCommand`
- At the list's end, the last step holds. The program slide stops.
- `STEP_JUMP` jumps to a step. A jump back loops the program.
- `STEP_VOLUME` sets the note, step or track volume.
  - **Trap:** the track volume outlives the instrument. No instrument resets it.
- `TOGGLE_SWEEPS` turns a sweep on or off. Revision 0 modules toggle only the
  pulse width sweep. They lack `FILTER_SET` and `FILTER_POSITION`.

### Sweeps and waves

A sweep holds a position, two limits, a direction, a countdown and an on flag.
`:Sweep`

- The pulse width moves by one every N ticks, only on a square wave.
  `:SquareSweep`
- At filter speeds 0 to 3, the filter position moves by 5 to 2 per tick. Higher
  filter speeds move it by one every filter speed − 3 ticks. `:FilterSweep`
- Pulse width limits are for the longest wave. Shorter waves get fewer widths.
- Each tick, a square wave is resampled from a 128-byte square. `:BuildSquare`
- Noise starts at a new random offset every tick. `:NoiseOffset`
