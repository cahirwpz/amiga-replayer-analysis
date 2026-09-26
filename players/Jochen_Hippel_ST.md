---
player: Jochen_Hippel_ST
control: { sequencer: commands, instrument: commands }
themes: [emulation]
ideas: [chip-emulation, register-shadow, log-volume-table]
streams: { voice: 4 }
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

| Stream      | Scope | Role       | Carries                                   | Control               | Rate          |
| ----------- | ----- | ---------- | ----------------------------------------- | --------------------- | ------------- |
| Positions   | voice | sequencer  | pattern, transposes, speed, volume offset | loop                  | pattern end   |
| Pattern     | voice | sequencer  | note, instrument, slide, length           | end                   | note end      |
| Pitch list  | voice | instrument | note offset, chip mode, sample, vibrato   | loop, jump, wait, end | tick          |
| Volume list | voice | instrument | volume                                    | loop, wait, end       | every N ticks |

## Sequencer

| Aspect   | Value     | Label            |
| -------- | --------- | ---------------- |
| Time     | lengths   | `:SetNoteLength` |
| Unit     | row       | `:Play`          |
| Note end | next note | `:ReadNote`      |
| Routing  | fixed     | `:InitSong`      |
| Reuse    | patterns  | `:NextPosition`  |
| Tempo    | speed     | `:NextPosition`  |

## Generators

| Generator | Scope | States          | Writes | Rate | Set by                 | Note-on |
| --------- | ----- | --------------- | ------ | ---- | ---------------------- | ------- |
| Vibrato   | voice | delay, up, down | period | tick | instrument, Pitch list | restart |
| Slide     | voice | on, off         | period | tick | Pattern, Pitch list    | restart |

## Channel outputs

These are chip settings. The layer copies them to Paula once per tick.

| Output | Writers, in tick order                        |
| ------ | --------------------------------------------- |
| Volume | Volume list (set), Positions (add)            |
| Period | Pitch list (note), Vibrato (add), Slide (add) |
| Sample | Pitch list (set)                              |
| DMA    | Pitch list (on), Pitch list (off)             |

## Interactions

| From       | To          | Event                                                      |
| ---------- | ----------- | ---------------------------------------------------------- |
| Pattern    | Pitch list  | A note with bit 7 set keeps both lists running `:ReadNote` |
| Pitch list | Volume list | `E2` restarts it `:RestartVolumeList`                      |
| Pitch list | other voice | The chip has one noise period for all `:NoisePeriod`       |
| Positions  | other voice | Voice 0 counts the song length for all `:NextPosition`     |

- Each voice steps its own position at its own pattern end. `:NextPosition`
- Tone wins over noise. `:EmuChannel`
- Tones play up to 23 cents sharp.
  [Accuracy](../details/Jochen_Hippel_ST-accuracy.md).
- The chip's envelope is not emulated. `:VolumeTable`
- The `SID` effect plays a 2-byte wave at the volume's level. `:SidPulse`

## State

| Scope      | Fields                                               |
| ---------- | ---------------------------------------------------- |
| Voice      | position, pattern, note length, list positions, mode |
| Instrument | volume list and speed, vibrato, pitch list           |
| Global     | chip register shadow, speed                          |

## Open questions

- How close is the volume table to the chip's curve?
