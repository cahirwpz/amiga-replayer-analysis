---
player: RobHubbard
template: 3
ideas:
  [replay-in-module, byte-write-sweep, sample-rate-tune, period-scaled-vibrato]
---

# Rob Hubbard

A tiny replay ships inside each module. One byte written per tick sweeps the
pulse width of a short wave.

## Unique ideas

- Each module carries its own replay behind five jump entries. Each game gets
  the replay its music was written for. `:Play` `:InitSong`
  - Limits: every module repeats the 830 bytes of replay code.
- A sweep writes one byte per tick into a short wave, like [Fred](Fred.md)'s
  pulse wave. The edge between two byte values moves. `:Sweep` `:SweepDown`
  - Limits: the edge moves by one byte per tick.
- Each sample stores its recording rate. The period is scaled by it, so any rate
  plays in tune. `:InitSamples` `:NoteOn`
  - Limits: the period table holds 49 notes, four octaves.
- Vibrato adds a share of the period, not a fixed amount. It has the same
  interval on every note. `:Vibrato`
  - Limits: the share is a whole number. On short periods, the vibrato gets
    coarse.

## How it plays

The host's tick calls `:Play`. The replay sets no timer.

The level 4 vector points at a bare return. Audio interrupts do nothing.
`:NullInterrupt`

A tick runs voices 3 down to 0. Each voice counts down to its next note, or runs
its effects. `:VoiceTick`

### Player

The player holds a playing flag, the unit and the default instrument. The unit
is the ticks per step of a note's length. `:Module`

- The host saves and restores the level 4 vector through two jump entries.
- The start stops the sound and sets up samples, waves and voices. It stores the
  default instrument the host passes. `:InitSong`
  - `rh.GMUSIC` clears the song number and always plays song 0. `rh.FLYMUS`
    plays the song it is given.
  - `rh.GMUSIC` sets up 11 samples and `rh.FLYMUS` 6. The rest of the code is
    the same. `:InitSamples`
- A song record holds the unit, then one position list per voice. `:InitVoices`
- `STOP` on any voice stops the whole song. DMA goes off on all channels, and
  `ADKCON` loses all attach modes. `:StopSound`
  - **Trap:** `STOP` also ends the tick. Lower voices skip it. `:ReadStream`

### Instrument

An instrument is a sample or a wave. It holds a start, a loop offset, a length,
a tune and a volume. `:Instrument`

- A vibrato divider and a vibrato table set its vibrato. Two bounds set its
  sweep.
- Instruments 0 to 10 are samples. Each tune is 3579545 / the sample's rate.
  `:InitSamples`
- Instruments 13 to 15 are three waves in the replay's data. `:InitWaves`
  - In PGA Tour Golf, wave 13 has vibrato. Wave 15 has vibrato and a sweep.
- A loop offset of 0 plays the sample once, then a
  [silent loop](../docs/paula-techniques.md#silent-loop). `:QueueLoop`
- A negative loop offset loops the whole sample. A positive one loops from it to
  the end.
- A negative `INSTRUMENT` number picks the default instrument. `:SetInstrument`

### Voice

A voice holds its pattern position, position list, tick counter, note and
period. It holds the portamento step, instrument, vibrato and sweep positions.
`:Voice`

Each tick, in this order: `:VoiceTick`

1. The tick after a note start, `AUDxLC` and `AUDxLEN` get the loop. This is a
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). `:QueueLoop`
2. The tick counter counts down. At 0, the voice reads its next event.
   `:CountDown`
3. One tick before 0, DMA goes off. Every note ends in a one-tick gap.
   - **Trap:** an event of one tick skips the gap. The next sample then waits
     for the old loop's end.
4. Otherwise, portamento adds its step to the period. `AUDxPER` gets the period.
   `:Portamento`
5. Vibrato writes `AUDxPER`: period + period / divider × the table value. The
   period itself stays. `:Vibrato`
   - `VIBRATO_LOOP` restarts the vibrato table.
6. The sweep writes one byte into the wave. See the sweep. `:Sweep`
   - **Trap:** effects also run during a `REST`. A resting voice still edits its
     wave.

The voice reads commands until an event: a note or a `REST`. `:ReadStream`

- A byte up to `NOTE_MAX` is a length. The note byte follows. There are no rows.
- `INSTRUMENT` picks the instrument. `PORTAMENTO` sets a signed step per tick.
  `:SetInstrument` `:SetPortamento`
- `PATTERN_END` reads the next pattern from the position list. Offset 0 wraps to
  the first. `:NextPosition`
- `NOP` and unknown bytes above `STOP` are skipped.
- **Trap:** every event clears portamento and the sweep direction. A portamento
  lasts one note. `:CountDown`

A note start: `:NoteOn`

1. The tick counter gets the length × the unit.
2. The sweep position gets the lower bound. The vibrato table restarts.
3. `AUDxLC` and `AUDxLEN` get the whole sample. `AUDxVOL` gets the instrument's
   volume.
4. `AUDxPER` and the period get the table value × the tune / 1024.
5. DMA goes on.

- The volume is fixed per instrument, with no envelope.
- **Trap:** the sweep position restarts, but the wave bytes stay. The edge jumps
  at the note start (inference).

A voice falls silent through the gap tick, or a sample's silent loop. `REST`
gives `AUDxLC` and `AUDxLEN` the silent loop for a length. `:Rest`

### Sweep

A voice's sweep holds a position and a direction. The instrument holds its lower
and upper bounds. `:Sweep`

1. Up, the position steps up and the byte there gets `LOW`. `:Sweep`
2. Past the upper bound, it turns. That byte gets `HIGH`.
3. Down, the position steps down and the byte there gets `HIGH`. `:SweepDown`
4. At the lower bound, it turns. That byte gets `LOW`.

- The edits are [live wave edits](../docs/paula-techniques.md#live-wave-edits).
  - **Trap:** voices on one instrument share its wave. Each voice sweeps it from
    its own position.
- **Trap:** the turn writes one byte past the upper bound. In `rh.GMUSIC`, this
  byte is the first song's unused first byte. `:Sweep`

## Open questions

- Do other Rob Hubbard modules sweep samples, not only waves?
- What calls `:Play` in the game? The replay sets no timer.
