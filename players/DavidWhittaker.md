---
player: DavidWhittaker
template: 2
ideas:
  [
    replay-in-module,
    fractional-tempo,
    register-shadow,
    effects-steal-voices,
    bit-pattern-effects,
    pitch-list,
    volume-list,
    sample-rate-tune,
  ]
---

# David Whittaker

A tempo byte drops a share of the ticks. Game sound effects borrow a channel;
the music plays on in a copy of its registers.

## Context

| Fact      | Value                                                   |
| --------- | ------------------------------------------------------- |
| Player    | `DavidWhittaker`                                        |
| Author    | David Whittaker                                         |
| Year      | 1989                                                    |
| Game      | Xenon 2 Megablast                                       |
| Code read | ira: `ext/c-flod/neoart/flod/whittaker`                 |
| Spec      | [specs/david_whittaker.py](../specs/david_whittaker.py) |

## Key ideas

- Each tick adds `Tempo` to a byte sum. A carry drops the music's tick. `:Play`
  - Enables: a tempo between two whole speeds. Xenon 2 drops 20 of every 256
    ticks.
  - Costs: the dropped ticks make lengths uneven by one tick.
- Music writes each channel register to a shadow first. It writes to Paula only
  while no sound effect owns the channel. `:Shadow`
  - Enables: when the effect ends, the shadow goes to Paula. The music's current
    note sounds on, mid-note. `:EndEffect`
  - Costs: each effect start busy-waits three times for DMA. `:DmaWait`
- A synthetic effect rotates two 8-bit patterns. Their bits pick one of two
  period steps and one of two wave starts. `:SynthEffect` `:EffectOutput`
  - Enables: warbles, trills and tone-noise rhythms from a 24-byte record.
- Each note restarts its volume list. The pitch list runs on across notes.
  `:NoteOn` `:Effects`
  - Enables: a fast arpeggio keeps its phase over a run of short notes.
  - Costs: the pitch list steps every tick. Its speed is fixed.
- Each sample stores its recording rate. The period is scaled by it, as in
  [Rob Hubbard](RobHubbard.md). `:InitSamples`

## Composer's view

The composer writes a position list per voice and patterns of bytes. State bytes
come before a note and stay until changed.

| Aspect   | Answer                                                               | Source          |
| -------- | -------------------------------------------------------------------- | --------------- |
| Notation | A length byte: 1 to 32 units of `SPEED` ticks.                       | `:ReadCommand`  |
| Notation | An instrument byte picks one of 20 samples.                          | `:ReadCommand`  |
| Notation | A list byte picks one of 16 volume lists or 16 pitch lists.          | `:ReadCommand`  |
| Notation | A note byte plays for the current length.                            | `:NoteOn`       |
| Notation | `HOLD_NOTE` extends the note by one length. `REST` is silence.       | `:StartNote`    |
| Notation | `SLIDE`, `VIBRATO_ON`, `VIBRATO_OFF` shape the pitch.                | `:Effects`      |
| Notation | `TRANSPOSE` shifts all voices. `VOICE_TRANSPOSE` shifts one.         | `:ReadCommand`  |
| Notation | `NEXT_PATTERN` goes on. `POSITIONS` swaps the voice's position list. | `:SetPositions` |
| Notation | `FADE` starts a fade. `SONG_END` stops the song.                     | `:SetFade`      |
| Cost     | DMA goes off one tick before each event, unless it is `HOLD_NOTE`.   | `:CountDown`    |
| Cost     | Every note ends in a gap of one tick.                                | `:CountDown`    |
| Cost     | `SLIDE` lasts one note: each event clears it.                        | `:ReadStream`   |
| Cost     | `SPEED` on one voice sets the speed of all voices.                   | `:SetSpeed`     |

## What is unique

- With `Ntsc` set, every sixth tick is dropped. A 60 Hz host then plays at the
  50 Hz speed. `:Play`
- A score fade ends the song when the volume reaches 0. `:Fade`
- A sample effect plays at its recorded rate. Its length and rate set its
  duration in ticks. `:InitEffectSamples`
- Xenon 2 detunes four samples by fixed amounts after it computes the tunes.
  `:InitSamples`
- The replay has no wave writes. The Xenon 2 version builds no synth sound.

## Open questions

- Where does the game load the effect waves and effect samples? Both start where
  `dw.ingame` ends.
- The ports rewrite a pulse wave in some versions (inference). Which modules use
  it? It may earn a delta card.
- [Fred](Fred.md) shares this period table and vibrato. Rob Hubbard's table
  starts one octave up. Is there one source?
