---
player: VoodooSupremeSynthesizer
template: 3
ideas:
  [
    voice-streams,
    chunk-pitch-shift,
    double-buffered-waves,
    volume-list,
    pitch-list,
  ]
---

# Voodoo Supreme Synthesizer

Each audio interrupt plays the next 128-byte chunk of a long sample. Other modes
rebuild a 32-byte wave from two samples every tick.

## Unique ideas

- In chunk mode, each audio interrupt queues the next chunk. It then moves a
  pointer by a step. `:NextChunk`
  - The step can be 128 × period ÷ the base note's period. Then the sample moves
    at the base note's speed at every pitch. `:ChunkStep`
  - A table can move the pointer to any place in the sample. `:ChunkTable`
  - CPU: one audio interrupt per chunk and voice.
- The other modes fill one half of a 2 × 32-byte buffer every tick from two
  samples. Paula plays the half filled one tick before. `:SetHardware`
  - Three modes combine the samples: average, exclusive-or and morph.
- Each voice reads its own byte stream. Calls and loops share one small stack
  per voice. `:CmdCall` `:CmdLoopStart` `:CmdLoop`
  - Limits: the stack holds 20 entries, 80 bytes. Nothing checks for overflow.
- An interval multiplies the period by a small fraction, e.g. 107/101 for a
  semitone. `:Interval`

## How it plays

A vertical blank server runs the tick. `:TickServer` In chunk mode, each
channel's audio interrupt runs `:NextChunk` for its voice.

A tick runs voices 0 to 3. `:Tick` `:VoiceTick`

### Player

The player holds the subsong's base address and a goto count. `:Module`

- At the start, each voice plays an empty sample of 16 words at volume 0.
  `:InitVoices`
- DMA never goes off. Silence is
  [volume 0](../docs/paula-techniques.md#silence-by-volume) or the empty sample.
- `:CmdGoto` shifts a bit into the goto count. At `ALL_LOOPED` after a tick, the
  host gets the song end, and play goes on. `:Tick`
  - **Trap:** the count needs exactly four gotos in one tick. Voices whose gotos
    fall on different ticks never end the song.

### Voice

A voice holds its stream, return stack, note ticks, transpose, period and
volume. It holds two samples, a mode and a mask. `:Voice`

When its note ticks run out, the voice reads its stream: `:ReadStream`

1. A byte with bit 7 clear is a note, followed by a tick count. Its period comes
   from the note + the transpose. `:NotePeriod`
   - The lowest B's period is `$4519`, not `$4280`. It plays about 66 cents
     flat.
2. The note restarts each table walker, unless its keep flag is set.
   `:CmdKeepFlags`
   - **Trap:** a note never restarts DMA or the buffer. In exclusive-or and
     morph mode, a note starts from the last note's wave.
3. Other bytes are commands. `:Command`
   - `NOTE_CUT` sets the volume to 0 at once, not one tick late. `:NoteCut`
   - **Trap:** `NOTE_CUT` also stops the volume walker, for 255 ticks. With its
     keep flag, notes in those ticks stay silent.
   - `:CmdPortamento` acts as a note. Its tick count is also the slide's length.
   - **Trap:** a return inside an open loop pops the loop count as an address.
     `:CmdReturn`

Each tick, DMA goes on. `AUDxPER` and `AUDxVOL` get last tick's period and
volume, before the mode's routine runs. `:SetHardware`

### Table walkers

Each voice runs a volume, a period and a wave table walker. Each entry holds a
value and a tick count. `:Voice`

1. A volume entry sets a level, or adds a delta every tick for N ticks.
   `:VolumeEnvelope` `:VolumeLevel`
   - **Trap:** the volume wraps from 0 to 255. Nothing clamps it.
2. A period entry adds to the period, subtracts from it, or shifts it by an
   octave. It runs every tick of its entry, except an interval, which runs once.
   `:PeriodTable` `:PeriodCommand`
   - **Trap:** an octave entry of 3 ticks shifts three octaves.
3. A slide moves the period by its step every `porta_delay` ticks. `:Portamento`
   - **Trap:** the slide, the period walker and the note all change one period.
     A period entry adds on top of a slide.
   - **Trap:** a step of 127 or more reads as a period decrease. A fast slide
     down in pitch then goes up.
   - **Trap:** a slide of N period units over at most N ticks stops one step
     short.
   - Limits: a slide between equal notes divides by zero. `:CmdPortamento`

- **Trap:** an interval up rounds down, and an interval down rounds up. From
  period 428, a semitone up and back down gives 427. `:Interval`

### Buffer

The wave walker's table sets the mode. In the wave modes, each voice owns a 2 ×
32-byte buffer. Each tick: `:Voice`

1. `AUDxLC` gets the half filled last tick. Paula takes it at its next reload.
2. The other half gets the new wave.
   - **Trap:** the other half is the one queued last tick. With a pass shorter
     than a tick, Paula plays it during the fill.

- Average mode averages sample 1 and sample 2. Sample 2's phase moves each tick,
  which gives phasing (inference). `:MixWaves`
- It sets the mask's bits in each byte's magnitude. This distorts but keeps the
  sign (inference).
- Exclusive-or mode copies the playing half. Inside a moving window, it flips
  the bits that sample 2 and the mask set. `:XorWaves`
  - **Trap:** it reads the playing half, not the samples. Its changes add up,
    tick by tick. A second pass over the same bytes undoes them.
- Morph mode copies the playing half. Inside the window, each byte moves towards
  sample 1 or sample 2. `:MorphWave`
- A table command can copy sample 1 instead. It resets the wave. `:CopyWave`

### Chunks

In chunk mode, Paula plays sample 2 in chunks of 64 words. `:CmdWaveTable`

- A chunk table entry moves the pointer to an offset in sample 2. `:ChunkTable`
- Each tick sets the step: 128 bytes, or one that follows the period.
  `:ChunkStep`
- Past the end of sample 2, Paula plays the empty sample, until a chunk table
  entry.
- **Trap:** chunk mode sets `AUDxLEN` at once, and the pointer at the next audio
  interrupt. One 64-word pass reads from the buffer on.
- **Trap:** a step under 128 lets the last chunk read up to 127 bytes too far.
  `:NextChunk`
- **Trap:** sample 1 and the chunk pointer share one field. After chunk mode, a
  wave mode reads sample 1 where the chunks stopped. `:Voice`
- **Trap:** the mask also holds the base note. A mask set for a wave mode
  changes the chunk step. `:CmdMask`

## Open questions

- Which modules use chunk mode with the step that follows the period?
- Past the sample's end, with no table entry, the pointer moves on from the
  empty sample. Does it then play the player's memory? `:NextChunk`
- Does the lowest octave ever play? On a 32-byte wave, its notes are below 7 Hz.
