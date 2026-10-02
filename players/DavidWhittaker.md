---
player: DavidWhittaker
template: 3
ideas:
  [
    replay-in-module,
    fractional-tempo,
    register-shadow,
    effects-steal-voices,
    bit-pattern-effects,
    pitch-list,
    volume-list,
    sample-rate-tune,
  ]
---

# David Whittaker

A drop rate skips a share of the music's ticks. Game sound effects borrow a
channel, and the music plays on in a shadow.

## Unique ideas

- The module is the replay, with its entry points first. `:InitSong`
- Each tick adds the drop rate, `Tempo`, to a byte sum. A carry drops the
  music's tick. `:Play`
  - Xenon 2 drops 20 of every 256 ticks. Lengths get uneven by one tick.
- Music writes each channel register to its shadow. When a sound effect ends,
  the shadow goes to Paula, and the music's note sounds on. `:Shadow`
  - Limits: a sound effect start busy-waits two or three times. `:DmaWait`
- A synth sound effect rotates two 8-bit patterns. Their bits pick one of two
  period steps and one of two wave starts. `:SynthEffect`
  - It makes warbles, trills and tone-noise rhythms from 24 bytes (inference).
- Each note restarts its volume list. The pitch list runs on, so a fast arpeggio
  keeps its phase across short notes. `:NoteOn`
  - Limits: the pitch list steps every tick. Its speed is fixed.
- A sample's tune, the NTSC clock / its recording rate, scales its periods.
  `:InitSamples` See [Rob Hubbard](RobHubbard.md).

## How it plays

The replay installs no interrupt. The host runs the tick, e.g. from its VBL
(guess). `:Play` The game calls entry points to start and end sound effects.

### Player

The player holds `Speed`, the ticks per length unit. It also holds the drop sum,
the master volume, the fade and the global transpose. `:Module`

1. With `Ntsc` set, every sixth tick is dropped, with its sound effects. A 60 Hz
   host then plays at 50 Hz speed. `:Play`
2. On a drop rate carry, only the sound effects run.
3. A fade lowers the master volume every N ticks. The game's fade uses N = 3,
   and `FADE` sets N. `:Fade`
4. Voices 0 to 3 run their ticks, then each active sound effect. `:VoiceTick`

- **Trap:** a fade's end or `SONG_END` sets DMA off on all channels. It stops
  every sound effect, too. `:SongEnd`

### Voice

A voice holds a position list of pattern offsets and its pattern position. It
holds a countdown, note, voice transpose, sample, length, both lists, slide and
vibrato. `:Voice` An event is a note, `REST` or `HOLD_NOTE`, one length long.

Each tick, in this order: `:VoiceTick`

1. A tick after a note start, `AUDxLC` and `AUDxLEN` get the loop. Without one,
   they get a [silent loop](../docs/paula-techniques.md#silent-loop).
2. The countdown drops. At 0, the voice reads its next event. `:CountDown`
3. At 1, DMA goes off, unless the next byte is `HOLD_NOTE`. Every note ends in a
   one-tick gap, a
   [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait) (guess).
   `HOLD_NOTE` only restarts the countdown.
   - **Trap:** a length byte before `HOLD_NOTE` restarts the held note from its
     loop.
   - **Trap:** a one-tick note gets no gap. The next sample waits for the old
     loop's end.
4. On other ticks, `AUDxPER` and `AUDxVOL` get new values. `:Effects`

The period is the table entry for note, transposes and pitch list value. The
tune scales it, then `SLIDE` and vibrato add. `:Effects`

- A pitch list value with `LIST_END` is used, then the list restarts.
- `SLIDE` waits its delay, then subtracts a growing sum. Each event ends it.
- Vibrato is a triangle in periods. It must hit its depth exactly, or it wraps.
  `:Vibrato`
- The volume list sets `AUDxVOL` every N + 1 ticks, × the master volume / 64. A
  value with `HOLD` stays. `:VolumeList`

At an event, the voice reads bytes until an event or `SONG_END`. `:ReadCommand`

| First byte          | The byte sets                             |
| ------------------- | ----------------------------------------- |
| 0                   | A note, for the current length            |
| `NEXT_PATTERN`      | A command                                 |
| `FIRST_PITCH_LIST`  | One of 16 pitch lists, restarted at once  |
| `FIRST_VOLUME_LIST` | One of 16 volume lists, for the next note |
| `FIRST_SAMPLE`      | The sample, one of 20                     |
| `FIRST_LENGTH`      | The length, 1 to 32 units of `Speed`      |

- `NEXT_PATTERN` reads the position list, and a 0 entry wraps. `POSITIONS` swaps
  the list. `:NextPattern`
- **Trap:** `TRANSPOSE` shifts all voices. The others shift mid-note.
  `:SetTranspose`
- **Trap:** `SPEED` sets `Speed` for all voices, from each one's next length
  byte. `:SetSpeed`

A note start writes all four registers: the whole sample, its period and the
first volume. DMA goes on. `:NoteOn`

A voice falls silent at `REST`: the silent loop, with DMA off from the gap.
`:Rest` A one-shot sample also ends on its silent loop.

### Shadow

A shadow holds start, length, period and volume. Its flags say "music ran" and
"a sound effect owns the channel". `:Shadow`

- Music writes reach Paula only on a channel without a sound effect. There, the
  gap also leaves DMA on.
- A sound effect's end turns DMA off and busy-waits. All four registers get the
  shadow, then DMA on. `:EndEffect`
  - **Trap:** the shadow holds the last sample write, the loop. A one-shot note
    comes back silent.

### Sound effect

Each channel holds one sound effect, with a duration and a volume list.
`:Effect` Sound effects ignore the master volume.

- The game's request names a channel and a sound effect, negative for a sample.
  A new request replaces the old one. `:StartEffect`
- At the duration's end, or after `EndEffects`, the sound effect ends.
  `:EffectTick`

A synth sound effect copies a 24-byte record. Each tick: `:SynthEffect`

1. Every N ticks, the step pattern rotates. Its bit 0 picks a period step.
2. A fixed step adds to the period. Every M ticks, the period resets.
3. The volume list sets `AUDxVOL`. A 0 ends the sound effect. `:EffectVolume`
4. `AUDxPER` gets the period, at least `MIN_PERIOD`. The offset pattern picks
   `AUDxLC` in the effect wave. `:EffectOutput`
   - `AUDxLC` sounds only at the next reload. A long wave skips pattern bits.

A sample sound effect plays at its recorded rate and volume 64, then its loop.
It ends after one pass, or when its slide drops below `MIN_PERIOD`.
`:SampleEffect`

## Open questions

- Where does the game load the effect wave and samples? Both start where
  `dw.ingame` ends.
- Ports rewrite a pulse wave in some versions (guess). Which modules use it?
- Did Rob Hubbard and David Whittaker share this core? See
  [the shared driver](../docs/shared-driver.md).
