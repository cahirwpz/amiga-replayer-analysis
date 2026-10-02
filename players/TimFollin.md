---
player: TimFollin
template: 3
ideas:
  [
    bare-instruments,
    track-programs,
    pulse-width-sweep,
    semitone-portamento,
    sample-chaining,
  ]
---

# Tim Follin

There is no instrument program. Each voice's track sets small state machines.
Their settings hold until the track changes them.

## Unique ideas

- An instrument is only a sample. Envelope, vibrato, trill, portamento and pulse
  sweep are per-voice settings from the track. `:CmdInstrument` `:ReadTrack`
  - Limits: every change of sound costs track bytes.
- Commands take no time. A note carries its length, or a fixed length applies.
  `:ReadTrack` `:CmdFixedLength`
  - Limits: voices line up only by counting ticks.
- Instruments 0–3 are pulse waves, swept in place. Every N ticks, one sample
  byte flips. `:PulseSweep`
  - Limits: the edge moves between bytes 4 and 30 of the wave.
- Portamento moves the note index, not the period. `:Portamento`
  - Limits: it steps by whole semitones.
- A trill moves the note itself up by an interval and back. `:TrillTick`
- A second sample can follow one tick after the note starts. The first plays
  once, and the second loops. `:ChainSample`

## How it plays

The host's tick runs the chain step for all voices, then the tick. There is no
audio interrupt. `:ChainTick` `:Tick`

### Player

The player holds the subsong and a fade level. A subsong has one track per voice
and its own instrument list. `:Module` `:Subsong`

- Each tick, it runs each active voice. `:Tick`
- Subsong 14 starts with every voice inactive. With 3 voices, voice 3 stays
  untouched. `:StartSubsong`

### Voice

A voice holds its track position, note timer, call stack and loop slot. It holds
the note, target, transpose, period, sample, flags and four state machines.
`:Voice`

Each tick, in this order: `:VoiceTick`

1. The pulse sweep runs. `:PulseSweep`
2. The envelope runs. `AUDxVOL` gets its volume, every tick. `:EnvelopeTick`
3. Vibrato runs once its delay ends. Otherwise the trill runs. `:VibratoTick`
   `:TrillTick`
4. Portamento runs, unless a trill step happened. Its step overwrites the
   vibrato's period. `:Portamento`
5. The note timer counts down. One tick before the end, `GATE_OFF` turns DMA
   off. `:GateOff`
6. At the end, the track reads on. `:NoteTimer`

The track reads commands until a note. Each command changes a setting and takes
no time. `:ReadTrack`

- `CmdCall` has four return slots, and nothing checks them. `:CmdCall`
- **Trap:** a loop has one slot. A loop inside a called routine replaces its
  caller's loop. `:CmdLoopStart`
- **Trap:** after `CmdFixedLength`, a note has no length byte. The same track
  bytes then read differently. `:CmdFixedLength`

A note start: `:PlayNote`

1. The note gets the transpose, unless `CmdNoTranspose` came just before. With
   portamento on, it becomes the target, and the pitch stays.
2. `AUDxLC` and `AUDxLEN` get the whole sample, which is also its loop. DMA goes
   on, and `AUDxPER` gets the period. `:StartSample`
3. The trill, the vibrato delay and, if set, the envelope restart.
   - **Trap:** the envelope restarts after this tick's volume write. The new
     volume is heard one tick later.

- **Trap:** without `GATE_OFF`, the channel still plays at DMA on. The new
  sample waits for the old loop's end. `:StartSample`
- **Trap:** the chain step writes the second sample one tick later. Without
  `GATE_OFF`, a loop longer than a tick never plays the first sample.
  `:ChainSample`

There is no rest note. A voice falls silent through its envelope, or through
`CmdEnd`: DMA off and volume 0. `:CmdEnd`

### State machines

Each voice has four. The track sets them, and a note restarts all but the pulse
sweep. `:Envelope` `:Vibrato` `:Trill` `:Pulse`

- The envelope's attack adds a step every N ticks. Its decay subtracts the step
  down to the sustain level. `:EnvelopeTick`
  - **Trap:** attack ends only at exactly 63. A step that misses 63 runs on past
    it.
  - With envelope restart off, the volume runs on across notes.
- Vibrato adds a step to the period every tick. It turns every two half cycles.
  `:VibratoTick`
  - Vibrato steps in periods. Low notes get a smaller pitch change.
  - With a half cycle of 0, it never turns. It slides to the note's end.
- **Trap:** vibrato and the trill share one direction flag. With a first
  direction other than 0 or 1, neither turns. `:TrillTick`
- The pulse sweep widens the pulse by one byte per step, then narrows it.
  `:PulseSweep`
  - **Trap:** the sweep edits the instrument's sample. Voices on one pulse
    instrument share the wave, as
    [live wave edits](../docs/paula-techniques.md#live-wave-edits).
  - **Trap:** notes do not restart the sweep. Only `CmdPulseSpeed` does.

## Open questions

- Which game is this from? Subsong 13 has an unused volume override.
  `:SetVolume`
- A fade would restart subsong 0. Nothing starts a fade (guess: a game
  leftover). `:Tick`
- `ResetPulse` writes at +2, but the wave plays from +$32 (guess: a typo). So
  `CmdPulseSpeed` never resets the playing wave. `:ResetPulse`
