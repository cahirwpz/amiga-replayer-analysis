---
player: ArtOfNoise-8V
template: 2
ideas: [wavetable-scan, arpeggio-tables, voice-mixing, game-sync-flags]
---

# Art Of Noise 8V

A synth wave is a row of equal parts. The loop steps through them, forward,
backwards or ping-pong.

## Context

| Fact      | Value                                                   |
| --------- | ------------------------------------------------------- |
| Player    | `ArtOfNoise-8V`                                         |
| Author    | Bastian Spiegel                                         |
| Family    | Art Of Noise                                            |
| Code read | original: `ext/uade/amigasrc/players/uade/artofnoise`   |
| Spec      | [specs/art_of_noise_8v.py](../specs/art_of_noise_8v.py) |

## Key ideas

- A synth instrument loops one part of its wave, the format's `partwave`. Every
  N ticks, the loop start steps to the next part. `:SynthTick` `:StartSynth`
  - Enables: a timbre that moves through many stored shapes during a note.
  - Costs: every shape is stored in full.
- The step changes only the loop. The mixer takes the new loop when the playing
  part ends. `:StartMixVoice`
  - Enables: steps without clicks (inference).
  - Costs: a step waits for the playing part to end.
- After the first pass, the loop runs between two parts of the wave. The
  instrument's mode picks forward, backwards or ping-pong. `:SynthTick`
  - Enables: a long attack, then a short moving sustain.
- Spare bits in each cell pick one of 16 arpeggio tables. A table holds up to 7
  offsets. `:PickArpeggio`
  - Enables: chords and runs with the command column still free.
  - Costs: 16 tables per module.
  - Costs: offsets go only up, by 0 to 15 semitones.
- Each Paula channel plays two voices. Its audio interrupt mixes the next 128
  bytes for them, apart from the tick. `:MixInterrupt` `:MixPair`
  - Enables: eight voices at any tempo. See
    [voice mixing](../ideas/voice-mixing.md).
  - Costs: CPU high, about 100 cycles per mixed byte (estimate). The source
    recommends a 68020. `:MixPair`

## Composer's view

The composer writes 8 tracks of ProTracker-like cells, arpeggio tables, and
sample or synth instruments.

| Aspect   | Answer                                                                 | Source              |
| -------- | ---------------------------------------------------------------------- | ------------------- |
| Notation | A cell: note, instrument, command and argument.                        | `:ReadCell`         |
| Notation | A synth instrument: a wave, a part length and a step speed.            | `:Instrument`       |
| Notation | A synth instrument: the parts of the first pass and of the loop.       | `:Instrument`       |
| Notation | A synth instrument: its own vibrato, with a delay.                     | `:StartSynth`       |
| Notation | An instrument: an envelope that rises to a top, then falls to a level. | `:InitEnvelope`     |
| Notation | `WAVE_SPEED` changes the step speed of the playing note.               | `:CmdWaveSpeed`     |
| Notation | `WAVE_HOLD` lets later notes on the same wave keep the step.           | `:CmdWaveHold`      |
| Notation | `WAVE_HOLD` can also stop the steps where they are.                    | `:CmdWaveHold`      |
| Notation | `SYNTH_DRUMS` slides the pitch down and the volume down.               | `:CmdSynthDrums`    |
| Notation | `TRACK_VOLUME` sets a second volume for the track.                     | `:CmdTrackVolume`   |
| Notation | `EXTERNAL_EVENT` passes a byte to the game or demo.                    | `:CmdExternalEvent` |
| Cost     | Each row picks its arpeggio table again. Table 0 is the default.       | `:ReadCell`         |
| Cost     | A row with no note can change the arpeggio of the held note.           | `:ReadCell`         |
| Cost     | A note's first step comes one tick after it starts, at any speed.      | `:StartSynth`       |
| Cost     | A sample without a loop ends on a silent one-word loop.                | `:StartSample`      |
| Cost     | The envelope runs to 127. Above 64, it raises the note's volume.       | `:WriteShadow`      |
| Cost     | An arpeggio steps every tick, unless `ARPEGGIO_SPEED` slows it.        | `:CmdArpeggioSpeed` |

## What is unique

- A new note on the same synth wave plays on, with no restart. Only the steps
  start again. `:StartSynth`
- Ping-pong steps play each end part twice. `:SynthTick`
- Between two arpeggio steps, vibrato offsets add up. With a slow arpeggio, the
  pitch drifts. `:VibratoTick`
- The mixer has a linear interpolation pass, commented out. `:MixPair`

## Open questions

- Which modules step backwards or ping-pong?
- The file keeps an unused 4-voice output routine. It halves the envelope level
  first. Is the 8-voice doubling intended?
