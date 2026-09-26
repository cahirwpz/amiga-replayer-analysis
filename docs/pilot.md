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

| Player                   | Theme             | Why                                                | Card                             |
| ------------------------ | ----------------- | -------------------------------------------------- | -------------------------------- |
| `MugicianII`             | synthesis, mixing | Waveforms as envelopes, in-place effects, 7 voices | [done](../players/MugicianII.md) |
| `SoundMon2.2`            | synthesis         | Four table walkers per voice                       | pending                          |
| `FutureComposer1.3`      | synthesis         | Volume and pitch command lists                     | pending                          |
| `SonicArranger`          | synthesis         | Synth instruments                                  | pending                          |
| `TFMX-Pro`               | synthesis         | Macro language with conditions and calls           | pending                          |
| `SonixMusicDriver`       | synthesis         | Note score, synth with filter bank                 | pending                          |
| `MED`                    | synthesis         | Two synth command lists that jump into each other  | pending                          |
| `AbyssHighestExperience` | synthesis         | AHX; read from a C port                            | pending                          |
| `SynthDream`             | synthesis         | Synth format, not yet read                         | pending                          |
| `Jochen_Hippel_ST`       | emulation         | Atari ST sound chip emulated on Paula              | pending                          |
| `SoundPlayer`            | tricks            | Attach modes, confirmed in code                    | pending                          |
| `DigitalSonixChrome`     | tricks            | Audio interrupts count loop repeats                | pending                          |

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

Review the cards, then tune the limits, the template and the axes.
