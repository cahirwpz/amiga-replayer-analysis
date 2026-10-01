---
player: TFMX-7V
template: 2
base: TFMX-Pro
ideas: [voice-mixing]
---

# TFMX 7V

[TFMX Pro](TFMX-Pro.md) with seven voices: voices 4–7 are mixed into channel 3.
It is TFMX Pro's source built with its `on7voice` switch (guess).

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
  - Enables: seven voices with unchanged instrument program code.
  - Costs: voice 3 cannot play while the mix plays.
- The mixer sums voices 4–7 into one tick's buffer for channel 3. `:MixTick`
  `:MixLoop`
  - Enables: four extra voices on one channel.
  - Costs: CPU high. At 16 kHz, mixing takes about 60% of a 7.09 MHz 68000
    (estimate).
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

- A note to voice 3 turns mixing off. A note to voices 4–7 turns it on.
  `:SwitchMixing`
- DMA on after DMA off restarts a mixed voice's sample. A new loop starts at the
  wrap. `:FakeDma`
- Loops under 32 words play silence. Short waveforms are mute on voices 4–7.
  `:ShortLoopSilent`
- While mixing, the fade sets channel 3's volume. Mixed voices stay unfaded.
  `:FadeToChannel3`
- While mixing, a tick visits seven voices. A fade then moves 7/4 as fast.
  `:MixOn` `:MixOff`
- A program cannot wait for sample passes, on any voice. The program goes on to
  the next opcode. `:WaitLoopsOff`

## Open questions

- Which songs turn voice 3 back into a plain voice?
- Did the original use the `killf1`–`killf4` wrap hooks for the sample-pass wait
  (guess)?
