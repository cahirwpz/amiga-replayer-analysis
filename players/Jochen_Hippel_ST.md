---
player: Jochen_Hippel_ST
template: 3
ideas:
  [chip-emulation, register-shadow, log-volume-table, pitch-list, volume-list]
---

# Jochen Hippel ST

The Atari ST replay runs unchanged. An emulator turns its sound chip registers
into Paula writes.

## Unique ideas

- The ST replay writes its sound chip's registers into a shadow in RAM. The
  emulator turns the shadow into Paula writes. `:Play` `:EmuTick`
  - Limits: a chip channel with tone and noise on loses the noise.
- A tone is a looped 4-byte square wave. A new pitch keeps the wave's phase.
  `:EmuTone`
  - Limits: most tones play up to 23 cents sharp.
- Noise is a looped 1024-byte random sample. The noise register picks one of 32
  periods. `:EmuNoise`
  - Limits: a higher register value gives a higher pitch, the opposite of the
    chip.
- A table maps the chip's 16 logarithmic volume steps to Paula volume.
  `:EmuChannel`
  - Limits: the chip's envelope is not emulated. It gives a fixed volume of 32.
- Each voice runs a pitch list every tick and a volume list every N ticks. A
  snare switches between noise and tone in its pitch list. `:PitchList`
- Paula channel 1 is a fourth voice. Pitch lists start samples on it.
  `:StartDigi`
- Channel 1 can instead play a 2-byte pulse wave, `SID`, at a chip voice's
  pitch. `:SidVoice` `:SidPulse`
  - Limits: it restarts every tick.

## How it plays

The host calls the replay once per tick. Channel starts poll `INTREQ`, with no
audio interrupt. `:Interrupt`

A tick runs the ST replay, then the emulator. Busy-waits delay each next write.
`:EmuTick`

### Player

The player holds the tick counter, the speed and the stop flag. It also holds
the mixer byte and the noise byte, shared by all voices. `:Module`

Each tick: `:Play`

1. Voices A, B and C run their lists. Each writes its period and volume register
   into the shadow.
2. The mixer byte and the noise byte go into the shadow.
   - **Trap:** the voices share one noise register. The last voice to set it
     wins. `:NoisePeriod`
3. Every `speed` ticks, each voice reads its pattern. `:ReadPattern`
   - **Trap:** rows are read after the lists. A new note first sounds on the
     next tick.

A position holds a pattern, a transpose, an instrument transpose and flags, per
voice. `:NextPosition`

- Each voice steps to its next position at its own pattern end.
  - **Trap:** the voices stay in step only if their patterns last equally long.
- `VOLUME_OFFSET` sets this voice's volume offset. `SET_SPEED` sets the speed.
- Voice A counts the positions for all. After the last one, every voice's next
  position is the first. `:RestartSong`
  - **Trap:** the restart resets the emulator after this tick's shadow writes.
    For that tick, channel 2 plays a tone at volume 32. `:ResetEmu`
- Subsong 0 stops the music. The replay then zeroes the volume registers once.
  `:Init`

### Voice

A voice holds its pattern position, note length and row counter. It also holds
the note, flags, transposes, volume offset, mode, slide, vibrato and note
offset. `:Voice` `:PitchReader`

An instrument holds the volume list's speed, a pitch list number, vibrato speed,
depth and delay. Its volume list follows. `:Instrument`

Each row, when the note length runs out: `:ReadPattern`

1. `SET_LENGTH` sets the length of later notes, in rows. `:SetNoteLength`
2. `REST` sets the length and reads no note. The last note's lists run on.
   `:Rest`
3. A note has a note byte, a flags byte with the instrument, and maybe a third.
   `:ReadNote`
4. The third byte is a slide step, or picks the pitch list instead of the
   instrument's.
5. A `LEGATO` note changes the note and keeps both lists running.
6. Any other note restarts both lists and the vibrato from the instrument.
   - **Trap:** a new note keeps the old volume until its volume list's first
     step. `:VolumeList`

Each tick, the voice computes its registers: `:PitchList`

1. The pitch list reads opcodes until a note offset, `HOLD` or `WAIT`.
   `:PitchCommands`
   - **Trap:** without `TypePlay`, bytes `FIRST_NOTE` to `LATER_OPCODES` are
     note offsets. With it, they are opcodes.
   - **Trap:** with `TypePlay`, `DIGI_OFF` and `DIGI_ON` mean other opcodes.
2. `NOISE_ONLY`, `TONE_ONLY` and `TONE_NOISE` set the mode. `RESTART_VOLUME`
   makes the volume list restart and step at once. `:RestartVolumeList`
3. The volume list steps every N ticks. Its value is the volume. `:VolumeList`
4. Note offset, note and transpose pick a chip period. A `FIXED` offset ignores
   the note and both transposes. `:PitchToPeriod`
5. The mode sets the voice's mixer bits. In noise mode, the noise register
   follows the note.
6. `MMME` modules scale vibrato and slide by the period. Older modules double
   the vibrato per octave down and slide in periods. `:ScaledVibrato`
   `:OctaveVibrato`
7. The volume register gets the volume minus the volume offset, at least 0.
   `:VolumeOffset`

A voice falls silent when its volume list reaches 0. Its channel plays on at
volume 0.

### Emulator

Each chip channel holds a volume, a period and what plays: silence, tone or
noise. Channel 1 has its own state. `:EmuState` `:DigiState`

Each tick, chip channels A, B and C set Paula channels 0, 3 and 2: `:EmuTick`

1. `AUDxVOL` gets the table's volume. `AUDxPER` gets the chip period × 7 + 1.
   `:EmuChannel` `:WriteChannel`
2. With tone on, the square wave starts if no tone played. `:EmuTone`
3. Else, with noise on, the noise sample starts if no noise played. `AUDxPER`
   comes from the noise register. `:EmuNoise`
4. Else, an empty sample restarts every tick, with `AUDxVOL` 0.
5. Channel 1 follows. A sample plays once at `AUDxVOL` 64, then its loop or a
   [silent loop](../docs/paula-techniques.md#silent-loop). `:EmuDigi`

A start is a [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait).
It writes `AUDxPER` 1, DMA off, `AUDxLC` and `AUDxLEN`, DMA on, then the loop.
`:NotePlay`

- Each start busy-waits at least three scanlines. Channel 1 restarts an empty
  sample every tick while off.

Each tick, voice A's `SID` mode picks its own period, voice B's or voice C's.
Channel 1 then restarts the pulse. `:SidVoice`

- The pulse's second byte comes from voice A's volume. `AUDxVOL` is channel 0's.
  `:SidPulse`
- **Trap:** voice A runs first. It reads the periods of voices B and C from the
  last tick.
- **Trap:** the pulse shares channel 1 with samples. A period out of range turns
  channel 1 off, a playing sample too.

## Open questions

- How close is the volume table to the chip's curve? `:EmuChannel`
- Which Hippel versions need `TypePlay`? `:PitchCommands`
