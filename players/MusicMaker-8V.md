---
player: MusicMaker-8V
template: 2
ideas: [voice-mixing, interrupt-clock, self-modifying-mixer, sample-envelope]
---

# MusicMaker 8V

Eight voices on four channels: each channel mixes two voices at the higher
voice's own period.

## Context

| Fact      | Value                                                   |
| --------- | ------------------------------------------------------- |
| Player    | `MusicMaker-8V`                                         |
| Author    | Thomas Winischhofer                                     |
| Family    | MusicMaker                                              |
| Code read | original: `ext/uade/amigasrc/players/other/music_maker` |
| Spec      | [specs/music_maker_8v.py](../specs/music_maker_8v.py)   |

## Key ideas

- Voices 2n and 2n+1 share channel n. The channel plays at the higher note's
  period, so that voice needs no resampling. `:MixPair` `:MixSpan`
  - Enables: the higher note of each pair keeps its full quality.
  - Costs: high notes raise the mix rate, and with it the CPU load.
- The louder voice sets the channel volume. A table scales the quieter voice by
  the ratio of the two volumes. `:VolumeTable`
  - Enables: one table read per byte, for one voice only.
  - Costs: every sample byte is halved at load, so voices lose 1 bit.
    `:HalveSamples`
- Each buffer lasts one tick at its own period. The replay runs when all four
  channels have started their buffers. `:AudioInterrupt` `:BufferLength`
  - Enables: no timer, and four channels at four rates stay in step.
  - Costs: the replay busy-waits for the last channel. `:CorrectDrift`
- On a 68000, the mixer writes its own step instructions for each pair of
  periods. It keeps one unrolled copy per case. `:BuildStepPattern` `:PickMixer`
  - Enables: no step arithmetic in the inner loop.
  - Costs: a 68020 or later would need a cache flush. It uses a slower mixer
    instead. `:DbraStep`
- An envelope table changes volume and pitch by sample position, one entry per
  40 bytes. The format calls it `HULL`. `:HullVolume` `:HullStep`
  - Enables: an envelope that stays with the sample at any pitch.

## Composer's view

The composer writes a position list per voice and patterns of 3-byte events. The
format calls a pattern `macro`.

| Aspect   | Answer                                                                   | Source                       |
| -------- | ------------------------------------------------------------------------ | ---------------------------- |
| Notation | An event byte: instrument and volume, or a command.                      | `:ReadEvent`                 |
| Notation | A note byte: loop flag, filter state, note.                              | `:ReadEvent`                 |
| Notation | A length byte: legato flag, filter flag, length.                         | `:ReadEvent`                 |
| Notation | A position word: a pattern number, `PAUSE` or `END_OF_LIST`.             | `:NextPattern`               |
| Notation | A pattern that starts with `CONTINUE` holds the last note on.            | `:NextEvent`                 |
| Notation | 64 notes: quarter tones up to period 170, then semitones.                | `:StartNote`                 |
| Cost     | Each note chooses: its sample plays once, or the attack and then a loop. | `:StartNote`                 |
| Cost     | An event names 16 instruments. Others need a bank event before it.       | `:InstrumentBank`            |
| Cost     | Volume has 16 steps.                                                     | `:StartNote`                 |
| Cost     | Every event takes 2 to 128 ticks, in steps of 2. Commands too.           | `:ReadEvent`                 |
| Cost     | A speed command can only make the song faster.                           | `:SetSpeed`                  |
| Cost     | Vibrato and tremolo are 4-tick triangles. Only the step size varies.     | `:PeriodSlide` `:Modulation` |

## What is unique

- A note can cut its sample and keep the rest. A later event plays that rest.
  `:BreakNote` `:ResumeBreak`
- With loudness on, high notes play quieter, down to half volume. `:Loudness`
- The fast mixer caps the mix rate. Periods up to the song's limit play slower
  and skip bytes. `:MixPair`
- A late channel gets a shorter next buffer, by up to 5 bytes. `:CorrectDrift`

## Open questions

- Which songs use the quarter tones?
- Why does the table make high notes quieter? Hearing, or aliasing (guess)?
  `:Loudness`
