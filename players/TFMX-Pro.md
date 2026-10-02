---
player: TFMX-Pro
template: 3
ideas:
  [
    instrument-programs,
    tracks-not-voices,
    self-modifying-programs,
    resampling-synthesis,
    random-offset-loops,
  ]
---

# TFMX Pro

An instrument is a program that runs once per tick and shapes one note.

## Unique ideas

- An instrument program, TFMX's `macro`, has 52 opcodes. They include waits,
  loops, one call and branches on note, volume and note-off. `:MacroStep`
  `:SplitByNote` `:WaitNoteOff`
- Eight tracks share four voices. Each note names its voice. `:NoteToVoice`
- A note restarts only the program. Effects, volume and sample carry over.
  `:NoteToVoice`
  - Limits: a program must clear old effects itself. `:ClearEffects`
- An offset loop, TFMX's `riff`, plays another program's bytes as note offsets.
  It can jump at random and echo on the next voice. `:RiffTick`
  - Limits: every offset plays for the same number of ticks.
- IMS rebuilds a voice's wave every tick, as a hard sync with a slew limiter.
  `:ImsTick`
  - Limits: CPU high. It rebuilds up to 256 bytes per voice per tick.
- Programs rewrite programs. `:CopyToMacro` `:AddToMacro`
  - Limits: every voice that plays the program hears the change.

## How it plays

A timer interrupt runs the replay, and a position command can set its rate.
`:SetSpeed` Audio interrupts only count sample passes. `:CountLoopIrq`

A tick runs every voice, then the tracks. Last, it writes all `AUDxPER` and
turns DMA on. `:PlayTick`

- **Trap:** voices run before the tracks. A note's program starts one tick after
  its row.

### Player

The player holds the position, `speed`, a tick counter and the fade. `:Module`

- A position holds a pattern and a transpose per track, or a command.
  `:SetTracks` `:PositionSpecials`
- A pattern end on any track moves all tracks to the next position.
  `:PatternEnd`
  - **Trap:** one track's pattern end cuts the other tracks' patterns short.
- A fade moves its level by 1 every N voice visits. `:FadeTick`
  - **Trap:** the counter moves four times per tick. Voices in one tick can get
    different levels.

### Track

A track holds its pattern, place, wait, transpose and one return. `:Track`

At each row, a track counts down its wait, or reads until a wait: `:ReadPattern`

1. A note gets the transpose and goes to the voice in its byte 2. `:TrackNote`
   - A note below `NOTE_WAIT` reads on. A chord is several notes on one track.
   - **Trap:** a note from `NOTE_WAIT` to `$bf` takes its wait from the detune
     byte. It plays without detune.
2. Pattern opcodes loop, jump, wait, stop or start another track. Others send
   note-off, vibrato or an envelope to a voice. `:PatternOpcode`
   - **Trap:** a return restores track 0's place. Calls work only on track 0.
     `:PatternReturn`

### Voice

A voice holds its program, key state, note, detune, note volume and volume. It
holds a base period, the period, the sample, and six effects. `:Voice`

- A sound effect locks the voice for a set number of ticks. Track notes to it
  are lost. `:PlaySoundEffect` `:NoteToVoice`
- A note sets the note, detune and note volume, and restarts the program.
  Effects skip one tick. `:NoteToVoice`
  - **Trap:** a note that starts the same program keeps its first-pass mark.
    `:SkipFirstPass`

Each tick, in this order: `:VoiceTick`

1. The lock counts down. A pending sound effect note plays.
2. The program runs, unless it waits or has stopped. `:RunMacro`
3. Unless paused: sweep, IMS, vibrato, portamento, envelope and offset loop.
   `:ModulationTick`
   - The sweep moves the sample start each tick. It turns every N ticks.
     `:SweepTick`
   - **Trap:** during portamento, vibrato writes nothing. Its phase moves on.
     `:VibratoTick`
4. `AUDxVOL` gets the volume, scaled by the fade. A locked voice is not scaled.
   `:FadeTick`

A DMA off opcode, the silence opcode or `TRACK_OFF` silences a voice. `:DmaOff`
`:SetSilence` `:StopVoice` A release to 0 leaves DMA on.

### Instrument program

A program is a list of 4-byte steps: an opcode and three argument bytes. Its
state is a place, a wait, a loop count, one return and a first-pass mark.
`:Macro`

- Steps run until a wait or a note opcode ends the tick. `:EndMacroTick`
  - **Trap:** during portamento, a note opcode sets only the target. `:PutNote`
- Each envelope opcode ramps to a target and stops. ADSR is attack, wait, decay,
  note-off wait and release steps. `:MacroEnvelope` `:WaitNoteOff`
- DMA on acts at the tick's end. A delayed DMA off acts at the next tick's
  start. `:DmaOn` `:DmaOff`
  - The program then reads past one wait. It restarts the sample in that tick.
    `:EndMacroTick`
- A program can wait for N + 1 passes of its sample, as
  [loop counting](../docs/paula-techniques.md#loop-counting). `:WaitLoops`
- A wait with bit 0 set waits for an offset byte with bit 7. Its first pass only
  arms it. `:MacroWait`

### Offset loop

An offset loop holds a source program, a step and ticks per step. Its flags are
random, echo and no rests. `:Riff`

Every N ticks, the next byte plus the note sets the period. `:RiffTick`

- A 0 byte restarts the loop. A byte for note 0 jumps to a random step.
- **Trap:** during portamento, a byte sets only the target. The loop stays on
  that step.
- With random, every fourth step drops its note about 1 time in 16. A byte with
  bit 6 jumps to a random step. `:RiffRandom`
- With echo, the next voice copies this voice at 3/8 of a step. It takes the
  period and 5/8 of the volume. `:RiffEcho`
  - **Trap:** the echo writes over the next voice, even during its portamento.

### IMS

IMS holds a source, a mask, a step, a step change and a delta. Swings change the
last three each tick. `:Ims` `:Swing`

- The channel loops the voice's buffer in the sample memory. `:ImsLength`
- Each tick, the buffer gets the source from its start, cut at the buffer's end.
  Its loop sounds as a hard sync. `:ImsTick`
- The step change bends the step across the buffer. The delta limits each byte's
  move from the last.
- A mirror writes a negated copy into the next voice's buffer. `:ImsOff`
- **Trap:** with IMS on, the sweep moves the source. A length opcode sets the
  mask. `:AddLength`
- **Trap:** Paula reads the buffer while the replay rewrites it. One loop can
  mix two ticks' waves (inference).

## Open questions

- The source calls the offset loop code the Ballblazer routine. Is it modelled
  on Ballblazer's music (guess)?
