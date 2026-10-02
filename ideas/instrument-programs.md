# Instrument programs

These players differ in where an instrument's behaviour lives. It can live in a
program, in driver code or in the score. A program is flexible, at the price of
an interpreter on every voice.

## Instrument programs

An instrument program is a list of opcodes that runs once per tick on a voice.
It sets the sample, period and volume, and it waits, loops and branches.

- [TFMX Pro](../players/TFMX-Pro.md): a program, TFMX's `macro`, has 52 opcodes.
  It branches on note, volume and note-off. `specs/tfmx_pro.py:MacroStep`
  - A new note restarts only the program. Effects, volume and sample keep their
    values.
- [Jason Page](../players/JasonPage.md): notes and game sound effects request
  the same programs. A request with a lower priority than the voice's program is
  dropped. `specs/jason_page.py:RequestProgram`
  - Starting a program turns DMA off. Only the program turns it on.

## Programs that rewrite programs

A program opcode can write into the bytes of another program.

- [TFMX Pro](../players/TFMX-Pro.md): opcodes copy or add values into a program.
  Every voice that plays that program hears the change.
  `specs/tfmx_pro.py:CopyToMacro`

## Instrument drivers

Each instrument type has its own routines instead of data for shared code. The
player calls the type's routines for every voice that plays it.

- [Sonix Music Driver](../players/SonixMusicDriver.md): a driver has a tick
  routine and a routine that writes Paula registers. The synth driver and the
  sample drivers each keep their own voice state.
  `specs/sonix_music_driver.py:TickInstruments`

## Instruments inside the score

A stream holds an instrument's definition at its first use.

- [SoundFactory](../players/SoundFactory.md): an opcode stores the definition's
  address in one of 32 slots. The stream continues after the definition.
  `specs/sound_factory.py:OpDefineInstrument`
  - Effect opcodes write into the instrument, not into the voice. Every voice
    that plays it hears the change at once.

## Bare instruments

An instrument holds only a sample. The score sets every other sound property per
voice.

- [Tim Follin](../players/TimFollin.md): the track sets envelope, vibrato,
  trill, portamento and pulse sweep as voice state. Each change is a track
  command and costs bytes. `specs/tim_follin.py:CmdInstrument`

## Compared

- TFMX Pro and SoundFactory both let one voice change data that other voices
  read. TFMX Pro edits a program. SoundFactory edits an instrument.
- Tim Follin puts all sound control in the score. TFMX Pro and Jason Page put it
  in the instrument program.
