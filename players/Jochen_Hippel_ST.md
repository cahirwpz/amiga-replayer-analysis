---
player: Jochen_Hippel_ST
control: commands
themes: [emulation]
ideas: [chip-emulation, register-shadow, log-volume-table]
streams: { song: 1, voice: 3 }
---

# Jochen Hippel ST

The Atari ST player runs as is. A layer turns its sound chip registers into
Paula settings.

## Key ideas

- The ST code writes chip registers into a shadow table.
  `data/annot/Jochen_Hippel_ST.yaml:RegisterShadow`
- Three chip channels go to Paula channels 0, 3 and 2. `:Play_Emu`
- Tone: a 4-byte square wave at 7 times the chip period. `:EmuChannel`
- Noise: a 1024-byte sample. `:EmuNoise`
- A table maps 16 log volume steps to Paula's linear volume. `:VolumeTable`
- Paula channel 1 plays digital samples. `:StartDigi`

## Streams

| Stream      | Scope | Carries                          | Control               | Rate          |
| ----------- | ----- | -------------------------------- | --------------------- | ------------- |
| Positions   | song  | pattern and transposes per voice | loop                  | pattern end   |
| Pattern     | voice | note, instrument, flags          | none                  | row           |
| Pitch list  | voice | note offset, chip mode, sample   | loop, jump, wait, end | tick          |
| Volume list | voice | volume                           | loop, wait, end       | every N ticks |

## Generators and interactions

- Tone wins over noise. `:EmuChannel`
- Tones play up to 23 cents sharp.
  [Accuracy](../details/Jochen_Hippel_ST-accuracy.md).
- The chip's envelope is not emulated. `:VolumeTable`
- The `SID` effect plays a 2-byte wave at the volume's level. `:SidPulse`

## State

| Scope      | Fields                                              |
| ---------- | --------------------------------------------------- |
| Voice      | position, pattern, list positions, speed, chip mode |
| Instrument | volume list and speed, vibrato, pitch list          |
| Global     | chip register shadow, noise rate, speed             |

## Open questions

- How close is the volume table to the chip's curve?
