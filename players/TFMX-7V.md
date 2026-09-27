---
player: TFMX-7V
base: TFMX-Pro
control: { sequencer: program, instrument: program }
themes: [mixing]
ideas: [voice-mixing]
streams: {}
---

# TFMX 7V

[TFMX Pro](TFMX-Pro.md) with seven voices: voices 4–7 are mixed into channel 3.

## Key ideas

- Voices 4–7 write to register sets in RAM, not to Paula. The macro engine stays
  unchanged. `data/annot/TFMX-7V.yaml:FakeRegisters`
- The mixer reads these sets as Paula would. DMA-on restarts the sample; a new
  loop starts at the wrap. `:FakeDma`
- Volume costs one table read per byte: 64 tables of 256 bytes. The sum of four
  is clipped, not divided. `:BuildMixTables`
- Channel 3's audio interrupt fills one tick's buffer, then runs the tick.
  `:MixTick` `:TickFromMixer`
- The buffer holds one tick at 50 Hz. A position command stretches it, so the
  tick slows. `:MixOn` `:CmdMixSlow`
- A note to voice 3 turns mixing off; voices 4–7 turn it on. `:SwitchMixing`
- Loops under 32 words play silence, so short synth waves are mute on voices
  4–7. `:ShortLoopSilent`

The readme calls it Jochen Hippel's mixer. Wanted Team rewrote the loop and kept
the original as comments.

At 16 kHz, 254 cycles per byte take about 57% of a 7.09 MHz 68000.

| Aspect            | Original `:OriginalMixLoop`   | Rewrite `:MixLoop`          |
| ----------------- | ----------------------------- | --------------------------- |
| Volume table pick | code patches each voice's lea | high byte of the table read |
| Stack pointer     | used for data                 | kept; one step on the stack |
| Bytes per pass    | 1                             | 2                           |
| Cycles per byte   | 268                           | 254                         |

## Generators

| Generator | Scope | States  | Writes    | Rate | Set by           | Note-on |
| --------- | ----- | ------- | --------- | ---- | ---------------- | ------- |
| Mixer     | song  | on, off | wave data | tick | Macro, Positions | keep    |

## Channel outputs

Channel 3, while mixing:

| Output    | Writers, in tick order |
| --------- | ---------------------- |
| Wave data | Mixer (edit)           |
| Sample    | Mixer (set)            |
| Period    | Mixer (set)            |
| Volume    | Fade (set)             |

## Interactions

| From      | To    | Event                                                |
| --------- | ----- | ---------------------------------------------------- |
| Mixer     | Macro | Each filled buffer runs one tick `:TickFromMixer`    |
| Positions | Mixer | `$EFFE 0003` sets the buffer length `:CmdMixSlow`    |
| Pattern   | Mixer | A note's voice turns mixing on or off `:NoteToVoice` |

## State

| Scope  | Fields                                                                    |
| ------ | ------------------------------------------------------------------------- |
| Voice  | voices 4–7: start, length, period, volume in RAM; offset, step, loop      |
| Global | mix rate, slow-down, two buffers and a silent one, volume and clip tables |

## Open questions

- Which songs turn voice 3 back into a plain voice?
- Where did the original patch `killf1`–`killf4`? That code is gone.
