# Mugician II waveform effects

Source: `wanted_team/MugicianII/src/Mugician II_v8.asm`. All line numbers refer
to this file.

## How an effect runs

- Instrument byte 11 selects the effect. It indexes the jump table at line 2506.
- The effect rewrites the instrument's own wave. Only synth waves are affected
  (line 2262).
- It runs every N ticks. N is instrument byte 14 (line 2294).
- Wave A is instrument byte 12. Wave B is instrument byte 13.
- On a new note, wave A is copied over the working wave (line 2128).
- "Step" below is the effect position. It lives in the instrument, so voices
  share it.

## Effects

"Length" is the instrument's wave length. Rows without it work on all 128 bytes.
The last column is inference, not verified by listening.

| No.   | Operation                                                   | Line | Likely sound (inference) |
| ----- | ----------------------------------------------------------- | ---- | ------------------------ |
| 0     | Nothing                                                     | 2507 | —                        |
| 1     | Replace each sample by its average with the next one        | 2873 | Duller, step by step     |
| 2     | Average wave A with wave B, read from a moving offset       | 2744 | Phasing                  |
| 3     | Shift the wave one sample left, cyclically                  | 2841 | Slight detune            |
| 4     | Shift the wave one sample right, cyclically                 | 2848 | Slight detune            |
| 5     | Keep every second sample, then repeat that half             | 2697 | One octave up            |
| 6     | Double each sample of the first half                        | 2684 | One octave down          |
| 7     | Negate one more sample per step, over the length            | 2807 | Changing pulse width     |
| 8     | Add a ramp; its slope is read from wave B                   | 2717 | Growing brightness       |
| 9     | Add wave B, sample by sample, over the length               | 2786 | Changing timbre          |
| 10    | Set each sample to 3/4 of the previous plus 1/4 of the next | 2884 | Duller, faster           |
| 11    | Crossfade wave A and wave B, back and forth over 128 steps  | 2540 | Slow morph               |
| 12    | Same crossfade over 32 steps                                | 2612 | Fast morph               |
| 13    | Set each sample to the average of its two neighbours        | 2901 | Duller                   |
| 14    | Negate two samples, byte 13 apart, moving each step         | 2821 | Pulse-width sweep        |
| 15    | Smooth each step; every byte 13 steps, apply effect 5       | 2856 | Dull, then bright again  |
| 16–31 | Nothing                                                     | 2523 | —                        |

## Notes

- Effects 3–6, 10 and 13 use all 128 bytes. The others use the instrument's
  length.
- Effect 9 adds without clipping, so values wrap around.
- Effect 15 falls through into effect 5's code (line 2871).
- Not yet cross-checked against an independent replayer.
