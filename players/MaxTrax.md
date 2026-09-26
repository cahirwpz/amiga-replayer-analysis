---
player: MaxTrax
control: { sequencer: commands, instrument: tables }
themes: [tricks]
ideas: [midi-score, voice-allocation, multisamples]
streams: { song: 1, voice: 1 }
---

# MaxTrax

A MIDI-style score for 16 MIDI channels, played on 4 voices through
audio.device.

## Key ideas

- Notes carry lengths; each voice counts down its own stop event.
  `data/annot/MaxTrax.yaml:SetStopEvent` `:StopCountdown`
- A note queues two requests: the attack part once, the sustain part looped.
  `:QueueAttack` `:QueueSustain`
- A patch stores one sample per octave. Low notes take a longer one, so the
  period stays short. `data/annot/MaxTrax-shared.yaml:OctaveShift`
- Pitch adds up in a log domain: note, bend, portamento, tuning. One table turns
  it into a period. `:CalcNote` `:IntAlg`
- Tempo can slide linearly over a length. `data/annot/MaxTrax.yaml:TempoSlide`
- Past display line 128, the rest of the tick's events wait. `:BeamBudget`
- [Score events and CCs](../details/MaxTrax-events.md).

## Streams

| Stream          | Scope | Role       | Carries                         | Control   | Rate  |
| --------------- | ----- | ---------- | ------------------------------- | --------- | ----- |
| Score           | song  | sequencer  | notes, tempo, CCs, programs     | loop, end | delta |
| Volume envelope | voice | instrument | target volumes and times; patch | wait      | delta |

## Sequencer

| Aspect   | Value     | Label                                       |
| -------- | --------- | ------------------------------------------- |
| Time     | deltas    | `data/annot/MaxTrax.yaml:ScoreClock`        |
| Unit     | pulse     | `:SetTempo`                                 |
| Note end | length    | `:SetStopEvent`                             |
| Routing  | allocated | `data/annot/MaxTrax-shared.yaml:pick_voice` |
| Reuse    | loops     | `data/annot/MaxTrax.yaml:BeginRepeat`       |
| Tempo    | scaled    | `:SetTempo`                                 |

- Voices 0 and 3 are left, 1 and 2 right. A MIDI channel's pan picks the side.
  `data/annot/MaxTrax-shared.yaml:pick_voice`
- The other side wins if ours has no free or releasing voice and it has one.
- On one side, the voice with the lower envelope state wins: free, then
  releasing, then held. A round-robin breaks ties. `:pick_voice1`
- The winner is stolen, even mid-note. `data/annot/MaxTrax.yaml:StealVoice`
- Priority: score 0, game notes 1, game sounds 2. No note steals a voice of
  higher priority. `:ExtraServer`

## Generators

| Generator  | Scope | States      | Writes | Rate | Set by | Note-on |
| ---------- | ----- | ----------- | ------ | ---- | ------ | ------- |
| Portamento | voice | glide, done | period | tick | Score  | flag    |

## Channel outputs

| Output | Writers, in tick order                      |
| ------ | ------------------------------------------- |
| Sample | Score (set)                                 |
| Period | Score (note), Score (add), Portamento (add) |
| Volume | Score (scale), Volume envelope (set)        |
| DMA    | Score (on)                                  |

## Interactions

| From  | To              | Event                                                                                             |
| ----- | --------------- | ------------------------------------------------------------------------------------------------- |
| Score | Volume envelope | Stop event starts the release; damper pedal holds it `data/annot/MaxTrax-shared.yaml:DamperPedal` |
| Score | game            | Sync event signals a task `data/annot/MaxTrax.yaml:SyncEvent`                                     |
| game  | Score           | Notes and sounds take voices by priority `:ExtraServer`                                           |

- VBL raises a software interrupt; the music runs there. `:MusicVBlank`
- CC 65 off writes into the score: a bug.
  `data/annot/MaxTrax-shared.yaml:PortaOffBug`

## State

| Scope      | Fields                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------- |
| Voice      | MIDI channel, patch, note, end note, envelope step and time, priority                               |
| Instrument | sample per octave with attack and sustain parts, envelopes, volume, tune                            |
| Global     | score clock, tempo slide, repeat counters; per MIDI channel: patch, bend, pan, volume, damper, mono |

## Open questions

- Which games used MaxTrax? The source names Music-X and The Dreamers Guild.
