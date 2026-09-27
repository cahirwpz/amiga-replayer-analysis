---
player: TFMX-7V
template: 2
base: TFMX-Pro
ideas: [voice-mixing]
---

# TFMX 7V

[TFMX Pro](TFMX-Pro.md) with seven voices: voices 4–7 are mixed into channel 3.

## Context

| Fact       | Value                                                        |
| ---------- | ------------------------------------------------------------ |
| Player     | `TFMX-7V`                                                    |
| Author     | Chris Hülsbeck                                               |
| Family     | TFMX                                                         |
| Influences | `JochenHippel-7V`                                            |
| Code read  | disassembly: `ext/uade/amigasrc/players/wanted_team/TFMX-7V` |
| Spec       | [specs/tfmx_7v.py](../specs/tfmx_7v.py)                      |

## Key ideas

- Voices 4–7 write register sets in RAM, not Paula. `:FakeChannel`
  - Enables: seven voices with an unchanged macro engine.
  - Costs: voice 3 cannot play while the mix plays.
- The mixer sums voices 4–7 into one tick's buffer for channel 3. `:MixTick`
  `:MixLoop`
  - Enables: four extra voices on one channel.
  - Costs: CPU high. At 16 kHz, mixing takes about 57% of a 7.09 MHz 68000.
- Channel 3's audio interrupt runs the whole replay. `:HookChannel3`
  `:TickFromMixer`
  - Enables: the tick and the buffer never drift apart.
  - Costs: a position command that stretches the buffer also slows the tick.
    `:CmdMixSlow`
- Volume is one table read per byte. The sum of four is clipped, not divided.
  `:BuildMixTables`
  - Enables: one voice alone plays at full loudness.
  - Costs: 17,408 bytes of tables.

## What is unique

- A note to voice 3 turns mixing off; a note to voices 4–7 turns it on.
  `:SwitchMixing`
- DMA on restarts a mixed voice's sample. A new loop starts at the wrap.
  `:FakeDma`
- Loops under 32 words play silence, so short synth waves are mute on voices
  4–7. `:ShortLoopSilent`
- While mixing, the fade sets channel 3's volume. Mixed voices stay unfaded.
  `:FadeToChannel3`
- Wanted Team rewrote the mix loop: 254 instead of 268 cycles per byte.
  `:MixLoop`

## Open questions

- Which songs turn voice 3 back into a plain voice?
- Where did the original patch `killf1`–`killf4`? That code is gone.
