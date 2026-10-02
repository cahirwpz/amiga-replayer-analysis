# Live wave edits

The CPU rewrites the bytes of a waveform while a note plays it. One short wave
then changes its timbre at a small cost per tick. See
[live wave edits](../docs/paula-techniques.md#live-wave-edits).

## Wave effects

An instrument names one effect. Every few ticks, the effect rewrites the bytes
of the playing waveform.

- [SoundMon 2.2](../players/SoundMon2.2.md): one effect per note edits the
  wave's first 32 bytes. It smooths, morphs or copies.
  `specs/soundmon_22.py:WaveEffect`
- [Mugician II](../players/MugicianII.md): 15 handlers smooth, shift, negate or
  blend the 128-byte wave every N ticks. `specs/mugician_ii.py:RunEffect`
- [Sonic Arranger](../players/SonicArranger.md): one of 17 effects rewrites a
  byte range every N ticks. `specs/sonic_arranger.py:WaveEffect`
- [Fred](../players/Fred.md): a morph instrument rewrites 32 bytes every tick.
  Each byte is a source byte plus the step times a delta.
  `specs/fred.py:MorphStep`

## Partial wave inversion

A value N inverts the first N bytes of a wave. Sweeping N sounds like a
pulse-width sweep, on any wave (inference).

- [SoundMon 2.2](../players/SoundMon2.2.md): the `EG` walker gives N, from 0 to
  31, at each of its steps. `specs/soundmon_22.py:EgWalker`

## One-byte sweeps

A wave holds low bytes below an edge and high bytes above it. Each step writes
one byte, so the edge moves and the pulse width changes.

- [Fred](../players/Fred.md): the edge moves by one byte per step. The wave
  holds up to 64 bytes. `specs/fred.py:Pulse`
- [Rob Hubbard](../players/RobHubbard.md): the edge moves by one byte per tick.
  `specs/rob_hubbard.py:Sweep`

## Wave copy per voice

A note copies its wave into a buffer of its voice. Edits then change only that
voice's sound.

- [Sonic Arranger](../players/SonicArranger.md): the copy lives in the voice's
  record, in chip memory. `specs/sonic_arranger.py:StartSynthWave`

## Effect chain

Several effects run in a fixed order every tick. Each one reads the buffer the
one before it wrote.

- [Musicline Editor](../players/MusiclineEditor.md): transform, phase, mix,
  resonance and filter run in this order. The channel plays the last buffer.
  `specs/musicline.py:PlayEffects`

## Morph by program

An instrument program, not an instrument setting, starts a morph.

- [Jason Page](../players/JasonPage.md): an opcode copies a wave, or morphs it
  one step per byte towards another. `specs/jason_page.py:OpMorph`

## Wave sweeps

A sweep moves an effect's setting, and the effect rebuilds the wave from it.

- [SoundFactory](../players/SoundFactory.md): phasing and a low-pass filter
  rebuild a short wave into a buffer per voice. Each sweeps its setting between
  two limits. `specs/sound_factory.py:WaveEffects`

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
with no restart.

- [Musicline Editor](../players/MusiclineEditor.md): the replay skips the DMA
  restart (inference: no click). `specs/musicline.py:DmaPlay`

## Compared

- Edits pile up until the next note on Sonic Arranger. Musicline Editor starts
  each tick from the plain wave.
- Fred and Sonic Arranger edit a copy per voice. On SoundMon 2.2 and Mugician
  II, voices that play one wave hear each other's edits.
