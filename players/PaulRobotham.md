---
player: PaulRobotham
template: 3
ideas:
  [
    per-voice-streams,
    packed-lengths,
    length-remainder,
    period-scaled-vibrato,
    effect-voice-limit,
  ]
---

# Paul Robotham

Each voice reads its own note stream, with lengths in pulses. There are no
patterns.

## Unique ideas

- Each voice reads one byte stream. Loops nest on a stack. `:LoopEnd`
  - Limits: a part that two voices play is stored twice.
  - Limits: no command jumps back for good. A loop count of 0 plays 65 536
    passes.
- A length byte holds a 5-bit value and a 3-bit shift, for 1 to 3968 pulses.
  `:ReadLength`
  - Limits: a length with more than five significant bits needs a tie.
- The pulse length scales pulses to ticks. Each voice keeps the remainder of
  that division for its next length. `:ReadLength`
  - Voices never drift apart, at any tempo.
- Vibrato adds a share of the period. Its interval is the same on every note.
  `:Vibrato`
- A legato note after an instrument change starts the new instrument at its
  loop. The attack part is skipped. `:SwapInstrument`
- A sound effect takes a music voice. Its stream runs on, muted. `:MutedVoice`
  - The music comes back in time, at the voice's next note start.
  - Limits: the effect start is commented out. UADE plays no effects.
    `:StartEffect`

## How it plays

The host's tick calls the replay. There is no audio interrupt. `:Play`

A tick runs each voice, then the master fade. A voice with an effect runs its
stream muted, then the effect. `:Play`

### Player

The player holds the pulse length, the master volume and its fade. It also holds
the voice mask and the effect voice count. `:Module`

- The pulse length is in 1/10800 tick. A command sets it to its argument × 16.
  `:SetPulseLength`
  - **Trap:** one voice's command sets the tempo of all voices. Voices before it
    in this tick already read their lengths at the old tempo.
  - A song restart keeps the last pulse length. `:InitSong`
- A master fade moves the master volume by 1 every N ticks, to a target.
  `:FadeMaster`
  - **Trap:** one command in any stream fades the whole song. `:MasterFade`
- A clear bit in the voice mask mutes its voice. `:StartDma`
- `EffectVoices` limits effects to voices 0 to N. `:EffectVoices`
- Two commands switch the audio filter. `:FilterOn` `:FilterOff`

### Voice

A voice holds its stream position, loop stack and timer, the ticks to its next
byte. It holds the remainder, instrument, volume, tables, portamento, vibrato
and fade. `:Voice`

Its flags come from `SetMode`: legato, keep the envelope, keep the vibrato
phase. Its volume-on bit allows `AUDxVOL` writes. `:SetMode`

Each tick, in this order: `:StepVoice`

1. The vibrato phase moves by the vibrato speed. The envelope index moves by 4
   bytes.
2. At timer 0, the stream reads on. Otherwise, the pending DMA step runs.
   `:StartDma`
3. Portamento moves the period towards the target by its step. `:Portamento`
4. `AUDxPER` gets the period + period × vibrato value / (10000 / depth).
   `:Vibrato`
5. The timer counts down. A length of 0 ticks lasts 65 536 ticks.
   - The first byte waits 10 ticks. `:InitSong`
6. With the volume-on bit set, `AUDxVOL` gets envelope × volume / 63. The master
   volume scales it. `:EnvelopeTick`

The stream reads commands, which take no time, up to a note, `TIE` or
`END_BYTE`.

- A note byte, 1 to 126, takes a length byte. Notes above 59 read past the
  periods.
- `TIE` and its length hold the note on. It restarts nothing. `:ReadLength`
- No command plays an arpeggio. It is written out as notes.
- An unused command number flashes the screen. `:BadCommand`
- `END_BYTE` turns DMA off for good. `:VoiceEnd`

A note start, with the legato flag clear: `:NoteOn`

1. DMA goes off, and the volume-on bit clears. The fade ends.
2. `AUDxLC` and `AUDxLEN` get the whole sample. `AUDxPER` gets the note's
   period.
3. The length sets the timer. The vibrato phase and the envelope restart, unless
   their flags keep them. `:ReadLength`
4. The next tick, DMA goes on, and the volume-on bit sets. `:StartDma`
   - **Trap:** the note's own tick skips this step. A one-tick note before
     another note never turns DMA on.
5. The tick after, `AUDxLC` and `AUDxLEN` get the loop, as a
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). A sample
   without a loop gets a [silent loop](../docs/paula-techniques.md#silent-loop).

- With portamento on, the pitch slides from the last period. `:Portamento`

With the legato flag set:

- A note changes only the target period. The sample plays on. `:LegatoNote`
  - **Trap:** a legato note does not end a fade.
- `SetInstrument` clears the legato flag and marks the change. `:SetInstrument`
  - **Trap:** an instrument swap needs `SetMode` again, after `SetInstrument`.
- After a change, a legato note gets `AUDxVOL` 0 and DMA off. `AUDxLC` and
  `AUDxLEN` get the loop. `:SwapInstrument`
  - Without a loop, it plays the silent loop at `EMPTY_PERIOD`.

There is no rest byte. A voice falls silent through its envelope, volume 0, its
fade or the silent loop.

The envelope index starts at byte 3 and wraps at 256. A table has 64 steps.
`:EnvelopeTick`

- A negative byte jumps back by its size, rounded up to 4 bytes.
- An envelope with no jump repeats every 64 ticks.
- `FadeOut` starts a release. The fade level replaces the volume and falls by
  the fade step each tick. `:FadeOut` `:FadeStep`

### Sound effect

Each voice has an effect slot: sample, loop, period, ticks left and volume.
`:Effect`

1. The start call takes, of voices 0 to N, the one with the fewest ticks left. A
   later voice wins a tie. `:StartEffect`
   - Its ticks are about the sample's play time at 50 Hz.
   - **Trap:** a looping effect counts down from −1. A new effect replaces it
     before taking a free voice.
2. First tick: DMA goes off. `AUDxLC` and `AUDxLEN` get the sample.
   `:EffectTick`
3. Second tick: `AUDxVOL` gets 0, and DMA goes on.
4. Third tick: `AUDxLC` and `AUDxLEN` get the loop. `AUDxVOL` gets the effect's
   volume.
5. At 0 ticks left, DMA goes off and `AUDxVOL` gets 0.
   - **Trap:** DMA comes back only at a note start or an instrument swap. A
     legato note stays silent.

- **Trap:** a swap in the muted stream turns DMA off. It cuts the effect.
  `:SwapInstrument`
- The original also wrote `AUDxPER`. The adaptation does not. `:EffectTick`
- The effect voice count keeps effects off key voices (guess).

## Open questions

- How many pulses make a quarter note? `:ReadLength`
- Did the game stop looping effects before starting new ones? `:StartEffect`
- Who writes the voice mask? This source never does. `:StartDma`
