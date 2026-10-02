---
player: MED
template: 3
ideas:
  [volume-list, wave-list, cross-list-jumps, waveform-as-table, release-jump]
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Unique ideas

- A synth sound has two command lists, each with its own interval in ticks.
  `:SynthTick`
  - Limits: each list holds up to 128 bytes.
- Each list can set the other's index. A volume phase can start a new wave
  phrase. `:VolJumpWaveList` `:WaveJumpVolList`
  - Limits: a jump has no condition.
- Waveforms double as volume envelopes and vibrato shapes. `:VolEnvOnce`
  `:VibratoWave`
  - Limits: an envelope takes one of the 64 waveform slots.
- A synth sound with a sample plays slot 0 as a sample, through both lists. MED
  calls it `hybrid`. `:StartSynthNote`
  - Limits: the sample takes the first of the 64 waveform slots.
- When the gate time ends, the volume list jumps to its release part. No pattern
  data is needed. `:SynthRelease`
  - Limits: a hard stop, `NOTE_OFF`, skips the release part. `:CmdNoteOff`
- A synth arpeggio is one wave-list opcode and its note offsets.
  `:ArpeggioStart`

## How it plays

A CIA timer interrupt runs the tick at the song's tempo. With beat-based tempo,
only every fourth interrupt runs a tick. `:PlayTick` `:SetTempo`

- An optional mode, not in the spec, plays samples from fast memory. Audio
  interrupts copy them into chip buffers.

A row reads all tracks, runs the pre-row commands and starts the notes. Each
tick runs hold, tick commands, register writes and DMA start. `:PlayTick`

### Player

The player holds the section, position, pattern, row and tick counter. It holds
one row loop for the whole song. `:Module`

- A section names a list of positions. A position names a pattern, MED's
  `block`. `:NextPlaySeq`
- A pattern has one track per voice. Voice n plays channel n. `:Pattern`
- Tick commands run from the row just played, on each of its ticks. `:DoFX`
- **Trap:** `CMD_LOOP` keeps one mark and one count for all tracks. Loops on two
  tracks share them. `:CmdLoop`

### Voice

A voice holds its instrument, note, period, gate time and `decay`. MED calls the
gate time `hold`. `:Voice`

It holds three volumes. The note volume comes from the instrument. The track
volume scales the output, and the synth volume comes from the volume list.

Each row, it reads its track: `:PlayTick`

1. An instrument number loads volume, gate time, `decay` and finetune. A note
   without one plays the last instrument.
2. `CMD_HOLD_DECAY` sets gate time and `decay` until the next instrument number.
   `:CmdHoldDecay`
3. `CMD_PORTAMENTO` makes the row's note its target. That note does not play.
   `:SetPortamento`
4. `TRIPLET_FIRST` plays the note a third into the row, `TRIPLET_SECOND` two
   thirds. `:MiscTick`
5. An instrument number without a note extends the gate time by one row. So does
   `CMD_PORTAMENTO` on the next row. `:ExtendHold`

- A pattern arpeggio needs its command on every row. Each row starts on its high
  note, unlike ProTracker. `:ArpeggioTick`

A note start: `:PlayNote`

1. The note gets the play transpose and the instrument transpose.
   `:AddTransposes`
2. DMA goes off, except for a synth note after a synth note. That note is
   legato. `:KeepSynthChannel`
3. A sample note folds its note into range once. `AUDxLC` and `AUDxLEN` get the
   whole sample.
4. A synth note resets both lists and all synth modulation. Its period table
   lies two octaves lower. `:StartSynthNote`
   - **Trap:** after `CMD_WAVE_LIST_POS`, notes keep the wave list's index.
     Until the next instrument number, each starts where the last stopped.
     `:CmdWaveListPos`

Each tick, it writes its registers: `:UpdatePerVol`

1. A synth voice runs its lists and gets a period. `:SynthTick`
2. `AUDxPER` gets that period plus pattern vibrato and arpeggio.
3. `AUDxVOL` gets the output volume × the track volume / 256. A synth's output
   volume is the synth volume × the note volume / 64.

After the tick, a busy-wait polls the beam before DMA on. A second wait precedes
the loop write. `:StartDMA`

- See [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait) and
  [loop by reload](../docs/paula-techniques.md#loop-by-reload).
- On a fast CPU, the first wait shrinks to 161 CCK (estimate).

When the gate time ends: `:HoldAndFade` `:SynthRelease`

- **Trap:** `decay` has two readings. A synth's volume list jumps to it as an
  index. A sample fades by it per tick.
- A sample with `decay` 0 turns DMA off. Gate time 0 never ends.
- A sample without a loop ends on a
  [silent loop](../docs/paula-techniques.md#silent-loop). `NOTE_OFF` turns DMA
  off at once. `:ChannelOff`

### Lists

Each list holds an index, an interval, a countdown and a wait. A visit comes
every interval and reads bytes until a value or a wait. `:ReadVolumeList`
`:ReadWaveList`

- A wait counts visits, not ticks. `:VolWait`
- **Trap:** a jump clears the other list's wait, not its countdown. The target
  acts at its next visit. `:VolJumpWaveList`
- The list end parks the list. Slides, envelope and vibrato run on.
  `:VolListEnd`

A volume list visit: `:SynthTick`

1. The volume slide adds to the synth volume.
2. An envelope step overwrites it. It reads a waveform as 128 volumes, once or
   looping. `:VolEnvelopeStep`
3. A list value overwrites both.

A wave list visit: `:WaveListTick`

1. The pitch slide adds its step, even while the list waits.
2. A value writes a waveform to `AUDxLC` and `AUDxLEN`. It starts at the next
   reload, with no restart. `:ReadWaveList`

Every tick, after the visits:

1. The synth arpeggio replaces the period. `:SynthArpeggio`
   - **Trap:** the synth arpeggio discards pattern portamento's period.
     Portamento then has no effect.
2. The synth vibrato adds shape × depth / 256. Low notes get a smaller pitch
   change. `:SynthVibrato`
3. The pitch slide adds last. A clamp at 113 writes the wrong register.
   `:SynthTick`
