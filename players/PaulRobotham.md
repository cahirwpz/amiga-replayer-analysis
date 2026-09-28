---
player: PaulRobotham
template: 2
ideas:
  [
    per-voice-streams,
    packed-lengths,
    length-remainder,
    period-scaled-vibrato,
    effect-voice-limit,
  ]
---

# Paul Robotham

Each voice reads its own note stream. Lengths are packed into one byte.

## Context

| Fact      | Value                                                             |
| --------- | ----------------------------------------------------------------- |
| Player    | `PaulRobotham`                                                    |
| Author    | Paul Robotham                                                     |
| Year      | 1994                                                              |
| Game      | Starlord                                                          |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/PaulRobotham` |
| Spec      | [specs/paul_robotham.py](../specs/paul_robotham.py)               |

## Key ideas

- Each voice reads one byte stream, with no patterns. Loops nest per voice.
  `:ReadStream` `:LoopStart` `:LoopEnd`
  - Enables: any rhythm, with no row grid.
  - Costs: a part that two voices play is stored twice.
- A length byte holds a 5-bit value and a 3-bit shift. `:ReadLength`
  - Enables: one byte covers 1 to 3968 pulses.
  - Costs: a length with more than five significant bits needs a tie.
- The pulse length scales pulses to ticks. Each voice keeps the remainder of
  that division for its next note. `:ReadLength` `:SetPulseLength`
  - Enables: any tempo, and voices never drift apart.
- Vibrato adds a share of the period, not a fixed amount. `:Vibrato`
  - Enables: the vibrato has the same interval on low and high notes.
- A sound effect takes a music voice, whose stream runs on muted. `:MutedVoice`
  `:EffectTick`
  - Enables: the music comes back in time, at the voice's next note.
- The song limits effects to voices 0 to N. An effect takes the voice with the
  fewest effect ticks left. `:EffectVoices` `:StartEffect`
  - Enables: the composer keeps effects off key voices (inference).
  - Costs: the effect call is commented out, so UADE never runs it.

## Composer's view

The composer writes one stream per voice, instruments, envelope and vibrato
tables. Voice settings hold until a command changes them.

| Aspect   | Answer                                                                    | Source                      |
| -------- | ------------------------------------------------------------------------- | --------------------------- |
| Notation | A note byte, 1 to 126, then a length byte.                                | `:ReadStream`               |
| Notation | Byte $7F, then a length byte: a tie.                                      | `:ReadStream`               |
| Notation | A length byte: bits 0-4 are a value, bits 5-7 shift it left.              | `:ReadLength`               |
| Notation | A command: a byte from $80, then 0 to 2 argument bytes.                   | `:RunCommand`               |
| Notation | A repeat: a loop start with a count, the part, then a loop end.           | `:LoopStart` `:LoopEnd`     |
| Notation | A mode byte per voice: legato, keep the envelope, keep the vibrato phase. | `:SetMode`                  |
| Notation | Byte 0 ends the voice for good.                                           | `:VoiceEnd`                 |
| Cost     | A length that rounds to 0 ticks stalls its voice for 65 536 ticks.        | `:ReadLength`               |
| Cost     | An arpeggio is written out as notes. No command plays one.                | `:RunCommand`               |
| Cost     | A new instrument turns legato mode off. The mode must be set again.       | `:SetInstrument`            |
| Cost     | Every voice waits 10 ticks before its first byte.                         | `:InitSong`                 |
| Cost     | One command in any stream fades the whole song.                           | `:FadeMaster` `:MasterFade` |

## What is unique

- In legato mode, a note after an instrument change starts the new instrument at
  its loop. The attack part is skipped. `:SwapInstrument`
- The stream starts a fade: a release that lasts until a note restarts the
  sample. `:FadeOut` `:FadeStep` `:EnvelopeTick`
- An envelope with no jump repeats every 64 ticks. `:EnvelopeTick`
- A tie restarts neither the envelope nor the vibrato. `:ReadLength`
- The pulse length is global. A larger value plays slower. `:SetPulseLength`

## Open questions

- How many pulses make a quarter note? `:ReadLength`
- A new effect replaces a looping effect before a free voice. Did the game stop
  looping effects first? `:StartEffect`
- Which tool wrote the streams? Pulses suggest a MIDI sequencer (guess).
- Who writes the voice mask? This source never does. `:StartDma`
