---
player: SoundPlayer
control: { sequencer: commands, instrument: none }
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

| Stream | Scope | Role      | Carries                   | Control          | Rate |
| ------ | ----- | --------- | ------------------------- | ---------------- | ---- |
| Track  | voice | sequencer | note, instrument, command | loop, wait, jump | row  |

## Sequencer

| Aspect   | Value               | Label                             |
| -------- | ------------------- | --------------------------------- |
| Time     | rows, deltas        | `:RowTimer` `:CmdWait`            |
| Unit     | row                 | `:RowTimer`                       |
| Note end | next note, note-off | `:NoteStop` `:CmdStop`            |
| Routing  | fixed               | `:ReadRow`                        |
| Reuse    | loops               | `:CmdRepeatStart` `:CmdRepeatEnd` |
| Tempo    | none                | `:RowTimer`                       |

## Generators

| Generator    | Scope | States         | Writes | Rate          | Set by | Note-on |
| ------------ | ----- | -------------- | ------ | ------------- | ------ | ------- |
| Volume slide | voice | up, down, done | volume | every N ticks | Track  | keep    |
| Hold         | voice | hold, release  | sample | tick          | Track  | keep    |

## Channel outputs

| Output | Writers, in tick order          |
| ------ | ------------------------------- |
| Volume | Volume slide (add), Track (set) |
| Period | Track (note)                    |
| Sample | Hold (set), Track (set)         |
| DMA    | Track (on), Track (off)         |

## Interactions

| From  | To          | Event                                                     |
| ----- | ----------- | --------------------------------------------------------- |
| Track | other voice | Attach bits: modulate its volume or period `:CmdPerModOn` |
| Track | game        | Sets flags for the game `:CmdSetFlag`                     |

- Waits and repeats count per voice, so the columns drift apart. `:VoiceWait`
- A row comes every 6 ticks. `:RowTimer`
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
- `DD` parks a voice on its row until a restart. `:CmdStepBack` Why?
