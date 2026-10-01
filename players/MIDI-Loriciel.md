---
player: MIDI-Loriciel
template: 2
ideas: [midi-score, voice-allocation, multisamples]
---

# MIDI-Loriciel

An SMF player with four allocated voices, where each note plays its sample once.

## Context

| Fact      | Value                                                              |
| --------- | ------------------------------------------------------------------ |
| Player    | `MIDI-Loriciel`                                                    |
| Author    | Loriciel                                                           |
| Year      | 1993                                                               |
| Game      | Entity (intro music)                                               |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/MIDI-Loriciel` |
| Spec      | [specs/midi_loriciel.py](../specs/midi_loriciel.py)                |

## Key ideas

- The score is an SMF. Only note-on, note-off, program change and tempo act.
  `:ChannelEvent` `:ReadMeta`
  - Enables: music from any MIDI sequencer.
  - Costs: no CC, no pitch bend, no running status.
- Voice allocation takes the first free voice. Voice stealing takes the last
  busy voice of the same MIDI channel, else the first voice. `:AllocateVoice`
  - Enables: 16 MIDI channels share four voices.
  - Costs: no rule for age or priority. A fifth note cuts a playing note.
- An instrument is a multisample. Each sample, with its own tuning, covers the
  notes up to its top note. `:FindSampleZone` `:SelectSample`
  - Enables: low and high notes from different recordings.
- Velocity sets the volume once, by a fixed curve. `:SetVelocity`
  - Enables: dynamics with no envelope.
  - Costs: the volume never changes during a note.
- The game adds an offset to every new note's volume. `:SetVolumeOffset`
  - Enables: one music volume for the game, with no work per tick.
  - Costs: playing notes keep their volume.
- At the end of every tick, each busy voice queues silence. A sample plays once
  and never loops. `:SilentTail`
  - Enables: notes that end by themselves, with no timer per voice.
  - Costs: a held note falls silent when its sample ends.
- A tick is four pulses. Tempo sets the CIA timer's rate. `:TrackTick`
  `:SetTempo`
  - Enables: tempo changes with no change to the pulse step.
  - Costs: events closer than four pulses slip to a later tick.

## Composer's view

The composer writes an SMF and a sample bank (the format's `BNKS`). The bank
gives each MIDI program a list of samples, each for a range of notes.

| Aspect   | Answer                                                                             | Source           |
| -------- | ---------------------------------------------------------------------------------- | ---------------- |
| Notation | A note is a note-on and a note-off on one MIDI channel.                            | `:NoteOnEvent`   |
| Notation | A program change picks the instrument for later notes on the MIDI channel.         | `:SelectProgram` |
| Notation | A tempo meta event sets the tick rate.                                             | `:TempoEvent`    |
| Notation | The header's division gives the PPQ.                                               | `:InitTracks`    |
| Notation | A negative division becomes 192 PPQ.                                               | `:InitTracks`    |
| Cost     | A long note needs a long sample.                                                   | `:SilentTail`    |
| Cost     | With two notes of different pitch on one MIDI channel, the first note-off fails.   | `:MatchNoteOff`  |
| Cost     | A voice whose note-off did nothing stays busy until it is stolen.                  | `:MatchNoteOff`  |
| Cost     | With two same-pitch notes on one MIDI channel, the first note-off ends the second. | `:MatchNoteOff`  |
| Cost     | Every event needs its status byte. Running status breaks the score.                | `:ReadEvent`     |
| Cost     | The game sets how many times the song plays.                                       | `:PlayTick`      |
| Cost     | After the last pass, the player stops the timer.                                   | `:PlayTick`      |

## What is unique

- Only the latest voice of a MIDI channel can take a note-off. `:MatchNoteOff`
- A stolen voice gets no DMA off. The note may be silent, or the old sample may
  play on at the new pitch. `:StartNote`
- A note-off stops the channel at once. There is no release. `:StopNote`
- Each tick reads the tracks in file order. Events at one pulse play in track
  order, not in time order. `:PlayTick`

## Open questions

- Which scores avoid overlapping notes on one MIDI channel?
