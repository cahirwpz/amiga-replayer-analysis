---
player: ArtOfNoise-8V
template: 3
ideas: [wavetable-scan, arpeggio-tables, voice-mixing, game-sync-flags]
---

# Art Of Noise 8V

A synth loop steps through the equal parts of one long wave, on mixed voices.

## Unique ideas

- A synth wave is one long sample of equal parts, the format's `partwave`. Every
  N ticks, the loop start moves one part on. `:SynthTick` `:StartSynth`
  - Limits: every shape is stored in full.
  - Limits: a part holds at most 255 words.
- After the first pass, the loop runs between two parts. It moves forward,
  backwards or back and forth. `:SynthTick`
- The mixer takes a new loop only at the end of the playing part. A step never
  cuts a part (inference: no clicks). `:StartMixVoice`
- Spare cell bits pick one of 16 arpeggio tables. A table holds up to 7 offsets.
  `:PickArpeggio`
  - Limits: offsets go only up, by 0 to 15 semitones.
- Each Paula channel plays two voices, by
  [voice mixing](../ideas/voice-mixing.md). `:MixInterrupt` `:MixPair`
  - Limits: CPU high, about 104 cycles per mixed byte (estimate).
  - Limits: no interpolation. A linear pass in the source is commented out.
  - Limits: the mixer divides with `divu.l`, which needs a 68020.
    `:StartMixVoice`
- `EXTERNAL_EVENT` passes a byte to the game or demo, at the row's tick.
  `:CmdExternalEvent`

## How it plays

The [CIA timer](../docs/paula-techniques.md#cia-timer) runs the tick. Each
channel's audio interrupt mixes the next 128 bytes for its two voices. `:Play`
`:MixInterrupt`

- The mixer holds off all other interrupts while it mixes. A tick can wait.
- Channel 3 starts on channel 2's buffer and plays it once. `:Init`

Every `speed` ticks, voices 0 to 7 read their cells. Then each voice runs its
effects and writes its shadow. `:PlayEffects`

### Player

The player holds the position, row, tick, `speed`, tempo and event byte.
`:Module`

### Voice

A voice holds its note, instrument, wave, part, loop, volume and track volume.
It holds the period, slide, arpeggio, scan, envelope and vibrato. `:Voice`

Its restart flags are `NEW_START`, for a new part, and `NEW_LOOP`, for a new
loop. `:Shadow`

Each row, it reads a note, an instrument, a command and its argument:
`:ReadCell`

1. A note without an instrument replays the last one and keeps the volume.
2. A sample instrument without a note sets only `NEW_LOOP`. Its loop follows the
   playing part. A synth instrument changes only the volume.
3. `TONE_SLIDE` on the last instrument makes the note only the slide's target.
4. The voice picks its arpeggio table, also without a note. `:PickArpeggio`
   - **Trap:** each row picks again. A cell without spare bits picks table 0.
   - **Trap:** a row with no note changes the arpeggio of the held note.
   - **Trap:** a new note keeps the arpeggio's step, unless the old table has
     one step. It may start above the note.

A new note starts before the arpeggio pick: `:StartSample` `:StartSynth`

1. The envelope restarts, unless `SYNTH_CONTROL`'s bit 0 keeps it.
   `:InitEnvelope`
2. A sample note sets both restart flags. It plays to its loop's end, then
   loops.
3. A synth note on a new wave sets both restart flags and restarts the scan.
   - **Trap:** on the same wave, the old part plays on. Only the scan restarts.
4. `SYNTH_CONTROL`'s bit 4 makes the note legato. The old wave and scan run on,
   for any wave.
5. `SAMPLE_OFFSET` moves a synth note's scan by half a part per argument step.
   The first part still plays from the wave's start.

- **Trap:** a note above 60 starts the instrument at the old pitch. The arpeggio
  pick never runs. `:ReadCell`

Each tick, in this order: `:EffectsTick`

1. Every `ARPEGGIO_SPEED` ticks, at first every tick, the arpeggio sets the
   period.
   - Past note 60, a step reads the next fine tune's low notes (bug).
2. The command runs. Slides and vibrato skip the row's tick.
   - `SYNTH_DRUMS` slides the pitch down and the volume down. `:CmdSynthDrums`
   - `TRACK_VOLUME` sets a second volume for all notes. `:CmdTrackVolume`
3. With restart flags set, the scan and the envelope skip this tick. A new
   note's first scan step comes one tick later, at any speed. `:SynthTick`
4. The envelope rises to 127, then falls to its end level. It runs for samples
   too.
5. Vibrato adds its offset to the period, once per tick. `:VibratoTick`
   - **Trap:** offsets add up between arpeggio steps. With a slow arpeggio, the
     pitch drifts.
   - An instrument's own vibrato starts after its delay.
6. The shadow gets the period plus the slide, at least 103. `:WriteShadow`
   - **Trap:** an arpeggio table steps on top of a portamento.
7. The shadow's volume is the volume × the envelope / 64 × the track volume
   / 64. Then the loop and the restart flags. `:WriteShadowLoop`
   - **Trap:** the envelope reaches 127. It can double a quiet note, up to 64.

A sample without a loop ends on a
[silent loop](../docs/paula-techniques.md#silent-loop) of one word. The mixer
then stops the voice. A synth note sounds until the next note or volume 0.

### Scan

The scan walks a synth voice's loop through the wave. It holds a position, the
pass's ends, a step, a speed and a mode. `:Voice`

1. Every scan speed ticks, the position moves one part. `:SynthTick`
2. At the first pass's end or the loop's end, the mode acts.
   - Forward goes back to the loop's first part.
   - Backwards runs down from the loop's last part.
   - Back and forth turns, first at the first pass's end. It plays each end part
     twice.
3. The voice's loop becomes the position, and `NEW_LOOP` is set.

- `WAVE_SPEED` changes the scan speed of the playing note. `:CmdWaveSpeed`
- `WAVE_HOLD`'s low nibble keeps the scan across notes on the same wave. Its
  high nibble freezes the scan. `:CmdWaveHold`
  - **Trap:** both settings stay until the next `WAVE_HOLD`, for every note.
- **Trap:** a fast scan on a long, low part skips parts. Only the last loop
  sounds (estimate).

### Mixer

A mix voice holds a part, its position, a loop, a step and a volume. `:MixVoice`

1. At the tick's end, each shadow goes to its mix voice. `:StartMixVoice`
2. The step is 250 / period, in 16.16 bytes. The mix rate is about 14.2 kHz.
3. The audio interrupt writes its other buffer to `AUDxLC`. It fills that buffer
   now, and it plays next. `:MixInterrupt`
   - A change reaches the output within two buffers, about 18 ms (estimate).
4. Each output byte adds both voices' bytes, each × its volume / 128. `:MixPair`
5. At the part's end, the loop follows. A loop of 2 bytes or less stops the
   voice.
   - The end check runs every two bytes. The wrap drops the overshoot.

## Open questions

- Which modules scan backwards or back and forth?
- The unused 4-voice routine halves the envelope. Is the 8-voice doubling meant?
- The source calls a note above 60 a pause. Is the restart meant?
