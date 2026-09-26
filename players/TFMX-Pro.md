---
player: TFMX-Pro
control: { sequencer: program, instrument: program }
themes: [synthesis, tricks]
ideas:
  [
    macro-instruments,
    tracks-not-voices,
    self-modifying-macros,
    resampling-synthesis,
    random-riffs,
  ]
streams: { song: 1, track: 1, voice: 2 }
---

# TFMX Pro

An instrument is a macro: a program that shapes one note.

## Key ideas

- 52 opcodes, with branches on note, volume or note-off.
  `data/annot/TFMX-Pro.yaml:MacroOpcodes` `:SplitByNote`
  [All opcodes](../details/TFMX-Pro-macros.md).
- Eight tracks share the voices; each note names its voice. `:TrackNote`
- Macros rewrite other macros. `:CopyToMacro` `:AddToMacro`
- IMS rebuilds a wave every tick from a resampled source. `:ImsRender`
- A riff plays macro bytes as notes, with random jumps. `:RiffPlay`

## Streams

| Stream     | Scope | Role       | Carries                            | Control                           | Rate          |
| ---------- | ----- | ---------- | ---------------------------------- | --------------------------------- | ------------- |
| Positions  | song  | sequencer  | pattern, transpose per track       | loop, end                         | pattern end   |
| Pattern    | track | sequencer  | note, macro, voice, volume, detune | loop, jump, call, wait, end       | row           |
| Macro      | voice | instrument | sample, pitch, volume, generators  | loop, jump, call, wait, cond, end | tick          |
| Pitch riff | voice | instrument | note offset; macro bytes           | loop, jump                        | every N ticks |

## Sequencer

| Aspect   | Value                        | Label                    |
| -------- | ---------------------------- | ------------------------ |
| Time     | deltas                       | `:TrackStart` `:pwait`   |
| Unit     | row                          | `:Sequencer`             |
| Note end | next note, note-off, program | `:pkeyup` `:WaitNoteOff` |
| Routing  | per note                     | `:NoteToVoice`           |
| Reuse    | patterns, calls, loops       | `:PatternCall` `:ploop`  |
| Tempo    | speed, timer                 | `:speedsong`             |

## Generators

| Generator   | Scope | States      | Writes    | Rate          | Set by             | Note-on |
| ----------- | ----- | ----------- | --------- | ------------- | ------------------ | ------- |
| Start sweep | voice | up, down    | sample    | tick          | Macro              | program |
| IMS         | voice | off, render | wave data | tick          | Macro              | program |
| Vibrato     | voice | up, down    | period    | tick          | Macro, Pattern     | program |
| Portamento  | voice | glide, done | period    | every N ticks | Macro, Pattern     | program |
| Envelope    | voice | slide, done | volume    | every N ticks | Macro, Pattern     | program |
| Fade        | song  | slide, done | volume    | every N ticks | Pattern, Positions | keep    |

## Channel outputs

| Output    | Writers, in tick order                                                            |
| --------- | --------------------------------------------------------------------------------- |
| Sample    | Macro (set), Start sweep (add)                                                    |
| Wave data | IMS (edit)                                                                        |
| Period    | Macro (note), Macro (set), Vibrato (scale), Portamento (scale), Pitch riff (note) |
| Volume    | Macro (set), Envelope (add), Fade (scale)                                         |
| DMA       | Macro (on), Macro (off), Positions (off)                                          |

## Interactions

| From       | To          | Event                                                            |
| ---------- | ----------- | ---------------------------------------------------------------- |
| Pattern    | Macro       | Note-on restarts it; note-off clears its key flag `:NoteToVoice` |
| Pattern    | other track | Starts a pattern `:StartOtherTrack`                              |
| Macro      | other voice | Note-on or note-off `:PlayOtherVoice`                            |
| Macro      | game        | Sets flags for the game `:msendflag`                             |
| game       | Macro       | Sound effects lock voices by priority `:NoteToVoice`             |
| Portamento | Vibrato     | While gliding, vibrato writes no period `:Vibrato`               |
| Pitch riff | other voice | Echo at 5/8 volume `:RiffEcho`                                   |
| IMS        | other voice | Negated copy into its buffer `:ImsRender`                        |

- Any pattern end moves all tracks on. `:PatternEnd`
- Macros clear or pause generators. `:mclear` `:mdmaon`
- Failed byte checks corrupt memory (guess: anti-cracking). `:CheckByteTrap`

## State

| Scope      | Fields                                                                |
| ---------- | --------------------------------------------------------------------- |
| Voice      | macro, step, wait, loop, return, key flag, priority, note, generators |
| Instrument | none                                                                  |
| Global     | position, speed, track steps and waits, fade                          |

## Open questions

- Which songs use riffs and byte checks?
