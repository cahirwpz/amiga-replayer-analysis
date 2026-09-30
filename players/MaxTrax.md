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
  - Enables: songs from a MIDI sequencer play almost unchanged (guess).
  - Costs: 6 bytes per event.
- `MARK` events put markers in one score. A song can start at any marker.
  `:PlaySong` `:SkipMarks`
  - Enables: one score holds several subsongs.
- Voice allocation picks a voice per note, by side, envelope state and priority.
  `:PickVoice` `:PickSibling`
  - Enables: game notes and sounds share the 4 voices with the music.
  - Costs: voice stealing cuts a busy voice off at once. `:StealVoice`
- An instrument is a multisample with one sample per octave. A note moves down
  an octave while its period would pass about 508 (estimate). `:OctaveShift`
  - Enables: low notes keep their high frequencies.
  - Costs: each octave doubles the sample's size.
- Pitch is the sum of note, pitch bend, portamento and tuning, on a log scale.
  One table turns it into a period. `:CalcNote` `:IntAlg`
  - Enables: pitch bends and glides move evenly in semitones.
  - Costs: a table of 257 words.
- Volume envelopes run in milliseconds, with an attack part and a release part.
  `:DoOneVoice` `:EnvelopeRamp`
  - Enables: envelopes sound the same at any tempo.
  - Costs: each segment is a straight line to a target.
- A note makes two audio.device requests. The second one loops the sustain part.
  `:QueueAttack` `:QueueSustain`
  - Enables: the driver writes no sound registers itself.
  - Costs: every period or volume change is a request.

## Composer's view

The composer writes a song in Music-X, a MIDI sequencer. MaxTrax calls an
instrument a `patch`.

| Aspect   | Answer                                                         | Source                      |
| -------- | -------------------------------------------------------------- | --------------------------- |
| Notation | An event holds a command.                                      | `:Event`                    |
| Notation | An event holds a data byte.                                    | `:Event`                    |
| Notation | An event holds a start delta.                                  | `:Event`                    |
| Notation | An event holds a second data field.                            | `:Event`                    |
| Notation | A note has a MIDI channel.                                     | `:RunEvent`                 |
| Notation | A note has a velocity in 16 steps.                             | `:RunEvent`                 |
| Notation | 192 pulses per quarter note.                                   | `:SetTempo`                 |
| Notation | Tempo in beats per minute.                                     | `:SetTempo`                 |
| Notation | A tempo event can slide the tempo in a straight line.          | `:TempoSlide`               |
| Cost     | A chord takes one voice per note, out of 4.                    | `:PickVoice`                |
| Cost     | A glide needs mono mode and CC 65.                             | `:NoteOn`                   |
| Cost     | A glide takes the portamento time, whatever its interval.      | `:CalcNote`                 |
| Cost     | A legato note keeps the voice's sample and envelope.           | `:MonoLegato`               |
| Cost     | A release waits while CC 64 is down.                           | `:DamperPedal`              |
| Cost     | CC 7 changes only notes that start after it.                   | `:StealVoice`               |
| Cost     | Velocity counts only while the game sets `MUSIC_VELOCITY`.     | `:StealVoice`               |
| Cost     | A bend or a glide keeps the note's octave sample.              | `:CalcNote`                 |
| Cost     | A slide to a slower tempo overshoots high until it ends (bug). | `:ContinueTempo`            |
| Cost     | With the wheel below center, a new bend range bends up (bug).  | `:ControlCh`                |
| Cost     | CC 65 off writes a byte into the score (bug).                  | `:PortaOffBug`              |
| Cost     | A repeat is a begin and an end event.                          | `:BeginRepeat` `:EndRepeat` |
| Cost     | Repeats nest 4 levels deep.                                    | `:BeginRepeat`              |

## What is unique

- Pan picks the left or the right voices, not a level. `:PanSide`
- Of two voices on one side, the freest wins, in the order free, releasing,
  held. A round-robin breaks ties. `:PickSibling`
- Game sounds rank above game notes, which rank above the score. No note takes a
  voice of higher priority. `:PickVoice`
- A game note's length counts in milliseconds, not pulses. `:StopCountdown`
- While the score plays, the game can skip it ahead to a later marker.
  `:AdvanceSong`
- A sync event passes a value to the game. `:SyncEvent`
- Past display line 128, the frame's other events wait. `:BeamBudget`

## Open questions

- Which games used MaxTrax? The source names Music-X and The Dreamers Guild.
