# Waves built ahead

These players make their waves by rule, not from stored samples. A rule costs
less memory than a sample. The replay can also change the wave as it plays.

## Generated waves

The replay computes its waves from formulas when it starts.

- [AHX](../players/AbyssHighestExperience.md): it builds 45 waves. They are
  triangles and saws in 6 lengths, 32 squares of rising pulse width, and noise.
  `specs/abyss_highest_experience.py:MakeWaves`

## Filter bank

The replay stores filtered copies of each wave in advance. A filter position
picks the copy that plays. A filter sweep then costs no filter work during play.

- [AHX](../players/AbyssHighestExperience.md): at start, each wave gets 31
  low-pass and 31 high-pass copies.
  `specs/abyss_highest_experience.py:MakeFilters`
- [Sonix Music Driver](../players/SonixMusicDriver.md): at load, each synth wave
  gets 64 low-pass copies. The bank costs 8 kB per synth instrument.
  `specs/sonix_music_driver.py:SetFilter`

## Subtractive synth

A subtractive synth shapes a rich wave with a moving filter. A filter position
that changes over time gives a filter bank this sound.

- [Sonix Music Driver](../players/SonixMusicDriver.md): each tick, the envelope
  and the LFO set the filter position.
  `specs/sonix_music_driver.py:SelectFilter`

## Free-running buffer

A voice plays one buffer that loops forever. The replay changes the sound by
rewriting the buffer, never by a DMA restart.

- [AHX](../players/AbyssHighestExperience.md): each voice loops a 640-byte
  buffer. Copies of a new wave fill the whole buffer.
  `specs/abyss_highest_experience.py:FillBuffer`

## Wavetable scan

One long sample holds a row of equal parts. The loop moves from part to part.
The timbre then changes over time.

- [Art Of Noise 8V](../players/ArtOfNoise-8V.md): every N ticks, the loop start
  moves one part on. `specs/art_of_noise_8v.py:SynthTick`

## Length-tuned waves

Waves of different lengths play at the same pitch. The period depends on the
wave's length. It also depends on how many cycles the wave holds.

- [SoundFactory](../players/SoundFactory.md): the note's period is divided by
  the wave's length. It is multiplied by the wave's cycles.
  `specs/sound_factory.py:NotePeriod`

## Pulse width table

A table, not a sweep, sets the pulse width over time.

- [Synth Dream](../players/SynthDream.md): a table value sets the pulse width,
  in sixteenths of the wave. The replay rebuilds the wave every tick.
  `specs/synth_dream.py:PulseWalker`

## Soft-edge pulse

One byte at the edge of a pulse wave takes a middle value. The pulse width can
then sit between two whole bytes.

- [Synth Dream](../players/SynthDream.md): the table value's second byte is
  subtracted from the first high byte. `specs/synth_dream.py:PulseWalker`

## Pulse width sweep

The replay edits a pulse wave in place to move its edge.

- [Tim Follin](../players/TimFollin.md): every N ticks, the replay rewrites the
  byte at the edge. The edge moves one byte, between bytes 4 and 30.
  `specs/tim_follin.py:PulseSweep`

## Beam noise

The replay reads the video beam position as a source of random values.

- [Sonic Arranger](../players/SonicArranger.md): two wave effects write beam
  noise into the wave. The noise differs at each tick, as the beam moves.
  `specs/sonic_arranger.py:NoiseGenerator1`

## Resampling synthesis

The replay rebuilds a voice's wave every tick from a resampled source. A wave
has up to 256 bytes.

- [TFMX Pro](../players/TFMX-Pro.md): IMS restarts the source at each buffer
  pass, like a hard sync. It limits each byte's change, like a slew limiter.
  `specs/tfmx_pro.py:ImsTick`

## Chip emulation

Short looped waves imitate a sound chip's tone and noise channels.

- [Jochen Hippel ST](../players/Jochen_Hippel_ST.md): a tone is a looped 4-byte
  square wave. Noise is a looped 1024-byte random sample.
  `specs/jochen_hippel_st.py:EmuTone`

## Compared

- AHX filters all its waves once, at start. Sonix Music Driver filters only
  synth waves, at load.
- AHX stores 32 squares of fixed pulse width. Synth Dream rebuilds its pulse
  wave every tick. Tim Follin flips one byte every N ticks.
