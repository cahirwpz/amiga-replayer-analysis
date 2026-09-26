---
player: SoundPlayer
source: wanted_team/SoundPlayer
code: uade
control: commands
themes: [tricks]
ideas: [attach-modes, per-voice-positions, game-sync-flags]
related: []
streams: { voice: 1 }
evidence: code
---

# SoundPlayer

Pattern commands switch Paula's attach modes, so one channel modulates the next.

## Key ideas

- Commands set attach bits: volume or period modulation of the next channel.
  `src/SoundPlayer_v1.asm:1359` `:1383`
- All voices read one list of rows, each from its own position. `:776` `:1041`
- Commands set flags that the game can read. `:1316` `:967`
- Instruments are IFF 8SVX samples: a first part, then a repeat part. `:684`
- [All commands](../details/SoundPlayer-commands.md).

## Streams

| Stream | Scope | Carries                   | Control          | Rate |
| ------ | ----- | ------------------------- | ---------------- | ---- |
| Track  | voice | note, instrument, command | loop, wait, jump | row  |

## Generators and interactions

- Waits and repeats count per voice, so the columns drift apart. `:1060`
- Volume slides by 1 every N ticks, until 0 or 63. `:1122`
- A row comes every 6 ticks; the speed is fixed. `:1019`
- A note stops its channel on the row tick and restarts it one tick later.
  `:1187` `:1086`

## State

| Scope      | Fields                                                     |
| ---------- | ---------------------------------------------------------- |
| Voice      | position, wait, repeat mark and count, volume, slide, hold |
| Instrument | first part start and length, repeat part start and length  |
| Global     | tick counter, 20 game flags, attach bits                   |

## Open questions

- Did the Lemmings songs use modulation for timbre or for effects?
- Command `DD` makes a voice replay its row forever. What for?
