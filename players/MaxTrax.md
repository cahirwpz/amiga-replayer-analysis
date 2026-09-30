---
player: MaxTrax
template: 2
ideas: [midi-score, voice-allocation, multisamples, log-pitch]
---

# MaxTrax

A MIDI-like score for 16 MIDI channels, played on 4 voices through audio.device.

## Context

| Fact      | Value                                                |
| --------- | ---------------------------------------------------- |
| Player    | `MaxTrax`                                            |
| Author    | Talin (David Joiner) and Joe Pearce                  |
| Year      | 1991                                                 |
| Code read | original: `ext/uade/amigasrc/players/other/max_trax` |
| Spec      | [specs/maxtrax.py](../specs/maxtrax.py)              |

## Key ideas

- The score is one list of timed events. Each note carries its length.
  `:ReadEvents` `:SetStopEvent`
  - Enables: songs from a MIDI sequencer play almost unchanged.
  - Costs: 6 bytes per event.
- Voice allocation picks a voice per note, by side, envelope state and priority.
  `:PickVoice` `:PickSibling`
  - Enables: game notes and sounds share the 4 voices with the music.
  - Costs: voice stealing cuts a busy voice off at once. `:StealVoice`
- An instrument is a multisample: one sample per octave. A note moves down an
  octave while its period would pass about 508. `:OctaveShift`
  - Enables: low notes keep their high frequencies.
  - Costs: each octave doubles the sample's size.
- Pitch adds up as a logarithm: note, pitch bend, portamento and tuning. One
  table turns it into a period. `:CalcNote` `:IntAlg`
  - Enables: pitch bends and glides move evenly in semitones.
  - Costs: a table of 257 words.
- Volume envelopes run in milliseconds, with an attack part and a release part.
  `:DoOneVoice` `:EnvelopeRamp`
  - Enables: envelopes sound the same at any tempo.
  - Costs: each segment is a straight line to a target.
- A note is two audio.device requests: the attack part once, then the sustain
  part looped. `:QueueAttack` `:QueueSustain`
  - Enables: the driver writes no sound registers itself.
  - Costs: every period or volume change is a request.

## Composer's view

The composer writes a song in Music-X, a MIDI sequencer. MaxTrax calls an
instrument a `patch`.

| Aspect   | Answer                                                    | Source                      |
| -------- | --------------------------------------------------------- | --------------------------- |
| Notation | An event: command, data, start delta, stop time.          | `:Event`                    |
| Notation | A note: MIDI channel, velocity in 16 steps, length.       | `:RunEvent`                 |
| Notation | 192 pulses per quarter note.                              | `:SetTempo`                 |
| Notation | Tempo in beats per minute.                                | `:SetTempo`                 |
| Cost     | A chord takes one voice per note, out of 4.               | `:PickVoice`                |
| Cost     | A glide needs mono mode and CC 65.                        | `:MonoLegato`               |
| Cost     | A glide takes the portamento time, whatever its interval. | `:CalcNote`                 |
| Cost     | A legato note keeps the voice's sample and envelope.      | `:MonoLegato`               |
| Cost     | A release waits while CC 64 is down.                      | `:DamperPedal`              |
| Cost     | A repeat is a begin and an end event, 4 levels deep.      | `:BeginRepeat` `:EndRepeat` |

## What is unique

- Pan picks a side, not a level: the left or the right voices. `:PanSide`
- Of two voices on one side, the freer one wins: free, then releasing, then
  held. A round-robin breaks ties. `:PickSibling`
- Priority: score 0, game notes 1, game sounds 2. No note takes a voice of
  higher priority. `:PickVoice`
- Past display line 128, the frame's other events wait. `:BeamBudget`
- A tempo event can slide the tempo in a straight line. A slide to a slower
  tempo overshoots high until it ends: a bug. `:TempoSlide` `:ContinueTempo`
- A new pitch bend range, with the wheel below center, bends up: a bug.
  `:ControlCh`
- CC 65 off writes a byte into the score: a bug. `:PortaOffBug`

## Open questions

- Which games used MaxTrax? The source names Music-X and The Dreamers Guild.
