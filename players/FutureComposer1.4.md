---
player: FutureComposer1.4
template: 3
ideas: [pitch-list, volume-list, sample-pack, instrument-transpose]
---

# Future Composer 1.4

Each instrument runs a volume list and a pitch list. The pitch list also picks
the waveform and starts the sound.

## Unique ideas

- The pitch list (`FREQseq`) sets waveforms, transposes, pitch slides and
  vibrato. It steps every tick. `:ReadPitchList`
  - Limits: at most one command and one transpose per tick.
- A pattern note only turns DMA off. The pitch list's wave command starts the
  sound. `:StartInstrument` `:SetWave`
  - Limits: a pitch list that sets no wave leaves the note silent.
- The volume list steps every N ticks, with waits, loops and volume slides.
  `:VolumeListTick`
  - Limits: it holds at most 59 bytes per instrument.
- A pitch list byte with the `LOCKED` bit is a fixed note, e.g. for drums.
  `:LockedNote`
  - Limits: a fixed note ignores the row's note and all transposes.
- `PACK` picks one sample out of a sample pack of up to 20. `:SampleFromPack`
  - Limits: the pack needs its own header.
- Each position transposes notes and instrument numbers, per voice.
  `:AddInstrTranspose`
  - Limits: a position takes 13 bytes.
- Vibrato doubles its period offset for each octave down. Its width in semitones
  stays about the same. `:VibratoTick`

## How it plays

The host calls the tick once per frame. Init turns the audio interrupts off.
`:Play` `:InitMusic`

Every `speed` ticks, each voice reads a row. Next, each voice runs its lists and
writes its registers. DMA on and the loop writes come last.

### Player

The player holds the tick counter, `speed` and a count of pattern ends.
`:Module`

- A voice reads its next position after 32 rows, or at the note `PATTERN_END`.
  Each voice steps on its own. `:NextPosition`
  - A position holds a pattern, a transpose and an instrument transpose per
    voice. It also holds a speed. `:Position`
  - After the last position, the voice goes on at position 0.
- Every fourth pattern end, counted over all voices, reads the next position's
  speed. `:ReadSpeed`
  - **Trap:** the count is global. With equal patterns, voice 0 reads every
    speed, except position 1's.
  - **Trap:** another voice reads the byte 3 × its number further on.

### Voice

A voice holds its note, both position transposes, its volume and both lists. It
holds the vibrato, the portamento speed and two slides. `:Voice`

The slide is one period offset. Portamento and the pitch slide both add to it.

A row holds a note and an info byte: the instrument and two portamento bits.
`:ReadNote`

1. A note clears the slide. A note or a portamento bit clears the portamento.
2. Bit 7 takes the portamento speed from the next row's info byte. `:SlideSpeed`
   - **Trap:** that byte is also the next row's instrument. A note or a
     portamento bit there ends the portamento.
   - On the last row, the speed comes from the next pattern in memory.
3. A note turns DMA off. The instrument number gets the instrument transpose.
   `:StartInstrument` `:AddInstrTranspose`
4. The instrument's header sets the volume list's speed, the pitch list and the
   vibrato. Both lists and the vibrato restart.
   - **Trap:** both slides and the last transpose run on. A pitch slide from the
     old note bends the new one.
   - **Trap:** a running volume slide holds back the new volume list.
     `:VolumeListTick`

Each tick, in this order: `:VoiceTick`

1. The pitch list steps, then the volume list.
2. The note, both transposes and the pitch list's transpose pick a period.
   `:CalcPeriod`
   - Note indices 48 to 59 give the highest period. Indices 60 to 83 sound lower
     than index 0.
3. After its delay, vibrato adds a triangle offset. It starts at the centre.
   `:VibratoTick`
   - Index 84 plays index 0's period with 1/16 of its vibrato (estimate).
4. Every second tick, portamento moves the slide. Up to `PORTA_UP_MAX`, it
   slides up. `:DoSlide`
   - Portamento has no target note. It stops at a note or a portamento bit.
5. Every second tick, the pitch slide adds its signed step to the slide.
   `:PitchBend`
   - **Trap:** the slide adds to the pitch list's transposes. Only a note clears
     it.
6. `AUDxPER` gets the period plus the slide, clamped. `AUDxVOL` gets the volume.
   `:ClampPeriod`

DMA goes on for each voice that set a wave this tick. At the next tick, `AUDxLC`
and `AUDxLEN` get its loop, by
[loop by reload](../docs/paula-techniques.md#loop-by-reload). `:WriteLoops`

There is no note-off. A voice falls silent when its volume list reaches 0.

### Pitch list

A pitch list holds 64 bytes. Its state is a position, a wait and the last
transpose. `:PitchList`

Unless it waits, a step runs a command, if any, and reads a transpose.
`:ReadPitchList` `:ReadTranspose`

- `SET_WAVE` turns DMA off and marks the voice for DMA on. `AUDxLC` and
  `AUDxLEN` get the whole wave. `:SetWave`
  - The volume list restarts.
- `PACK` does the same with a pack's entry. `:SampleFromPack`
  - Without the pack's magic, DMA restarts from the old `AUDxLC`.
- `CHANGE_WAVE` writes `AUDxLC` and `AUDxLEN` with DMA on. The volume list runs
  on. `:ChangeWave`
  - **Trap:** the next tick writes the loop. If the old loop lasts longer, the
    new wave's head never plays.
- `BEND` sets the pitch slide. `SET_VIBRATO` sets the vibrato's speed and depth.
- `WAIT` waits N ticks, this one included. `JUMP` reads another pitch list at
  once. `:PitchWait` `:PitchListJump`
- `LIST_LOOP` loops, e.g. for an arpeggio. `LIST_END` stops the list.
  - **Trap:** a loop target is not checked for `LIST_LOOP` or `LIST_END`.

### Volume list

Its state is a position, a speed, a counter and a wait. The volume slide holds a
step, a time and a phase. `:VolumeList` `:Bend`

Each tick, a wait or a running volume slide steps first. Otherwise, a step runs
every `speed` ticks. `:ReadVolume`

- A plain byte sets the volume. `WAIT` waits N ticks.
- `BEND` moves the volume every second tick. Past 127, the volume drops to 0.
  `:VolumeBend`
- `LIST_LOOP`'s target counts from the instrument's start. `:VolumeLoop`

## Open questions

- Only the tick's own work separates DMA off and on. Does a low note miss its
  [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait) (guess)?
