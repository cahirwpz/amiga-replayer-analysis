# Jochen Hippel ST: emulation accuracy

What the code shows about how close the Paula output is to the ST's sound chip.
Labels are under `data/annot/Jochen_Hippel_ST.yaml:EmuChannel`.

## Tone pitch

- The chip plays a square at 2 MHz / (16 × period). The 2 MHz clock is a known
  ST fact, not in this code.
- The layer plays a 4-sample square at Paula period 7 × period + 1.
  `:EmuChannel`
- The exact factor would be 7.09. So most tones play sharp.

| Chip period | Chip tone (Hz) | Paula period | Error (cents) |
| ----------- | -------------- | ------------ | ------------- |
| 10          | 12500          | 71           | −1.5          |
| 20          | 6250           | 141          | +10.7         |
| 50          | 2500           | 351          | +18.1         |
| 100         | 1250           | 701          | +20.6         |
| 1000        | 125            | 7001         | +22.8         |
| 4095        | 30.5           | 28666        | +23.0         |

- Chip periods below 18 give Paula periods below 124, Paula's usual minimum.
  Those tones are above 6.9 kHz.
- The square's shape is exact: two samples low, two high. `:SquareWave`

## What is lost

- Tone and noise on one channel: only the tone plays. `:EmuChannel`
- Envelope mode: a fixed volume of 32 instead of the chip's envelope.
  `:VolumeTable`
- Volume steps: the table rises by 1.6 to 3.5 dB per step, 6 dB at the bottom.
  Comparing this with the chip's curve needs the `YM2149` datasheet.
