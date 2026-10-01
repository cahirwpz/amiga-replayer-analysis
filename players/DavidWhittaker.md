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

A rate byte drops a share of the ticks. Game sound effects borrow a channel. The
music plays on in a copy of its registers.

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

- Each tick adds `Tempo` to a byte sum. When the sum passes 255, the music's
  tick is dropped. `:Play`
  - Enables: a speed between two whole speeds. Xenon 2 drops 20 of every 256
    ticks.
  - Costs: the dropped ticks make lengths uneven by one tick.
- Music writes each channel register to a shadow first. It writes to Paula only
  while no sound effect owns the channel. `:Shadow`
  - Enables: when the effect ends, the shadow goes to Paula. The music's current
    note sounds on, mid-note. `:EndEffect`
  - Costs: a synthetic effect start busy-waits three times for DMA. A sample
    effect start busy-waits twice. `:DmaWait`
- A synthetic effect rotates two 8-bit patterns. Their bits pick one of two
  period steps and one of two wave starts. `:SynthEffect` `:EffectOutput`
  - Enables: warbles, trills and tone-noise rhythms from a 24-byte record
    (inference).
- Each note restarts its volume list. The pitch list runs on across notes.
  `:NoteOn` `:Effects`
  - Enables: a fast arpeggio keeps its phase over a run of short notes.
  - Costs: the pitch list steps every tick. Its speed is fixed.
- Each sample stores its recording rate. The period is scaled by it, as in
  [Rob Hubbard](RobHubbard.md). `:InitSamples`

## Composer's view

The composer writes a position list per voice and patterns of bytes. State bytes
come before a note and stay until changed.

| Aspect   | Answer                                                                    | Source            |
| -------- | ------------------------------------------------------------------------- | ----------------- |
| Notation | A length byte: 1 to 32 units of `SPEED` ticks.                            | `:ReadCommand`    |
| Notation | An instrument byte picks one of 20 samples.                               | `:ReadCommand`    |
| Notation | A list byte picks one of 16 volume lists.                                 | `:ReadCommand`    |
| Notation | A list byte picks one of 16 pitch lists.                                  | `:ReadCommand`    |
| Notation | A note byte plays for the current length.                                 | `:NoteOn`         |
| Notation | `HOLD_NOTE` extends the note by one length.                               | `:StartNote`      |
| Notation | `REST` is silence for one length.                                         | `:Rest`           |
| Notation | `SLIDE`, `VIBRATO_ON`, `VIBRATO_OFF` shape the pitch.                     | `:Effects`        |
| Notation | `TRANSPOSE` shifts all voices.                                            | `:SetTranspose`   |
| Notation | `VOICE_TRANSPOSE` shifts one voice.                                       | `:VoiceTranspose` |
| Notation | `NEXT_PATTERN` plays the voice's next pattern.                            | `:NextPattern`    |
| Notation | `POSITIONS` swaps the voice's positions.                                  | `:SetPositions`   |
| Notation | `FADE` starts a fade.                                                     | `:SetFade`        |
| Notation | `SONG_END` stops the song.                                                | `:SongEnd`        |
| Cost     | DMA goes off one tick before each event, unless the event is `HOLD_NOTE`. | `:CountDown`      |
| Cost     | Every note ends in a gap of one tick.                                     | `:CountDown`      |
| Cost     | `SLIDE` ends at the next event.                                           | `:ReadStream`     |
| Cost     | The pitch list, `SLIDE` and vibrato add up on one period.                 | `:Effects`        |
| Cost     | Vibrato depth is in periods. Low notes get a smaller pitch change.        | `:Vibrato`        |
| Cost     | `SPEED` on one voice sets the speed of all voices.                        | `:SetSpeed`       |

## What is unique

- With `Ntsc` set, every sixth tick is dropped. A 60 Hz host plays at the 50 Hz
  speed. `:Play`
- A score fade ends the song when the volume reaches 0. `:Fade`
- A sample effect plays at its recorded rate. Its length and rate set its
  duration in ticks. `:InitEffectSamples`
- Xenon 2 detunes four samples by fixed amounts after it scales the periods.
  `:InitSamples`

## Open questions

- Where does the game load the effect waves and effect samples? Both start where
  `dw.ingame` ends.
- The ports rewrite a pulse wave in some versions (guess). Which modules use it?
  It may earn a delta card.
- Did Rob Hubbard and David Whittaker write the shared core together? See
  [the shared driver](../docs/shared-driver.md).
