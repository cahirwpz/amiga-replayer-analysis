# SoundMon 2.2 wave effects

## How an effect runs

- Instrument byte 22 selects the effect at note start.
  `data/annot/SoundMon2.2.yaml:StartSynthNote`
- Pattern option 11 sets the effect. Option 13 toggles effect 1. `:OptEffect`
  `:SetAutoArp`
- Byte 23 is the effect speed. Byte 24 is the first delay.
- Effects change only the first 32 bytes of the wave. `:Effect1` `:Effect2`
- The note start saves those 32 bytes. The next note writes them back.
  `:SaveWave` `:RestoreWaveLoop`
- "Saved wave" below means this copy. "Next table" means the pool table after
  the wave.

## Effects

"Step" is the speed byte. The last column is inference, not verified by
listening.

| No. | Operation                                                      | Rate          | Label      | Likely sound (inference) |
| --- | -------------------------------------------------------------- | ------------- | ---------- | ------------------------ |
| 0   | Nothing                                                        | —             | —          | —                        |
| 1   | Replace each sample by its average with the one before         | every N ticks | `:Effect1` | Duller, step by step     |
| 2   | Move each sample by step towards the saved wave, read backward | tick          | `:Effect2` | Morph to mirrored wave   |
| 3   | Move each sample by step towards the saved wave                | tick          | `:Effect3` | Undo EG and MOD changes  |
| 4   | Move each sample by step towards the next table                | tick          | `:Effect4` | Morph to the next wave   |
| 5   | Same as 3                                                      | tick          | `:Effect5` | Same as 3                |
| 6   | After the delay, copy the next table over the wave, once       | once          | `:Effect6` | Sudden timbre change     |

## Open questions

- Effects 3 and 5 have identical code. The editor may treat them differently.
