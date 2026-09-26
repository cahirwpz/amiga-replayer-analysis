# Pilot

Twelve players to test the card template before the full survey. Each has replay
source we can read: original, disassembled, or a port.

## Selection rules

- Focus on formats that did not prevail on the demoscene.
- No `ProTracker`-like players.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- Replay logic must be readable: `replay` is `uade` or `port` in
  [the inventory](inventory.md). No guessing from module-embedded code.

## Players

| Player                                                                                | Theme             | Why                                                |
| ------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------- |
| [`MugicianII`](../data/inventory.csv?plain=1#L91 "MugicianII")                        | synthesis, mixing | Waveforms as envelopes, in-place effects, 7 voices |
| [`SoundMon2.2`](../data/inventory.csv?plain=1#L142 "SoundMon2.2")                     | synthesis         | Four table walkers per voice                       |
| [`FutureComposer1.3`](../data/inventory.csv?plain=1#L47 "FutureComposer1.3")          | synthesis         | Volume and pitch command lists                     |
| [`SonicArranger`](../data/inventory.csv?plain=1#L134 "SonicArranger")                 | synthesis         | Synth instruments                                  |
| [`TFMX-Pro`](../data/inventory.csv?plain=1#L161 "TFMX-Pro")                           | synthesis         | Macro language with conditions and calls           |
| [`SonixMusicDriver`](../data/inventory.csv?plain=1#L135 "SonixMusicDriver")           | synthesis         | Note score, synth with filter bank                 |
| [`MED`](../data/inventory.csv?plain=1#L84 "MED")                                      | synthesis         | Two synth command lists that jump into each other  |
| [`AbyssHighestExperience`](../data/inventory.csv?plain=1#L2 "AbyssHighestExperience") | synthesis         | AHX; read from a C port                            |
| [`SynthDream`](../data/inventory.csv?plain=1#L154 "SynthDream")                       | synthesis         | Synth format, not yet read                         |
| [`Jochen_Hippel_ST`](../data/inventory.csv?plain=1#L65 "Jochen_Hippel_ST")            | emulation         | Atari ST sound chip emulated on Paula              |
| [`SoundPlayer`](../data/inventory.csv?plain=1#L143 "SoundPlayer")                     | tricks            | Attach modes, confirmed in code                    |
| [`DigitalSonixChrome`](../data/inventory.csv?plain=1#L34 "DigitalSonixChrome")        | tricks            | Audio interrupts count loop repeats                |

## Rejected

| Player                                                           | Reason                              |
| ---------------------------------------------------------------- | ----------------------------------- |
| `RobHubbard`, `BenDaglish-SID`, `JankoMrsicFlogel`, `Special-FX` | Replay code is in the module        |
| `PreTracker`                                                     | Replay code is a prebuilt binary    |
| `Pokeynoise`, `ADPCM_mono`                                       | Too primitive or already well known |
| `Mugician`                                                       | Covered by `MugicianII`             |
| `JochenHippel-7V`                                                | Mixing is covered by `MugicianII`   |
| `PTK-Prowiz`                                                     | `ProTracker`-like                   |

## After the pilot

Progress is tracked in [`TODO.md`](../TODO.md).
