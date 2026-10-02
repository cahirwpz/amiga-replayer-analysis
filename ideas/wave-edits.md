# Live wave edits

The CPU rewrites the bytes of a waveform while a note plays it. One short wave
then changes its timbre at a small cost per tick. See
[live wave edits](../docs/paula-techniques.md#live-wave-edits).

## Wave effects

An instrument names one effect. Every few ticks, the effect rewrites the bytes
of the playing waveform.

- [SoundMon 2.2](../players/SoundMon2.2.md): an instrument or a note command
  picks the effect. It smooths, morphs or copies the first 32 bytes.
  `specs/soundmon_22.py:WaveEffect`
- [Mugician II](../players/MugicianII.md): the instrument picks one of 15
  handlers. Every N ticks, it smooths, shifts, negates or blends the 128-byte
  wave. `specs/mugician_ii.py:RunEffect`
- [Sonic Arranger](../players/SonicArranger.md): one of 17 effects rewrites a
  byte range every N ticks. `specs/sonic_arranger.py:WaveEffect`
- [Fred](../players/Fred.md): a morph instrument rewrites 32 bytes every tick.
  Each byte is a source byte plus the step count times its delta.
  `specs/fred.py:MorphStep`

## Partial wave inversion

A value N flips the sign of a wave's first N bytes. Sweeping N moves the edge
between flipped and plain bytes. On any wave, this sounds like a pulse-width
sweep (inference).

- [SoundMon 2.2](../players/SoundMon2.2.md): the `EG` walker steps through a
  table. Each step sets N, from 0 to 31. `specs/soundmon_22.py:EgWalker`

## One-byte sweeps

A wave holds low bytes before an edge and high bytes after it. Each step
rewrites the byte at the edge and moves the edge one byte. The pulse width
changes.

- [Fred](../players/Fred.md): the wave holds up to 64 bytes.
  `specs/fred.py:Pulse`
- [Rob Hubbard](../players/RobHubbard.md): the edge moves once per tick.
  `specs/rob_hubbard.py:Sweep`

## Wave copy per voice

A note copies its wave into a buffer of its voice. Other voices on the same wave
do not hear its edits.

- [Sonic Arranger](../players/SonicArranger.md): the copy lives in the voice's
  record, in chip memory. `specs/sonic_arranger.py:StartSynthWave`

## Effect chain

Several effects run in a fixed order every tick. Each one reads the buffer the
one before it wrote.

- [Musicline Editor](../players/MusiclineEditor.md): transform, phase, mix,
  resonance and filter run in this order. The channel plays the last effect's
  buffer. `specs/musicline.py:PlayEffects`

## Morph by program

An instrument program, not an instrument setting, starts a morph.

- [Jason Page](../players/JasonPage.md): an opcode copies a wave, or morphs it
  one step per byte towards another. `specs/jason_page.py:OpMorph`

## Wave sweeps

A sweep moves an effect's setting. The effect rebuilds the wave from it.

- [SoundFactory](../players/SoundFactory.md): phasing and a low-pass filter
  rebuild a short wave into a buffer per voice. Each setting sweeps between two
  limits. `specs/sound_factory.py:WaveEffects`

## Shared sweeps

One kind of sweep drives every effect of a chain.

- [Musicline Editor](../players/MusiclineEditor.md): each effect owns a sweep of
  the same type. `specs/musicline.py:Counter`

## Sweep between limits

A sweep turns only at its limits. A start outside them makes it run in first.

- [AHX](../players/AbyssHighestExperience.md): pulse width and filter position
  sweep this way. A sweep turns at the second limit it meets.
  `specs/abyss_highest_experience.py:Sweep`

## Bit pattern effects

Rotating bit patterns pick the next change. A few bytes give a rhythm of edits.

- [David Whittaker](../players/DavidWhittaker.md): two 8-bit patterns rotate.
  Their bits pick one of two period steps and one of two wave starts.
  `specs/david_whittaker.py:SynthEffect`

## Double-buffered waves

The CPU fills one half of a buffer while Paula plays the other half.

- [Voodoo Supreme Synthesizer](../players/VoodooSupremeSynthesizer.md): each
  tick fills one 32-byte half from two samples. Paula plays the half filled one
  tick before. `specs/voodoo_supreme_synthesizer.py:SetHardware`

## Seamless wave notes

A new note on the same wave keeps DMA on. The wave plays on at the new pitch,
without a click (inference).

- [Musicline Editor](../players/MusiclineEditor.md): the replay skips the DMA
  restart. `specs/musicline.py:DmaPlay`

## Compared

- Sonic Arranger edits build on each other until the next note. Musicline Editor
  starts each tick from the plain wave.
- Fred and Sonic Arranger edit a copy per voice. On SoundMon 2.2 and Mugician
  II, voices that play one wave hear each other's edits.
