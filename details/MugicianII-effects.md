# Mugician II waveform effects

## How an effect runs

- Instrument byte 11 selects the effect. It indexes a jump table.
  `data/annot/MugicianII.yaml:EffectTable`
- The effect rewrites the instrument's own wave. Only synth waves are affected.
  `:SynthWavesOnly`
- It runs every N ticks. N is instrument byte 14. `:EffectDelay`
- Wave A is instrument byte 12. Wave B is instrument byte 13.
- On a new note, wave A is copied over the working wave. `:CopyWaveA`
- "Step" below is the effect position. It lives in the instrument, so voices
  share it.

## Effects

"Length" is the instrument's wave length. Rows without it work on all 128 bytes.
The last column is inference, not verified by listening.

| No.   | Operation                                                   | Label       | Likely sound (inference) |
| ----- | ----------------------------------------------------------- | ----------- | ------------------------ |
| 0     | Nothing                                                     | `:NoEffect` | —                        |
| 1     | Replace each sample by its average with the next one        | `:Effect1`  | Duller, step by step     |
| 2     | Average wave A with wave B, read from a moving offset       | `:Effect2`  | Phasing                  |
| 3     | Shift the wave one sample left, cyclically                  | `:Effect3`  | Slight detune            |
| 4     | Shift the wave one sample right, cyclically                 | `:Effect4`  | Slight detune            |
| 5     | Keep every second sample, then repeat that half             | `:Effect5`  | One octave up            |
| 6     | Double each sample of the first half                        | `:Effect6`  | One octave down          |
| 7     | Negate one more sample per step, over the length            | `:Effect7`  | Changing pulse width     |
| 8     | Add a ramp; its slope is read from wave B                   | `:Effect8`  | Growing brightness       |
| 9     | Add wave B, sample by sample, over the length               | `:Effect9`  | Changing timbre          |
| 10    | Set each sample to 3/4 of the previous plus 1/4 of the next | `:Effect10` | Duller, faster           |
| 11    | Crossfade wave A and wave B, back and forth over 128 steps  | `:Effect11` | Slow morph               |
| 12    | Same crossfade over 32 steps                                | `:Effect12` | Fast morph               |
| 13    | Set each sample to the average of its two neighbours        | `:Effect13` | Duller                   |
| 14    | Negate two samples, byte 13 apart, moving each step         | `:Effect14` | Pulse-width sweep        |
| 15    | Smooth each step; every byte 13 steps, apply effect 5       | `:Effect15` | Dull, then bright again  |
| 16–31 | Nothing                                                     | `:NoEffect` | —                        |

## Notes

- Effects 3–6, 10 and 13 use all 128 bytes. The others use the instrument's
  length.
- Effect 9 adds without clipping, so values wrap around.
- Effect 15 falls through into effect 5's code. `:Effect15`
- The Flod port has the same 15 effects with the same numbers.
  `ext/c-flod/neoart/flod/digitalmugician/DMPlayer.c:DMPlayer_process`
- Flod runs effects only in 4-voice songs. The 68000 code always runs them: its
  skip flag is a constant 0. `data/annot/MugicianII.yaml:RunEffect`
