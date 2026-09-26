---
player: TimFollin
control: { sequencer: program, instrument: none }
themes: [synthesis, tricks]
ideas:
  [
    bare-instruments,
    track-programs,
    pulse-width-sweep,
    semitone-glide,
    sample-chaining,
  ]
streams: { voice: 1 }
---

# Tim Follin

There is no instrument program: each voice's track sets modal parameters for
seven small generators.

## Key ideas

- An instrument is only a sample. Parameters stay set until the track changes
  them. `data/annot/TimFollin.yaml:StartSample`
  [All commands](../details/TimFollin-commands.md).
- Tracks call, return, jump and loop. `:CmdCall` `:CmdLoop`
- Instruments 0–3 are pulse waves. A sweep step rewrites one sample.
  `:PulseSweep`
- Portamento walks the note table: semitone steps. `:Portamento`
- A second sample follows one tick after note start. `:ChainSample`

## Streams

| Stream | Scope | Role      | Carries                                   | Control               | Rate     |
| ------ | ----- | --------- | ----------------------------------------- | --------------------- | -------- |
| Track  | voice | sequencer | note, length, instrument, generator setup | loop, jump, call, end | note end |

## Sequencer

| Aspect   | Value        | Label                 |
| -------- | ------------ | --------------------- |
| Time     | lengths      | `:PlayNote`           |
| Unit     | tick         | `:NoteTimer`          |
| Note end | length       | `:NoteTimer`          |
| Routing  | fixed        | `:ReadTrack`          |
| Reuse    | calls, loops | `:CmdCall` `:CmdLoop` |
| Tempo    | none         | `:Tick`               |

## Generators

| Generator   | Scope | States              | Writes    | Rate          | Set by | Note-on |
| ----------- | ----- | ------------------- | --------- | ------------- | ------ | ------- |
| Pulse sweep | voice | widen, narrow       | wave data | every N ticks | Track  | keep    |
| Envelope    | voice | attack, decay, hold | volume    | every N ticks | Track  | flag    |
| Vibrato     | voice | delay, swing        | period    | tick          | Track  | restart |
| Trill       | voice | lower, upper        | note      | every N ticks | Track  | restart |
| Portamento  | voice | move, rest          | note      | tick          | Track  | keep    |
| Chain       | voice | wait, done          | sample    | note-on       | Track  | restart |
| Gate        | voice | open, closed        | DMA       | note end      | Track  | restart |

## Channel outputs

| Output    | Writers, in tick order                                       |
| --------- | ------------------------------------------------------------ |
| Volume    | Envelope (set), Track (set)                                  |
| Period    | Vibrato (add), Trill (note), Portamento (note), Track (note) |
| Sample    | Chain (set), Track (set)                                     |
| Wave data | Pulse sweep (edit)                                           |
| DMA       | Chain (on), Gate (off), Track (on), Track (off)              |

## Interactions

| From        | To          | Event                                                            |
| ----------- | ----------- | ---------------------------------------------------------------- |
| Vibrato     | Trill       | With vibrato on, trill runs only during its delay `:Vibrato`     |
| Trill       | Portamento  | A trill step skips portamento for that tick `:Trill`             |
| Portamento  | Vibrato     | Each step resets the period from the table `:Portamento`         |
| Track       | Envelope    | Note-on restarts it only with the restart flag `:PlayNote`       |
| Pulse sweep | other voice | Voices on one pulse instrument edit the same bytes `:PulseSweep` |

- Without the gate flag, the channel keeps running at note-on: legato.
  `:GateOff`

## State

| Scope      | Fields                                                |
| ---------- | ----------------------------------------------------- |
| Voice      | track, call stack, loop, ticks left, note, generators |
| Instrument | sample; pulse of instruments 0–3 changes at runtime   |
| Global     | subsong, voice count                                  |

## Open questions

- `ResetPulse` writes at offset 2; playback starts at `$32`. Why? `:ResetPulse`
- Which game is this from? It has 15 fixed subsongs.
