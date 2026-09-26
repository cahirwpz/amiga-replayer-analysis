# SoundMon 2.2 wave effects

Source: `ext/uade/amigasrc/players/uade/soundmon/Soundmon2.2.s`. All line
numbers refer to this file.

## How an effect runs

- Instrument byte 22 selects the effect at note start (line 557).
- Pattern option 11 sets the effect. Option 13 toggles effect 1 (lines 444,
  456).
- Byte 23 is the effect speed. Byte 24 is the first delay.
- Effects change only the first 32 bytes of the wave (lines 765, 787).
- The note start saves those 32 bytes. The next note writes them back (lines
  606, 261).
- "Saved wave" below means this copy. "Next table" means the pool table after
  the wave.

## Effects

"Step" is the speed byte. The last column is inference, not verified by
listening.

| No. | Operation                                                      | Rate          | Line | Likely sound (inference) |
| --- | -------------------------------------------------------------- | ------------- | ---- | ------------------------ |
| 0   | Nothing                                                        | —             | —    | —                        |
| 1   | Replace each sample by its average with the one before         | every N ticks | 758  | Duller, step by step     |
| 2   | Move each sample by step towards the saved wave, read backward | tick          | 782  | Morph to mirrored wave   |
| 3   | Move each sample by step towards the saved wave                | tick          | 800  | Undo EG and MOD changes  |
| 4   | Move each sample by step towards the next table                | tick          | 818  | Morph to the next wave   |
| 5   | Same as 3                                                      | tick          | 837  | Same as 3                |
| 6   | After the delay, copy the next table over the wave, once       | once          | 855  | Sudden timbre change     |

## Open questions

- Effects 3 and 5 have identical code. The editor may treat them differently.
