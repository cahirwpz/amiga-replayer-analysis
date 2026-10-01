---
player: Jochen_Hippel_ST
template: 2
ideas:
  [chip-emulation, register-shadow, log-volume-table, pitch-list, volume-list]
---

# Jochen Hippel ST

The ST replay runs as is. A layer turns its sound chip registers into Paula
settings.

## Context

| Fact      | Value                                                                 |
| --------- | --------------------------------------------------------------------- |
| Player    | `Jochen_Hippel_ST`                                                    |
| Author    | Jochen Hippel                                                         |
| Family    | Jochen Hippel                                                         |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/Jochen_Hippel_ST` |
| Spec      | [specs/jochen_hippel_st.py](../specs/jochen_hippel_st.py)             |

## Key ideas

- The ST replay writes chip registers into a copy in RAM. Each tick, a layer
  sets Paula channels 0, 3 and 2 from it. `:Play` `:EmuTick`
  - Enables: ST songs play with their own replay and data.
  - Costs: tone and noise on one channel lose the noise.
- A tone is a looped 4-byte square wave. It restarts only when the channel
  starts a tone. `:EmuTone`
  - Enables: a new pitch keeps the wave's phase.
  - Costs: most tones play up to 23 cents sharp.
- Noise is a looped 1024-byte random sample at one of 32 periods. `:EmuNoise`
  - Costs: the noise pitch moves the wrong way.
- A table maps 16 logarithmic volume steps to Paula volume. `:EmuChannel`
  - Costs: the chip's envelope gives a fixed volume of 32.
- The pitch list runs every tick. The volume list runs every N ticks.
  `:PitchList` `:VolumeList`
  - Enables: drums that switch between tone and noise, as data.
- Paula channel 1 plays samples. `:StartDigi` `:EmuDigi`
  - Enables: a fourth voice.
  - Costs: while off, it restarts an empty sample every tick.
- Channel 1 can play a 2-byte pulse wave (`SID`) at another voice's pitch.
  `:SidVoice` `:SidPulse`
  - Enables: a fourth tone voice.
  - Costs: it restarts every tick.

## Composer's view

The composer writes positions, patterns, instruments and pitch lists. An
instrument names its pitch list and holds its volume list.

| Aspect   | Answer                                                                         | Source                   |
| -------- | ------------------------------------------------------------------------------ | ------------------------ |
| Notation | A note: a note byte, a flags byte with the instrument, an optional third byte. | `:ReadNote`              |
| Notation | A note's third byte can pick its pitch list instead of the instrument's.       | `:ReadNote`              |
| Notation | `SET_LENGTH` sets the length of later notes in rows.                           | `:ReadPattern`           |
| Notation | `REST` sets the length and reads no note. The last note's lists run on.        | `:Rest`                  |
| Notation | A position: pattern, transpose, instrument transpose and flags, per voice.     | `:NextPosition`          |
| Notation | The position flag `VOLUME_OFFSET` lowers the voice's volume.                   | `:NextPosition`          |
| Notation | The position flag `SET_SPEED` sets the speed.                                  | `:NextPosition`          |
| Notation | An instrument: volume speed, pitch list, vibrato, then the volume list.        | `:Instrument`            |
| Cost     | A snare switches between noise and tone in its pitch list.                     | `:NoiseOnly` `:ToneOnly` |
| Cost     | A pitch list byte with `FIXED` set ignores the note and the transposes.        | `:PitchToPeriod`         |
| Cost     | A `LEGATO` note changes the pitch and keeps both lists running.                | `:ReadNote`              |
| Cost     | A new note keeps the old volume until its volume list's first step.            | `:VolumeList`            |
| Cost     | `RESTART_VOLUME` in the pitch list makes the volume list step at once.         | `:RestartVolumeList`     |
| Cost     | The patterns of all three voices must last equally long.                       | `:NextPosition`          |

## What is unique

- Each voice steps to its next position at its own pattern end. Voice 0 counts
  the positions for all. `:NextPosition` `:RestartSong`
- Rows are read after the lists. A new note first sounds on the next tick.
  `:Play`
- The three voices share one noise register. The last voice to set it wins.
  `:NoisePeriod`
- In noise mode, the noise pitch follows the note. `:PitchToPeriod`
- `MMME` modules scale vibrato and slide by the period. `:ScaledVibrato`
  `:ScaledSlide`
- Older modules double the vibrato for each octave down. They slide in period
  units. `:OctaveVibrato` `:PeriodSlide`
- A silent chip channel restarts an empty sample every tick. Each restart
  busy-waits for at least three scanlines. `:EmuChannel` `:NotePlay`

## Open questions

- How close is the volume table to the chip's curve? `:EmuChannel`
- Which Hippel versions need `TypePlay`? It makes `FIRST_NOTE` to
  `LATER_OPCODES` opcodes. `:PitchCommands`
