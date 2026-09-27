---
player: TimFollin
template: 2
ideas:
  [
    bare-instruments,
    track-programs,
    pulse-width-sweep,
    semitone-glide,
    sample-chaining,
  ]
---

# Tim Follin

There is no instrument program: each voice's track sets the parameters of small
state machines.

## Context

| Fact      | Value                                                    |
| --------- | -------------------------------------------------------- |
| Player    | `TimFollin`                                              |
| Author    | Tim Follin / Mike D.                                     |
| Code read | disassembly: `ext/uade/amigasrc/players/other/timfollin` |
| Spec      | [specs/tim_follin.py](../specs/tim_follin.py)            |

## Key ideas

- An instrument is only a sample. The track sets parameters that stay until it
  changes them. `:CmdInstrument` `:ReadTrack`
  - Enables: one command changes the sound of all later notes.
  - Costs: every sound change takes track bytes.
- Commands take no time. A note carries its length, or a fixed length applies.
  `:ReadTrack` `:CmdFixedLength`
  - Enables: a run of equal notes takes one byte per note.
  - Costs: voices line up only by counting ticks.
- Pulse waves are swept in place: every N ticks, one sample byte changes.
  `:PulseSweep`
  - Enables: a moving pulse width with no extra memory.
  - Costs: voices on one pulse instrument share the wave.
- Flag bit 7 stops the channel one tick before the note ends. Without it, the
  next sample waits for the loop's end. `:GateOff` `:StartSample`
  - Enables: legato or a clean restart, chosen per voice.
  - Costs: a clean restart loses the note's last tick.
- A second sample follows one tick after the note starts. The first plays once;
  the second loops. `:ChainSample`
  - Enables: an attack sample with its own loop.
  - Costs: the second sample must be in the subsong's list.

## Composer's view

The composer writes one track per voice, with commands between the notes. There
are no patterns. Each subsong has its own instrument list.

| Aspect   | Answer                                                 | Source                     |
| -------- | ------------------------------------------------------ | -------------------------- |
| Notation | A note byte, then a length byte.                       | `:PlayNote`                |
| Notation | Commands between notes set parameters for later notes. | `:ReadTrack`               |
| Cost     | After a fixed length, a note is one byte.              | `:CmdFixedLength`          |
| Cost     | An arpeggio is written as short notes.                 | `:PlayNote`                |
| Cost     | A trill is one command with three arguments.           | `:CmdTrill`                |
| Cost     | A repeat is two commands, one level deep.              | `:CmdLoopStart` `:CmdLoop` |

## What is unique

- Portamento moves the note index, so the glide steps by semitones.
  `:Portamento`
- A trill changes the note itself. It shares its direction bit with vibrato.
  `:TrillTick`
- After a note, vibrato waits a delay; the trill runs during it. `:VibratoTick`
- Attack ends only at exactly volume 63. `:EnvelopeTick`
- A note restarts the envelope after the tick's volume write. The change is
  heard one tick later. `:PlayNote`
- Calls have four return slots; loops have one slot and do not nest. `:CmdCall`
  `:CmdLoopStart`

## Open questions

- Which game is this from? Subsong 14 plays nothing, and subsong 13 has an
  unused volume override. `:StartSubsong` `:SetVolume`
- A fade would restart subsong 0, but nothing starts it (guess: a game
  leftover). `:Tick`
- `ResetPulse` writes at +2, but the wave plays from +$32 (guess: a typo).
  `:ResetPulse`
