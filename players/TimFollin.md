---
player: TimFollin
control: program
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

Instruments are bare samples; each voice's track program sets all expression.

## Key ideas

- An instrument is only a sample. Track commands set the rest.
  `data/annot/TimFollin.yaml:StartSample`
  [All commands](../details/TimFollin-commands.md).
- Tracks call, return, jump and loop. `:CmdCall` `:CmdLoop`
- Instruments 0–3 are pulse waves. A sweep step rewrites one sample.
  `:PulseSweep`
- Portamento walks the note table: semitone steps. `:Portamento`
- A second sample follows one tick after note start. `:ChainSample`

## Streams

| Stream | Scope | Carries                                   | Control               | Rate     |
| ------ | ----- | ----------------------------------------- | --------------------- | -------- |
| Track  | voice | note, length, instrument, generator setup | loop, jump, call, end | note end |

## Generators and interactions

- Envelope: attack to 63, decay to sustain, hold. `:Envelope`
- Vibrato in period steps, after a delay; or a one-way sweep. `:Vibrato`
- Trill: the note alternates with a higher note. `:Trill`
- Flag bit 7 stops the channel one tick early, to restart the sample. `:GateOff`

## State

| Scope      | Fields                                                |
| ---------- | ----------------------------------------------------- |
| Voice      | track, call stack, loop, ticks left, note, generators |
| Instrument | sample; pulse of instruments 0–3 changes at runtime   |
| Global     | subsong, voice count                                  |

## Open questions

- `ResetPulse` writes at offset 2; playback starts at `$32`. Why? `:ResetPulse`
- Which game is this from? It has 15 fixed subsongs.
