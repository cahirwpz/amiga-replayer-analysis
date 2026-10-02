---
player: MusicMaker-8V
template: 3
ideas: [voice-mixing, interrupt-clock, self-modifying-mixer, sample-envelope]
---

# MusicMaker 8V

Eight voices share four channels in pairs, and the audio interrupts are the
clock.

## Unique ideas

- Voices 2n and 2n+1 form a pair on channel n, by
  [mixing](../docs/paula-techniques.md#mixing). The channel plays at the higher
  voice's period, with no resampling for that voice. `:MixPair` `:MixSpan`
  - Limits: high notes raise the mix rate. A higher mix rate costs more CPU.
  - Limits: the fast mixer caps the mix rate. Periods up to the song's limit
    play slower and skip bytes. `:MixPair`
- The louder voice sets the channel volume. A table scales the quieter voice by
  the ratio of the two volumes. `:VolumeTable`
  - Limits: the replay halves every sample byte at load. Each voice loses 1 bit.
    `:HalveSamples`
- Each buffer lasts one tick at its own period. The tick runs once all four
  channels have started their buffers. `:AudioInterrupt` `:BufferLength`
  - Limits: the replay busy-waits inside the interrupt for the last channel.
    `:WaitAllChannels`
- On a 68000, the fast mixer writes its own step instructions for each pair of
  periods. Each case keeps its own copy of the inner loop. `:BuildStepPattern`
  `:PickMixer`
  - Limits: from the 68020 on, every channel uses the slow mixer. Code that
    writes code fights the cache (guess). `:DbraStep`
- A sample envelope changes volume and period by sample position. The format
  calls it `HULL`. `:HullVolume` `:HullStep`
  - It stays with the sample at any pitch.
  - Limits: one entry covers 40 sample bytes.
- `BREAK` saves a voice's remaining sample bytes, and with note 0 silences it. A
  later note plays the saved bytes. `:BreakNote` `:ResumeBreak`
- With `LoudnessSwitch` on, high notes play quieter, down to half volume.
  `:Loudness`

## How it plays

Only the four audio interrupts drive the replay. There is no VBL tick and no CIA
timer. `:AudioInterrupt`

1. A channel's interrupt writes `AUDxPER` and `AUDxVOL` for the buffer that
   starts now.
2. It writes the other buffer to `AUDxLC`. Paula takes it at the next reload.
3. Once all four channels have interrupted, the tick runs.
   - **Trap:** with an audio interrupt pending at the tick's end, the replay
     turns all sound off.

A tick corrects drift and takes a new tick length. Voices 7 down to 0 run, and
the mixer follows. `:PlaySound`

### Player

The player holds the tick length, in units of 115 CCK, and two fade speeds. It
holds a sample envelope per instrument and the audio filter state. `:Module`

- `SetSpeed` scales the song's tick length by a ratio of two 4-bit numbers. The
  next tick takes it. `:SetSpeed`
  - A song can only get faster.
- **Trap:** the last fade command sets the fade speed of all voices.
  `:VoiceFade`
- **Trap:** a note's filter flag switches the audio filter for all voices.
  `:NoteEvent`
- **Trap:** `HULL` sets an instrument's sample envelope for all voices. It
  starts at that instrument's next sample start. `:SetHull`

### Voice

A voice holds its position list, pattern position, tick countdown, sample and
loop. It holds its note, period, volume, fade, two steps and envelope position.
`:Voice`

A pattern is a list of 3-byte events. The format calls it `macro`. An event is a
note or a command, plus its length.

When the countdown ends, the voice reads an event: `:HandleVoice` `:ReadEvent`

1. Byte 0 holds the instrument and the volume, or a command. Byte 2 holds the
   legato flag, the filter flag and the length.
   - An event lasts 2 to 128 ticks, in steps of 2. Commands take time, too.
   - **Trap:** at `BANK`, or before `SOFT_STEP`, the next event's byte 2 sets
     the length.
2. An event names 16 instruments. `BANK` first adds an offset to reach the
   others. `:InstrumentBank`
3. A note clears both steps. Byte 1 holds the loop flag, a filter state and the
   note. `:NoteEvent`
   - There are 64 notes. From period 856 to 170, notes step by half a semitone.
     Above, they step by semitones, up to 113.
   - Volume has 16 steps. Volume 0 is a rest, which silences the voice.
4. With the legato flag, the sample plays on. A following `SOFT_STEP` sets both
   steps. `:SoftModulation`
   - A legato note keeps its sample envelope position.
5. Otherwise a new sample starts, once or as its attack and then its loop. Its
   sample envelope restarts. `:StartNote`
6. At the pattern's end, the voice reads its next position. `:NextEvent`
   `:NextPattern`
   - `PAUSE` waits. `END_OF_LIST` restarts the position list.
   - A pattern that starts with `CONTINUE` holds the last note on.

Each tick, the voice computes a volume and a period for the mixer: `:StepVoices`

1. A voice fade moves the volume divisor. `:FadeTick`
2. The volume step adds to the volume. With tremolo, its sign flips every second
   tick. `:VolumeSlide`
3. The sample envelope, loudness and the fade divisor scale the volume.
   `:HullVolume` `:Loudness`
4. The period step adds to the period. With vibrato, its sign flips every second
   tick. `:PeriodSlide`
   - Vibrato and tremolo are 4-tick triangles. Only the step size varies.
   - Vibrato depth is in periods. Low notes get a smaller pitch change.
   - **Trap:** vibrato and tremolo share one switch. Starting one clears the
     other's step. `:Modulation`
   - A period slide ends vibrato. A volume slide ends tremolo.
5. The sample envelope changes the period. It moves on by the bytes the sample
   plays this tick. `:HullStep`
   - At the sample's end, it moves back by the loop length, or stops.

### Mix channel

A mix channel holds its pair's remaining bytes, two buffers, a mix period and a
volume. It holds a drift correction and its mixer, fast or slow, which the song
picks. `:MixChannel`

Each tick, after all voices, in this order: `:MixChannels`

1. A new sample replaces a voice's remaining bytes. With 3 bytes or fewer left,
   the loop replaces them. `:MixPair`
2. The mix period is the lower period of the sounding voices. The channel volume
   is the louder voice's. `:MixPair`
   - With both voices silent, the buffer holds zeros at period 230.
3. The buffer length is the tick length × 115 / the mix period, made even.
   `:BufferLength`
   - A late channel gets a shorter next buffer, by up to 5 bytes.
     `:CorrectDrift`
4. Each output byte is the louder voice's byte plus the quieter one's, scaled.
   The voice at the mix period steps one byte. `:MixSpan`
   - The other voice steps by its period ratio.
   - At a sample's end, its loop follows, or silence. `:WrapSample`
5. The buffers swap. `AUDxLEN` gets the new length. `:SwapBuffers`

## Open questions

- Why does loudness make high notes quieter? Hearing, or noise from skipped
  bytes (guess)? `:Loudness`
