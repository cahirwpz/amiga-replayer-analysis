---
player: MIDI-Loriciel
control: { sequencer: commands, instrument: none }
themes: [tricks]
ideas: [midi-score, voice-allocation, multisamples]
streams: { track: 1 }
---

# MIDI-Loriciel

An SMF sample player with four allocated voices and no instrument programs.

## Key ideas

- MIDI tracks share instruments and note ownership through 16 MIDI channels.
  Only each channel's latest voice can receive note-off.
  `data/annot/MIDI-Loriciel.yaml:AllocateVoice` `:MatchNoteOff`
- Instruments map note ranges to samples and tuning offsets. These are lookups,
  not streams. `:SelectSample`
- Velocity and pitch use fixed lookups, not evolving controllers. `:SetVelocity`
  `:SelectSample`
- [Supported events and limits](../details/MIDI-Loriciel-events.md): no CCs,
  pitch bend or running status.

## Streams

| Stream       | Scope | Role      | Carries                       | Control   | Rate  |
| ------------ | ----- | --------- | ----------------------------- | --------- | ----- |
| Track events | track | sequencer | notes, programs, tempo; score | wait, end | delta |

## Sequencer

| Aspect   | Value     | Label            |
| -------- | --------- | ---------------- |
| Time     | deltas    | `:ReadDelta`     |
| Unit     | pulse     | `:TrackTick`     |
| Note end | note-off  | `:StopNote`      |
| Routing  | allocated | `:AllocateVoice` |
| Reuse    | none      | `:ReadEvent`     |
| Tempo    | timer     | `:SetTempo`      |

- First free voice wins, scanning 0 to 3. `:AllocateVoice`
- Otherwise, steal the last voice belonging to this MIDI channel.
- Without a match, steal voice 0. There is no age or priority policy.

Each tick advances four pulses. Tempo changes the timer, not this step.
`:TrackTick` `:SetTempo`

## Generators

| Generator   | Scope | States     | Writes | Rate | Set by       | Note-on |
| ----------- | ----- | ---------- | ------ | ---- | ------------ | ------- |
| Silent tail | voice | free, busy | sample | tick | Track events | restart |

## Channel outputs

| Output | Writers, in tick order                |
| ------ | ------------------------------------- |
| Sample | Track events (set), Silent tail (set) |
| Period | Track events (note)                   |
| Volume | Track events (set)                    |
| DMA    | Track events (on), Track events (off) |

Track writers run in event order. Busy voices then get a silent reload.
`:SilentTail`

Sample end does not free a voice. A matching note-off stops DMA without release.
`:MatchNoteOff` `:StopNote`

## State

| Scope      | Fields                                                                        |
| ---------- | ----------------------------------------------------------------------------- |
| Voice      | free/busy, MIDI channel, note, output address                                 |
| Instrument | sample zones: upper note bound, tuning offset, sample address and length      |
| Global     | tempo; tracks: cursor, wait, channel; MIDI channels: instrument, latest voice |

## Open questions

- Which scores avoid overlapping notes on one MIDI channel?
