---
player: MED
template: 2
ideas:
  [volume-list, wave-list, cross-list-jumps, waveform-as-table, release-jump]
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Context

| Fact      | Value                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ |
| Player    | `MED`                                                                                            |
| Author    | Teijo Kinnunen                                                                                   |
| Code read | original: `ext/uade/amigasrc/players/uade/med`                                                   |
| Spec      | [specs/med.py](../../../specs/med.py)                                                            |
| Links     | [archive.org](https://archive.org/details/OctaMED_Professional_v3.00_1992_RBF_Software_CU_Amiga) |

## Key ideas

- Two opcode lists per instrument, each at its own speed. `:SynthTick`
  - Enables: a slow volume shape beside fast wave changes.
  - Costs: 256 bytes of lists per synth sound; CPU low.
- Each list can set the other's position. `:VolJumpWaveList` `:WaveJumpVolList`
  - Enables: a volume phase can start a new wave phrase.
  - Costs: jumps have no conditions; the target keeps its own clock.

## Composer's view

The composer writes notes into patterns, one track per voice. MED calls a
pattern a `block` and a row a `line`. Positions order the patterns; a section
names a list of positions.

| Aspect   | Answer                                                    | Source           |
| -------- | --------------------------------------------------------- | ---------------- |
| Notation | A tracker grid: one column per track, one line per row.   | (manual)         |
| Notation | Synth sounds: two lists of values and opcodes.            | format notes     |
| Cost     | A synth arpeggio is one wave-list opcode.                 | `:ArpeggioStart` |
| Cost     | A pattern arpeggio needs its command on every row.        | `:ArpeggioTick`  |
| Cost     | A drawn envelope is one waveform and one opcode.          | `:VolEnvOnce`    |
| Cost     | A release needs no pattern data: hold and decay start it. | `:SynthRelease`  |

## What is unique

### Timing

- Each list runs every N ticks. `:SynthTick`
- A list's wait counts list visits, not ticks. `:VolWait`
- A jump moves the other list's position but keeps its clock. `:VolJumpWaveList`
- Hold counts ticks from the note-on. `:PlayRowNotes`
- The next row extends hold with an instrument number and no note, or with
  portamento. `:ExtendHold`
- When hold runs out, a synth jumps its volume list to the release part.
  `:SynthRelease` A note-off command is a hard stop instead. `:CmdNoteOff`

### Sound

- A volume-list visit runs the volume slide, then the envelope, then the list.
  Each overwrites the one before. `:SynthTick`
- A new waveform starts at the channel's next loop, with no restart.
  `:ReadWaveList`
- Synth arpeggio replaces the period, so pattern portamento then has no effect.
  `:SynthArpeggio`
- Pattern vibrato and arpeggio apply last. `:UpdatePerVol`
- A synth note after a synth note keeps the channel playing. `:KeepSynthChannel`
- Command E sets the wave-list start for a note on the same row.
  `:CmdWaveListPos`

### Sequencing

- A pattern end starts the next position. `:NextPlaySeq`
- After the last position, the next section starts. `:NextSection`
- A pattern command repeats rows. `:CmdLoop`

## Open questions

- Which songs use the jumps between lists?
