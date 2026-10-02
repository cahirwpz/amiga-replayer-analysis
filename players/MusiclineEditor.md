---
player: MusiclineEditor
template: 3
ideas:
  [
    wave-effect-chain,
    shared-sweeps,
    per-voice-positions,
    swing,
    seamless-wave-notes,
    timer-dma-wait,
    voice-mixing,
  ]
---

# Musicline Editor

Five wave effects rebuild a voice's wave every tick, each driven by its own
sweep.

## Unique ideas

- Transform, phase, mix, resonance and filter run as a chain every tick. The
  channel plays the last buffer. `:PlayEffects`
  - Limits: the loop must be 16 to 256 bytes, a power of 2. `:CheckWaveSize`
  - Limits: CPU high. Up to five passes run over 256 bytes per voice per tick.
- Each tick, the chain starts again from the plain wave. Only the sweeps, the
  mix buffer and the filters' last value carry over. `:PlayEffects`
  `:FilterPlay`
- One sweep type drives every effect. `:Counter`
- Each voice has its own positions, `speed` and swing, Musicline's `groove`.
  `:PlayVoice`
- A new note on the same wave keeps DMA on. The wave plays on at the new pitch,
  without a click (inference). `:DmaPlay`
- In 8-channel mode, the CPU [mixes](../ideas/voice-mixing.md) two voices into
  each channel. `:Play8Channels`
  - Limits: CPU high. The mix rate is fixed by `MIX_PERIOD`.

## How it plays

With 4 channels, CIA-B timer A runs the tick at the tempo. With 8 channels,
channel 0's audio interrupt runs it. `:StartTimerInt` `:StartAudioInt`

A tick reads rows, runs effects and computes periods for all voices. It then
writes periods and volumes, and starts new notes. `:PlayMusic`

### Voice

A voice holds its positions, `speed`, swing and row countdown. `:Channel`

When the row countdown ends: `:PlayVoice`

1. The swing phase flips. The countdown restarts at `speed`, or at swing.
2. A position holds a pattern and a transpose of -16 to +15 semitones. Or it
   ends the voice, jumps back N times, or waits N rows.
   - After an end, the voice reads no more rows. Its last note sounds on.
3. A row holds a note, an instrument number and five command words. A pattern
   has at most 128 rows, and jumps only back.
   - **Trap:** a new position resets `speed` and swing to the song's.
     `FxSpeedAll` sets the song's, or the tempo from `MIN_TEMPO` on.
     `:FxSpeedAll`
   - **Trap:** a pattern that ends on its first row stops the whole song.
4. Commands run, then the arpeggio table, then the note start. `:PlayPartFx`

A note start: `:PlayInst`

1. The instrument's sample or wave plays, or `FxWaveSample`'s. The transpose
   stays only with the instrument's flag.
2. A wave is stored in five sizes, 256 down to 16 bytes. The instrument's size
   loops whole. `:FixWaveLength`
3. A sample without the loop flag ends on a
   [silent loop](../docs/paula-techniques.md#silent-loop).
4. A note without an instrument number is legato. Only its pitch changes.
5. The instrument restarts vibrato, tremolo, envelope and sweeps. `:InstPlay`

Each tick, in this order: `:PlayEffects`

1. The chain's input goes back to the plain loop.
2. After a note's first tick, the arpeggio table, vibrato and tremolo run.
3. The envelope scales the volume. Each phase ramps, then jumps to its target.
   `:AdsrPlay`
   - Release follows the sustain time, unless `FxHoldSustain` holds it.
     `:FxHoldSustain`
4. The loop sweep writes a moving loop window to `AUDxLC` and `AUDxLEN`.
   `:MoveLoop`
   - After its turns, it can end on a silent loop.
5. The five wave effects run.
6. The pitch sums note, vibrato, semitone, finetune and transpose, in 1/32
   semitones. A table gives the period. `:NotePeriod`
   - A vibrato is the same interval at any pitch. `:VibratoPlay`
7. Voices without a new note get `AUDxPER` and `AUDxVOL`. `:PerVolPlay`
   - The volume is the envelope's × channel volume × master volume.

New notes start with a
[DMA restart wait](../docs/paula-techniques.md#dma-restart-wait):

1. DMA goes off, except for a wave note on the same wave. Timer B waits the
   longest old period, as 5-CCK counts. `:DmaPlay`
2. Each new note gets `AUDxVOL`, `AUDxLC`, `AUDxLEN`, `AUDxPER` and DMA on.
   `:DmaStart`
3. Timer B then gives restarted channels their loop in `AUDxLC` and `AUDxLEN`.
   `:DmaLoop`

### Arpeggio table

A voice holds the table, its position and a countdown. `:Channel`

- A note with an instrument number starts the table. Empty first steps hold back
  the note start. `:PlayArpg`
- The table steps every `arp_speed` ticks, with its own swing. `:ArpeggioPlay`
- A step holds a note, a wave and two commands. A note with bit 7 adds to the
  row's note, else it is a fixed note.
  - **Trap:** a step's wave starts a new note. DMA restarts unless the wave is
    the same. The envelope does not restart.
- A new instrument number ends the table. `:CheckInst`

### Wave effects

A voice holds five 256-byte buffers and five sweeps. A sweep holds a counter, a
speed, two limits, turns, a delay and two flags. `:Sweep`

- After a delay, the counter moves by the speed each tick. At a limit it turns.
  `:Counter`
  - It stops after its turns, or never with 0 turns.
- With the init flag, a note of the same instrument keeps the sweep. Its value
  runs on. `:InstPlay`
- With the step flag, the sweep moves once per note. The value then drifts by
  the step size each tick. `:PhasePlay`

Each effect reads the previous buffer: `:PlayEffects`

1. Transform crossfades two neighbours in a chain of six waves. `:TransformPlay`
2. Phase squeezes the whole cycle into its start. The rest holds the last value,
   or repeats. `:PhasePlay`
3. Mix adds a rotated copy of another wave, the wave or its last output.
   `:MixPlay`
4. Resonance runs a two-pole filter with feedback. `:ResonancePlay`
5. Filter runs a low-pass filter or a resonant one. `:FilterPlay`

- **Trap:** both filters start from the last tick's last value, also across
  notes. A restarted sweep resets it.
- With 4 channels and fast memory, the last buffer is copied into the voice's
  chip buffer. Paula plays it as
  [live wave edits](../docs/paula-techniques.md#live-wave-edits).

### Mixer

With 8 channels, voices n and n + 4 share channel n. `:Play8Channels`

- **Trap:** a tempo command sets the stopped timer A. The buffer keeps its first
  length. `:StartAudioInt`
- Paula plays half a double buffer while the tick fills the other. `:PlayMusic`
- A voice resamples at `MIX_PERIOD` / period. A volume table halves it.
  `:MixVoice`
- At the sample's end, the loop follows, or silence.

## Open questions

- The plain filter's feedback factor is $f000, small and negative. `:FilterPlay`
- Below note 0, the pitch lookup reads before its table. `:NotePeriod`
