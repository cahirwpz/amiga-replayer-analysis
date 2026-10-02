# Instrument programs

These players differ in where an instrument's behaviour lives. It lives in a
program, in code, in the score or nowhere. A program is flexible, but each voice
runs an interpreter.

## Instrument programs

An instrument program is a list of opcodes that runs once per tick on a voice.
It sets the sample, period and volume, and it waits, loops and branches.

- [TFMX Pro](../players/TFMX-Pro.md): a program, TFMX's `macro`, has 52 opcodes.
  It branches on note, volume and note-off. `specs/tfmx_pro.py:MacroStep`
  - A note restarts only the program. Effects, volume and sample carry over.
- [Jason Page](../players/JasonPage.md): notes and game sound effects request
  the same programs. A request below the voice's priority is dropped.
  `specs/jason_page.py:RequestProgram`
  - A program must turn DMA on itself.

## Programs that rewrite programs

A program opcode can write into the bytes of another program.

- [TFMX Pro](../players/TFMX-Pro.md): opcodes copy or add values into a program.
  Every voice that plays that program hears the change.
  `specs/tfmx_pro.py:CopyToMacro`

## Instrument drivers

Each instrument type has its own code, not its own data. The player calls the
type's routines for every voice that plays it.

- [Sonix Music Driver](../players/SonixMusicDriver.md): a driver has a tick
  routine and a register routine. The synth driver and the sample drivers keep
  different voice state. `specs/sonix_music_driver.py:TickInstruments`

## Instruments inside the score

A stream defines an instrument where it first needs it.

- [SoundFactory](../players/SoundFactory.md): an opcode stores the definition's
  address in one of 32 slots. The stream skips its bytes.
  `specs/sound_factory.py:OpDefineInstrument`
  - Effect opcodes write into the instrument, not into the voice. Every voice
    that plays it hears the change at once.

## Bare instruments

An instrument holds only a sample. The score sets every other sound property per
voice.

- [Tim Follin](../players/TimFollin.md): the track sets envelope, vibrato,
  trill, portamento and pulse sweep as voice state. Every change of sound costs
  track bytes. `specs/tim_follin.py:CmdInstrument`

## Compared

- TFMX Pro and SoundFactory both let one voice change data that other voices
  read. TFMX Pro edits a program. SoundFactory edits an instrument.
- Tim Follin moves all sound control into the score. TFMX Pro and Jason Page
  move it into the instrument.
