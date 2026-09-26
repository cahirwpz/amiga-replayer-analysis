---
player: Oktalyzer
control: { sequencer: commands, instrument: none }
themes: [mixing, tricks]
ideas: [voice-mixing]
streams: { song: 1, voice: 1 }
---

# Oktalyzer

Up to eight sample voices: each channel plays one voice or a mixed pair.

## Key ideas

- The song marks each channel as single or mixed. Mixed tracks need samples
  stored at 7 bits, so two sum within 8 bits.
  `data/annot/Oktalyzer.yaml:HalveSample` `:SkipFullSample`
- A mixed pair shares its channel's volume. `:TrackToChannel`
- Mixed voices change pitch in semitone steps only. `:MixPair`
- Replay 1 writes one resampler per note at start: 36 straight-line routines,
  313 bytes each. Repeated source bytes become neighbour means.
  `:BuildResamplers` `:ResampleTemplates`
- Replay 1 adds four bytes per add.l; carries spill into the next byte.
  `:AddPacked`
- Replay 2 plays the buffer at the higher note's period. That voice is added
  unchanged; only the lower one is resampled. `:PickHigher` `:MixPair`
- Replay 2's buffer length follows the note. A channel that ran ahead gets one
  word more. `:DriftFix` `:OK_AudInt`

| Replay | Rate                 | Pitch of mixed voices        | UADE |
| ------ | -------------------- | ---------------------------- | ---- |
| 1      | 15.6 kHz, fixed, PAL | generated code per note      | no   |
| 2      | higher note's period | lower voice resampled at run | yes  |

UADE's binary is OKPlay2. The author's objects `okplay1.o` and `okplay2.o` hold
the same code as the tracker.

## Streams

| Stream    | Scope | Role      | Carries              | Control | Rate        |
| --------- | ----- | --------- | -------------------- | ------- | ----------- |
| Positions | song  | sequencer | pattern number       | loop    | pattern end |
| Pattern   | voice | sequencer | note, sample, effect | jump    | row         |

## Sequencer

| Aspect   | Value     | Label                |
| -------- | --------- | -------------------- |
| Time     | rows      | `:OK_ReplayHandler`  |
| Unit     | row       | `:OK_ReplayHandler`  |
| Note end | next note | `:OK_GetPatternData` |
| Routing  | fixed     | `:TrackToChannel`    |
| Reuse    | patterns  | `:OK_GetPPatt`       |
| Tempo    | speed     | `:OK_CSpeed`         |

## Generators

| Generator | Scope | States | Writes    | Rate | Set by  | Note-on |
| --------- | ----- | ------ | --------- | ---- | ------- | ------- |
| Mixer     | song  | mix    | wave data | tick | Pattern | keep    |

## Channel outputs

| Output    | Writers, in tick order |
| --------- | ---------------------- |
| Wave data | Mixer (edit)           |
| Sample    | Mixer (set)            |
| Period    | Mixer (set)            |
| Volume    | Pattern (set)          |

## Interactions

| From    | To          | Event                                            |
| ------- | ----------- | ------------------------------------------------ |
| Pattern | other voice | A volume effect sets the whole pair `:OK_Volume` |

## State

| Scope      | Fields                                                    |
| ---------- | --------------------------------------------------------- |
| Voice      | sample pointer, bytes left, note, base note               |
| Instrument | none; samples carry length, loop, volume, bit depth       |
| Global     | position, row, speed, channel modes, two buffers per pair |

## Open questions

- Did a game or demo ship replay 1? The tracker offers both; songs do not
  choose.
