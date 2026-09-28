---
player: MusiclineEditor
template: 2
ideas:
  [
    wave-effect-chain,
    shared-sweeps,
    per-voice-positions,
    swing,
    seamless-wave-notes,
    timer-dma-wait,
    voice-mixing,
  ]
---

# Musicline Editor

Five wave effects rebuild a voice's wave every tick, each driven by its own
sweep.

## Context

| Fact      | Value                                                        |
| --------- | ------------------------------------------------------------ |
| Player    | `MusiclineEditor`                                            |
| Author    | Conny Cyréus and John Carehag                                |
| Year      | 1995                                                         |
| Code read | original: `ext/uade/amigasrc/players/other/musicline_editor` |
| Spec      | [specs/musicline.py](../specs/musicline.py)                  |

## Key ideas

- Transform, phase, mix, resonance and filter run in a chain every tick. Each
  writes its own buffer, and the channel plays the last one. `:TransformPlay`
  `:PhasePlay` `:MixPlay` `:ResonancePlay` `:FilterPlay`
  - Enables: a moving timbre from a few stored waves.
  - Costs: CPU high: up to five passes over 256 bytes per voice per tick.
- One sweep type drives every effect: start, speed, a bounce range, turns and a
  delay. `:Counter` `:InstPlay`
  - Enables: an "init" flag lets a sweep run on across notes of one instrument.
  - Enables: a "step" flag moves the sweep once per note instead.
- Each channel has its own position list, speed and `groove`, Musicline's term
  for swing. `:PlayVoice`
  - Enables: patterns of different lengths, and swing on one voice only.
- A new note on the same wave does not restart DMA. The wave plays on and takes
  the new pitch. `:DmaPlay`
  - Enables: wave notes without clicks, and without a phase reset.
- A second CIA timer waits for the stopped channels, instead of a busy loop.
  `:DmaPlay` `:DmaStart` `:DmaLoop`
  - Enables: the CPU works during the wait.
- In 8-channel mode, the CPU mixes two voices into each channel's buffer. The
  volume tables halve each voice, so the sum fits a byte. `:Play8Channels`
  `:MixVoice` `:MixAdd`
  - Enables: eight voices; see [voice mixing](../ideas/voice-mixing.md).
  - Costs: CPU high. The mix rate is fixed at period 126.

## Composer's view

The composer writes position lists, patterns and instruments. Musicline calls a
pattern a `part`.

| Aspect   | Answer                                                                | Source           |
| -------- | --------------------------------------------------------------------- | ---------------- |
| Notation | A position: a pattern number and a transpose of -16 to +15 semitones. | `:PlayVoice`     |
| Notation | A position can also end the list, jump back, or wait for rows.        | `:PlayVoice`     |
| Notation | A row: note, instrument and five effect words.                        | `:PlayPartFx`    |
| Notation | An instrument holds an envelope, vibrato, tremolo and five sweeps.    | `:InstPlay`      |
| Cost     | Jumps in position lists and in patterns only go back.                 | `:PlayVoice`     |
| Cost     | A pattern has at most 128 rows.                                       | `:PlayVoice`     |
| Cost     | A pattern that ends on its first row stops the song.                  | `:PlayVoice`     |
| Cost     | Wave effects need a loop of 16 to 256 bytes.                          | `:CheckWaveSize` |
| Cost     | An instrument ignores the transpose unless its flag says to follow.   | `:PlayInst`      |

## What is unique

- Each tick the chain starts again from the plain wave. Only the sweeps, and the
  filters' last sample, carry over. `:PlayEffects` `:FilterPlay`
- Phase squeezes the whole cycle into its first part. The rest holds the last
  value, or repeats the squeezed part. `:PhasePlay`
- Mix can add its own last output, rotated: feedback. `:MixPlay`
- Transform crossfades along a chain of up to six waves. `:TransformPlay`
- A wave is stored in five sizes, 256 down to 16 bytes. The instrument picks
  one. `:FixWaveLength`
- Pitch runs in 32 steps per semitone. A vibrato is the same interval at any
  pitch. `:NotePeriod` `:VibratoPlay`

## Open questions

- The plain filter multiplies its feedback by $f000 as a signed word, a small
  negative factor. Is this intended? `:FilterPlay`
- Below note 0, the pitch lookup reads before its table. Can a song reach it?
  `:NotePeriod`
- Which modules use 8-channel mode?
