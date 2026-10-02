---
player: Fred
template: 3
ideas: [replay-in-module, byte-write-sweep, in-place-waveform-effects]
---

# Fred

Each voice builds its wave in its own buffer, by a pulse sweep or a morph.

## Unique ideas

- A pulse instrument holds low bytes below an edge and high bytes above it. Each
  step moves the edge by one byte. `:Pulse` `:PulseInit`
  - It gives a pulse-width sweep, as on the C64, for one byte write per step.
  - Limits: the wave is at most 64 bytes.
- A morph instrument rewrites 32 bytes every tick. Each byte is a source byte
  plus the step times a delta. `:MorphStep` `:MorphWrite`
  - CPU: medium. 32 multiplies per tick per voice take 2 to 3% of a frame
    (estimate).
  - Limits: the morph wave is 32 bytes long.
  - None of the three Fuzzball modules uses a morph instrument.
- Two voices on one instrument sweep independently, each in its own buffer.
  `:Voice`
- Restart flags let a sweep span a phrase, or restart at each note. `:NoteOn`
- A turn count can stop a sweep after N turns. `:Pulse` `:MorphStep`
- The ADSR is timed. The release starts after a set number of sustain ticks.
  `:Sustain`
  - Limits: the note's length cannot end the sustain.

## How it plays

The module holds the replay and starts with jumps to its entries. `:InitSong`

The host's timer calls the tick, with no audio interrupt. A tick runs voices 3
down to 0. `:Play`

### Player

The player holds the song, `speed`, a stopped flag and a fade level. `:Module`

- A song start points each voice at its track's first pattern. `:InitSong`
- `SPEED` sets the speed for all voices. `:SetSpeed`
  - **Trap:** a count takes the speed when the stream sets it. Counts set before
    `SPEED` keep the old speed, on any voice.
- The host starts a fade. Each voice that runs its effects lowers the fade level
  once. `:StartFade` `:Volume`
  - **Trap:** four playing voices fade four times as fast as one.
  - At level 0, the replay stops. DMA stays on.
- `TRACK_END` on any voice ends the song. All `AUDxVOL` get 0, and DMA goes off.
  `:SongEnd`

### Voice

A voice holds its track, position, stream and count, the ticks to its next
event. It holds an instrument, note, period, envelope, arpeggio, vibrato and
portamento. `:Voice`

A track lists patterns, one track per voice. `:NextPosition`

Each tick, in this order: `:VoiceTick`

1. On the tick after a note, `AUDxLC` and `AUDxLEN` get the loop. This is a
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). `:QueueLoop`
   - A loop of 0 gets a [silent loop](../docs/paula-techniques.md#silent-loop).
     A negative loop keeps the whole sample looping.
   - A pulse or morph wave [loops](../docs/paula-techniques.md#short-wave-loops)
     from its buffer's start.
   - **Trap:** the loop start adds the loop in bytes. The length subtracts it in
     words.
2. The count drops by 1. At 0, the stream reads on. `:CountDown`
3. With 1 tick left, DMA goes off. This gap restarts the next note. `:CountDown`
   - A wait of up to 96 rows keeps DMA on. A wait after a note ties the note.
   - **Trap:** notes below 32 keep DMA on. Their sample waits for the old loop's
     end.
   - **Trap:** `PATTERN_END` turns DMA off. A tie never crosses a pattern end.
   - **Trap:** at speed 1, a one-row note never has 1 tick left. It gets no gap.
4. Effects run only while Paula reports the channel's DMA on. `:Arpeggio`
   - **Trap:** a gap or a rest freezes the envelope, arpeggio, vibrato and
     sweep.

The stream reads commands until a note, a wait, `REST` or `PATTERN_END`.
Commands take no time. `:ReadStream`

- A note lasts one row. A wait byte adds 1 to 123 rows.
- `INSTRUMENT` picks the instrument. `:SetInstrument`
- `PORTAMENTO` sets the length, target note and delay of the next portamento.
  `:SetPortamento`
  - **Trap:** the target uses the current instrument's tune, even before
    `INSTRUMENT`.
- `REST` turns DMA off for one row. `:Rest`
- `PATTERN_END` reads the track's next word at once. `TRACK_JUMP` there jumps
  within the track. `:NextPosition`

A note start: `:NoteOn`

1. Arpeggio and vibrato restart. The envelope restarts in attack, at volume 0.
2. A pulse or morph wave restarts after `INSTRUMENT`. Otherwise `PULSE_RESTART`
   or `MORPH_RESTART` decides. `:PulseInit` `:MorphInit`
   - **Trap:** `INSTRUMENT` restarts the sweep, even for the same instrument.
3. `AUDxLC` and `AUDxLEN` get the sample, or the voice's buffer. `AUDxVOL`
   gets 0.
4. `AUDxPER` gets the note's period, times the instrument's tune / 1024.
5. A new portamento starts from this note's period, towards the target.
6. DMA goes on, unless `VoiceMask` masks the voice. Effects run in this tick.
   `:StartDma`
   - A masked voice still writes the registers above. Its gap still turns DMA
     off.

Effects, each tick with DMA on: `:Arpeggio`

1. The note plus the arpeggio offset gives the period. The offset steps every N
   ticks.
2. After its delay, portamento adds step × distance / length. `:Portamento`
   - **Trap:** it adds on top of the arpeggio. At its end, the note becomes the
     target.
   - **Trap:** it runs on across later notes. Only its first note sets start and
     distance.
   - A portamento of length 0 divides by zero.
3. After its delay, vibrato adds a triangle offset. `AUDxPER` gets the result.
   `:Vibrato`
   - The offset is in period units. Low notes get a smaller interval.
   - The offset must hit the depth exactly. Otherwise it runs past and wraps.
4. The envelope runs attack, decay, sustain for N ticks, and release.
   `:Envelope`
5. `AUDxVOL` gets volume × the instrument's level × the fade level, scaled.
   `:Volume`
6. A pulse or morph instrument steps its wave. `:Synth`

A voice falls silent by `REST`, a one-shot sample's silent loop, or a release
to 0. A higher release level sounds until the next note. `:Release`

### Wave buffer

Each voice owns a 64-byte buffer, a pulse state and a morph state. The pulse's
edge is its position between low and high bytes. `:Voice`

The pulse: `:Pulse`

1. A restart writes low bytes up to the edge's start, then high bytes.
   `:PulseInit`
   - An edge start of 0, or a wave over 64 bytes, writes past the buffer.
2. After its delay, it steps every N ticks.
3. A step writes a low byte at the edge going up, a high byte going down.
   `:PulseUp`
4. Past either limit, it turns. With `PULSE_COUNTED`, it stops after N turns.

The morph: `:Morph`

1. A restart copies the source's 32 bytes into the buffer. `:MorphInit`
2. After its delay, the step moves by 1 every tick, from 1 to 2^shift and back.
   `:MorphStep`
3. Each step sets 32 bytes to source + step × delta >> shift. `:MorphWrite`
   - The deltas are signed words. The sum wraps at a byte, with no clipping.
4. At each end, it turns. With `MORPH_COUNTED`, it stops after N turns.

## Open questions

- Is the missing gap before notes below 32 intended? (guess: a wrong branch)
- Is `fred.title` cut short? Its one sample runs 138 bytes past the file's end.
