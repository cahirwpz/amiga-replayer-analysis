---
player: SoundPlayer
control: commands
themes: [tricks]
ideas: [attach-modes, per-voice-positions, game-sync-flags]
streams: { voice: 1 }
---

# SoundPlayer

Pattern commands switch Paula's attach modes, so one channel modulates the next.

## Key ideas

- Commands set attach bits: volume or period modulation of the next channel.
  `data/annot/SoundPlayer.yaml:CmdVolModOn` `:CmdVolModOff`
- All voices read one list of rows, each from its own position. `:InitVoices`
  `:ReadRow`
- Commands set flags that the game can read. `:CmdSetFlag` `:GameReadsFlag`
- Instruments are IFF 8SVX samples: a first part, then a repeat part.
  `:LoadInstrument`
- [All commands](../details/SoundPlayer-commands.md).

## Streams

| Stream | Scope | Carries                   | Control          | Rate |
| ------ | ----- | ------------------------- | ---------------- | ---- |
| Track  | voice | note, instrument, command | loop, wait, jump | row  |

## Generators and interactions

- Waits and repeats count per voice, so the columns drift apart. `:VoiceWait`
- Volume slides by 1 every N ticks, until 0 or 63. `:VolumeSlide`
- A row comes every 6 ticks; the speed is fixed. `:RowTimer`
- A note stops its channel on the row tick and restarts it one tick later.
  `:NoteStop` `:NoteRestart`

## State

| Scope      | Fields                                                     |
| ---------- | ---------------------------------------------------------- |
| Voice      | position, wait, repeat mark and count, volume, slide, hold |
| Instrument | first part start and length, repeat part start and length  |
| Global     | tick counter, 20 game flags, attach bits                   |

## Open questions

- Did the Lemmings songs use modulation for timbre or for effects?
- Command `DD` makes a voice replay its row forever. What for?
