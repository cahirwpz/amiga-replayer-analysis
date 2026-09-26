---
player: TFMX-Pro
control: program
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

An instrument is a macro: a program with loops, calls and conditions.

## Key ideas

- 52 macro opcodes. `data/annot/TFMX-Pro.yaml:MacroOpcodes`
  [All opcodes](../details/TFMX-Pro-macros.md).
- Eight tracks, not bound to voices. Each note names its voice. `:TrackNote`
- Macros branch on note, volume or note-off. `:SplitByNote`
- Macros start notes on other voices. `:PlayOtherVoice`
- Macros rewrite macros. `:CopyToMacro` `:AddToMacro`
- IMS rebuilds a wave every tick from a resampled source. `:ImsRender`
- A riff plays macro bytes as notes, with random jumps. `:RiffPlay`

## Streams

| Stream     | Scope | Carries                            | Control                           | Rate          |
| ---------- | ----- | ---------------------------------- | --------------------------------- | ------------- |
| Positions  | song  | pattern, transpose per track       | loop, end                         | pattern end   |
| Pattern    | track | note, macro, voice, volume, detune | loop, jump, call, wait, end       | row           |
| Macro      | voice | sample, pitch, volume, generators  | loop, jump, call, wait, cond, end | tick          |
| Pitch riff | voice | note offset; macro bytes           | loop, jump                        | every N ticks |

## Generators and interactions

- Any track's pattern end moves all tracks on. `:PatternEnd`
- Riff echo: the next voice copies the pitch, quieter. `:RiffEcho`
- Failed byte checks write random bytes to memory (guess: anti-cracking).
  `:CheckByteTrap`

## State

| Scope      | Fields                                                          |
| ---------- | --------------------------------------------------------------- |
| Voice      | macro, step, wait, loop count, return; note, period, generators |
| Instrument | none; the macro holds everything                                |
| Global     | position, speed, per track: pattern, step, wait; fade           |

## Open questions

- Which songs use riffs and byte checks?
