---
player: Oktalyzer
template: 2
ideas: [voice-mixing]
---

# Oktalyzer

Up to eight sample tracks play on four channels. A channel plays one track or a
mixed pair.

## Context

| Fact      | Value                                                |
| --------- | ---------------------------------------------------- |
| Player    | `Oktalyzer`                                          |
| Author    | Armin Sander                                         |
| Code read | disassembly: `ext/oktalyzer/src`                     |
| Spec      | [specs/oktalyzer.py](../specs/oktalyzer.py)          |
| Links     | [github.com](https://github.com/hitchhikr/oktalyzer) |

## Key ideas

- The song marks each channel single or mixed. A mixed channel plays two tracks
  from a buffer the CPU fills each tick. `:MixChannel` `:Play1`
  - Enables: 5 to 8 tracks.
  - Costs: a pair shares one channel volume.
- Samples for mixed tracks are stored at 7 bits. Two of them sum within 8 bits.
  `:SampleEntry`
  - Enables: mixing without clipping or volume tables.
  - Enables: such samples may lie outside chip memory.
- Replay 2 plays a buffer at the higher note's period. It adds that track
  unchanged and resamples only the lower one. `:PickHigher` `:MixPair`
  - Enables: one track of each pair keeps full quality.
  - Costs: the lower track repeats bytes, with no interpolation.
- Replay 2 fills one frame per note, from a table. A channel that runs ahead
  gets one word more. `:DriftFix` `:QueueBuffers`
  - Enables: buffers at any rate follow the frame tick.
  - Costs: a busy-wait when a channel runs late.
- Replay 1 writes one resampler per note, from 36 routines of straight code.
  Repeated source bytes become averages. `:BuildResamplers` `:RunResampler`
  - Enables: no step arithmetic while mixing.
  - Costs: about 43 kB of code (estimate).
  - Costs: all mixed channels play at 15.6 kHz.

## Composer's view

The composer marks channels single or mixed and writes patterns and samples. A
row holds a note, a sample, a command and an argument for each track. The
tracker shows commands as `0`–`9` and `A`–`Z`.

| Aspect   | Answer                                                                 | Source            |
| -------- | ---------------------------------------------------------------------- | ----------------- |
| Notation | A row has 4 to 8 cells, one per track.                                 | `:NewRow`         |
| Notation | A sample is for mixed tracks, single tracks, or both.                  | `:SampleEntry`    |
| Cost     | A mixed track ignores the sample's loop and volume.                    | `:GetMixedNotes`  |
| Cost     | Volume on a mixed track sets both tracks of its channel.               | `:SetVolume`      |
| Cost     | A mixed track has no portamento.                                       | `:TrackEffects`   |
| Cost     | A mixed track moves its pitch in semitones.                            | `:TrackEffects`   |
| Cost     | Single channels slide in periods or in semitones.                      | `:ChannelEffects` |
| Cost     | `OLD_VOLUME` lets a new note on a single channel keep the last volume. | `:OldVolume`      |
| Cost     | In replay 2, notes above A-3 on mixed tracks play as A-3.              | `:ClampNote`      |
| Cost     | The position jump's argument is decimal.                               | `:PositionJump`   |

## What is unique

- A single channel is silent for one tick before each note. DMA goes off at the
  row and on at the next tick. `:SetHardware` `:TurnDmaOn`
- A single note sounds one tick after the mixed notes of its row. `:SetHardware`
- A resampled mixed track stops at the tick when fewer bytes are left than it
  needs. The rest never plays. `:ResampleTrack` `:ResampleLower`
- Adds of 4 bytes at once let a carry spill into the byte before. `:AddPacked`
  `:AddHigher`
- Three arpeggio commands cycle in different orders. Command `A` starts below
  the note. `:ChannelEffects`

## Open questions

- Did a game or demo ship replay 1? The tracker offers both; songs do not
  choose.
- Replay 1 writes 313 bytes per tick and never syncs with the channel. Does the
  write position drift into the half that plays (guess)? `:Play1`
