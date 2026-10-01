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

- Transform, phase, mix, resonance and filter run in a chain every tick. The
  channel plays the last one's buffer. `:TransformPlay` `:PhasePlay` `:MixPlay`
  `:ResonancePlay` `:FilterPlay`
  - Enables: a moving timbre from a few stored waves.
  - Costs: CPU high. Up to five passes run over 256 bytes per voice per tick.
- One sweep type drives every effect. It has a start, a speed, a bounce range,
  turns and a delay. `:Counter` `:InstPlay`
  - Enables: a flag lets a sweep run on across notes of one instrument.
  - Enables: another flag moves the sweep once per note instead.
- Each channel has its own position list, speed and `groove`, Musicline's term
  for swing. `:PlayVoice`
  - Enables: patterns of different lengths, and swing on one voice only.
- A new note on the same wave does not restart DMA. The wave plays on and takes
  the new pitch. `:DmaPlay`
  - Enables: wave notes without clicks (inference).
- A second CIA timer waits for the stopped channels, instead of a busy-wait.
  `:DmaPlay` `:DmaStart` `:DmaLoop`
  - Enables: the CPU works during the wait.
- In 8-channel mode, the CPU mixes two voices into each channel's buffer. The
  volume tables halve each voice to keep the sum in a byte. `:Play8Channels`
  `:MixVoice` `:MixAdd`
  - Enables: eight voices. See [voice mixing](../ideas/voice-mixing.md).
  - Costs: CPU high. The mix rate is fixed at `MIX_PERIOD`.

## Composer's view

The composer writes position lists, patterns and instruments. Musicline calls a
pattern a `part`.

| Aspect   | Answer                                                                          | Source                  |
| -------- | ------------------------------------------------------------------------------- | ----------------------- |
| Notation | A position: a pattern number and a transpose of -16 to +15 semitones.           | `:PlayVoice`            |
| Notation | A position can also end the list, jump back, or wait for rows.                  | `:PlayVoice`            |
| Notation | A row: note, instrument and five effect words.                                  | `:PlayPartFx`           |
| Notation | An instrument holds an envelope, vibrato, tremolo and five sweeps.              | `:InstPlay`             |
| Notation | A note without an instrument number is legato. It changes only the pitch.       | `:PlayInst`             |
| Notation | An instrument's arpeggio table steps at its own speed and swing.                | `:ArpeggioPlay`         |
| Notation | An arpeggio step adds to the row's note, or sets a fixed note.                  | `:ArpeggioPlay`         |
| Notation | An arpeggio step can switch to another wave or sample.                          | `:ArpeggioPlay`         |
| Notation | An instrument can sweep its sample's loop between two points.                   | `:MoveLoop`             |
| Notation | A row command holds the envelope's sustain, or lets it go.                      | `:FxHoldSustain`        |
| Cost     | Jumps in position lists and in patterns only go back.                           | `:PlayVoice`            |
| Cost     | A pattern has at most 128 rows.                                                 | `:PlayVoice`            |
| Cost     | A pattern that ends on its first row stops the song.                            | `:PlayVoice`            |
| Cost     | Wave effects need a loop of 16 to 256 bytes.                                    | `:CheckWaveSize`        |
| Cost     | An instrument ignores the transpose unless its flag says to follow.             | `:PlayInst`             |
| Cost     | Without the hold flag, the envelope releases after its sustain time.            | `:AdsrPlay`             |
| Cost     | Empty first steps of an arpeggio table hold back the note-on.                   | `:PlayArpg` `:PlayInst` |
| Cost     | An instrument with a slide speed glides from its second note on (not modelled). | `:PlayInst`             |
| Cost     | When the loop sweep ends, a flag can silence the voice.                         | `:MoveLoop`             |

## What is unique

- Each tick the chain starts again from the plain wave. Only the sweeps, and the
  filters' last sample, carry over. `:PlayEffects` `:FilterPlay`
- Phase squeezes the whole cycle into its start. The rest holds the last value,
  or repeats the squeezed start. `:PhasePlay`
- Mix can feed its own last output back in, rotated. `:MixPlay`
- Transform crossfades along a chain of up to six waves. `:TransformPlay`
- A wave is stored in five sizes, 256 down to 16 bytes. The instrument picks
  one. `:FixWaveLength`
- Pitch runs in 32 steps per semitone. A vibrato is the same interval at any
  pitch. `:NotePeriod` `:VibratoPlay`

## Open questions

- The plain filter scales its fed-back value by $f000, a small negative signed
  factor. Is this intended? `:FilterPlay`
- Below note 0, the pitch lookup reads before its table. Can a song reach it?
  `:NotePeriod`
- Which modules use 8-channel mode?
