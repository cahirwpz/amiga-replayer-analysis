# Voice mixing

Software mixing adds voices beyond Paula's four channels. Each player below
fills a buffer once per tick, and a channel plays it.

| Player                                         | Mixed voices     | Volume per voice | Sum           | Mix rate          | Pitch                   |
| ---------------------------------------------- | ---------------- | ---------------- | ------------- | ----------------- | ----------------------- |
| [Mugician II](../players/MugicianII.md)        | 4 into 1 channel | 64 tables        | clipped       | fixed             | step per byte           |
| [TFMX 7V](../players/TFMX-7V.md)               | 4 into 1 channel | 64 tables        | clipped       | fixed             | step per byte           |
| [Oktalyzer](../players/Oktalyzer.md), replay 1 | 2 per channel    | none; shared     | 7-bit samples | fixed, 15.6 kHz   | generated code per note |
| [Oktalyzer](../players/Oktalyzer.md), replay 2 | 2 per channel    | none; shared     | 7-bit samples | higher note's own | lower voice only        |

## Two schemes

- Tables: one read applies a voice's volume; a second read clips the sum.
  Mugician II: `data/annot/MugicianII.yaml:BuildMixTables`. TFMX 7V:
  `data/annot/TFMX-7V.yaml:BuildMixTables`.
- Plain add: Oktalyzer halves the samples when it loads them. The sum then fits
  8 bits, and voices lose their own volume.
  `data/annot/Oktalyzer.yaml:HalveSample`

## Tricks

- Oktalyzer's replay 2 plays one voice at its own rate, so only one voice loses
  quality. `data/annot/Oktalyzer.yaml:PickHigher`
- Oktalyzer's replay 1 turns pitch into code: no step arithmetic at run time.
  `data/annot/Oktalyzer.yaml:BuildResamplers`
- TFMX 7V gives mixed voices RAM register sets, so the instrument program code
  needs no change. `data/annot/TFMX-7V.yaml:FakeRegisters`

## Cost

Cycles per mixed byte, by the source comments:

| Player      | Original | Wanted Team |
| ----------- | -------- | ----------- |
| Mugician II | 272      | 211         |
| TFMX 7V     | 268      | 254         |

Jochen Hippel's 7V player chooses between clipping and dividing the sum by 4.
`ext/uade/amigasrc/players/wanted_team/Jochen_Hippel_7V/src/Jochen Hippel 7V_020_v4.asm:lbC007560`
