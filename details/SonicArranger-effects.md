# Sonic Arranger wave effects

## How an effect runs

- Each note copies the instrument's wave into the voice. Paula plays the copy.
  `data/annot/SonicArranger.yaml:StartSynthWave`
- Instrument byte `$42` selects the effect. It indexes a jump table.
  `:EffectTable`
- The effect runs every N ticks; N is the effect delay. Synth instruments only.
  `:WaveEffect`
- Arguments: a value or second wave, `start` and `end`. Most effects change only
  bytes `start` to `end`.
- The effect position moves from `start` to `end`, then wraps. `:EffectStep`
- Changes pile up on the copy until the next note.

## Effects

"Other wave" is the second wave, selected by the argument. The last column is
inference, not verified by listening.

| No. | Operation                                                                       | Label       | Likely sound (inference) |
| --- | ------------------------------------------------------------------------------- | ----------- | ------------------------ |
| 0   | Nothing                                                                         | `:NoEffect` | —                        |
| 1   | Negate the byte at the effect position                                          | `:Effect1`  | Slowly changing buzz     |
| 2   | Negate the first N bytes of a fresh copy; N read from other wave                | `:Effect2`  | Changing pulse width     |
| 3   | Add the argument to every byte                                                  | `:Effect3`  | Harsh, as bytes wrap     |
| 4   | Shift the bytes one place left, cyclically                                      | `:Effect4`  | Slight detune            |
| 5   | Add the other wave to the copy                                                  | `:Effect5`  | Growing, wrapping mix    |
| 6   | Restore one byte from the original, negate the next one                         | `:Effect6`  | Moving glitch            |
| 7   | Add one value, read from the other wave at the position                         | `:Effect7`  | Harsh, as bytes wrap     |
| 8   | Effect 7, plus negate one byte at a moving position                             | `:Effect8`  | Harsh, with a buzz       |
| 9   | Move each byte one step towards the other wave, until equal                     | `:Effect9`  | Morph                    |
| 10  | Add the argument to the pitch offset, for N steps                               | `:Effect10` | Pitch sweep              |
| 11  | Add the argument to a byte if not above its neighbour, else subtract            | `:Effect11` | Brighter                 |
| 12  | Flip bits of the byte at the position, by the video beam position               | `:Effect12` | Noise creeping in        |
| 13  | Move each byte 2 towards its neighbour if they differ by more than the argument | `:Effect13` | Duller (low-pass)        |
| 14  | Effect 13, with the limit per byte read from the other wave                     | `:Effect14` | Duller, shaped           |
| 15  | Morph towards the other wave, then back to the original, forever                | `:Effect15` | Slowly swinging timbre   |
| 16  | Scramble every byte and add the video beam position                             | `:Effect16` | Noise                    |
| 17  | Lower the pitch a bit more each step; restart after N steps                     | `:Effect17` | Repeated drop, drum-like |
