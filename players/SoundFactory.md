---
player: SoundFactory
template: 2
ideas:
  [
    voice-streams,
    stream-sync-counter,
    inline-instruments,
    wave-sweeps,
    length-tuned-waves,
  ]
---

# SoundFactory

Each voice runs its own stream of notes and opcodes. The streams sync through
one shared counter.

## Context

| Fact      | Value                                                             |
| --------- | ----------------------------------------------------------------- |
| Player    | `SoundFactory`                                                    |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/Soundfactory` |
| Spec      | [specs/sound_factory.py](../specs/sound_factory.py)               |

## Key ideas

- A song gives each voice its own stream: notes with lengths, and opcodes.
  Streams call, jump and loop, on a stack per voice. `:ReadStream` `:OpCall`
  `:OpLoopStart`
  - Enables: each part repeats at its own rhythm, with no rows.
  - Costs: the composer keeps the voices in step by hand.
- One voice counts a shared counter up. Another waits until it holds a value.
  `:OpSignal` `:OpWaitSignal`
  - Enables: parts of different lengths meet again at a cue.
  - Costs: a waiting voice reads its opcode again every tick.
- An instrument is defined inside a stream. The player registers it when the
  stream passes it. `:OpDefineInstrument`
  - Enables: sound data sits next to the notes that use it.
  - Costs: before a stream passes it, the number plays a default instrument.
- Effect opcodes write into the instrument, not into the voice. `:OpVibrato`
  `:OpAdsr`
  - Enables: one opcode changes the sound on every voice that plays it.
  - Costs: two voices cannot play one instrument with different effects.
- Phasing and a low-pass filter rebuild a short wave into a buffer per voice.
  Each sweeps its setting between two limits. `:WaveEffects` `:BuildPhasing`
  `:BuildFilter`
  - Enables: a moving timbre from one short wave.
  - Costs: CPU medium: each step rebuilds the whole wave. A wave holds at most
    256 bytes.
- A wave's period divides by its length and multiplies by its cycle count.
  `:NotePeriod`
  - Enables: waves of any length play in tune.

## Composer's view

The composer writes one stream per voice, for up to 16 songs. A note carries its
length in ticks. Instruments and their effects are opcodes in the streams.

| Aspect   | Answer                                                           | Source          |
| -------- | ---------------------------------------------------------------- | --------------- |
| Notation | A note: one byte, then a length word.                            | `:NoteOn`       |
| Notation | Bit 15 of the length keeps the envelope running.                 | `:NoteOn`       |
| Notation | An opcode byte from $80, then its arguments.                     | `:ReadStream`   |
| Notation | A song: a voice mask and four stream offsets.                    | `:InitSong`     |
| Cost     | A loop of N plays N times. A count of 0 plays 256 times.         | `:OpLoopEnd`    |
| Cost     | A sync takes one opcode on each side.                            | `:OpSignal`     |
| Cost     | The release starts at half the note's length, unless held.       | `:AutoRelease`  |
| Cost     | Phasing and the filter need a wave of 256 bytes or less.         | `:BuildPhasing` |
| Cost     | A fade is an opcode in a stream. A fade-out to 0 stops the song. | `:OpFadeOut`    |

## What is unique

- Attack and decay each take their setting in ticks, whatever the levels.
  `:Attack` `:Decay`
- The release takes twice its setting in ticks, from any sustain level.
  `:Release`
- A one-shot sample with a loop plays its tail once the release starts.
  `:AutoRelease`
- One tick before the next event, DMA goes off. This happens only for periods of
  429 and above. `:EarlyStop`
- An octave flip jumps the pitch an octave up and back, at a set speed.
  `:OctaveFlip`

## Open questions

- Which modules use the shared counter, and for what? `:OpWaitSignal`
- Why does the early DMA stop skip periods below 429? A guess: short periods
  restart in time anyway. `:EarlyStop`
- Who wrote the Soundfactory editor, and when? The replay names only Profiteam.
