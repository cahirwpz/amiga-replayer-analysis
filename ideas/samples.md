# Sample use

These players choose, join or package samples in ways a plain tracker does not.
Each idea costs little code, but changes what one instrument can sound like.

## Multisamples

A multisample gives one instrument several samples. Each sample covers a range
of notes. No sample then plays far from its recorded pitch.

- [MIDI-Loriciel](../players/MIDI-Loriciel.md): a zone is one sample with a top
  note and a note offset. A note plays the first zone whose top note is at or
  above it. `specs/midi_loriciel.py:FindSampleZone`
- [MaxTrax](../players/MaxTrax.md): an instrument holds one sample per octave.
  The player takes the first sample whose period is at most about 508.
  `specs/maxtrax.py:CalcNote`

## Sample chaining

A note plays two samples in a row. The first sample is an attack, and the second
one loops.

- [Tim Follin](../players/TimFollin.md): a second sample can follow one tick
  after the note starts. The first sample plays once, and the second loops.
  `specs/tim_follin.py:ChainSample`

## Sample pack

A sample pack is one sample that holds several samples. A command picks one of
them by number.

- [Future Composer 1.4](../players/FutureComposer1.4.md): the pitch list's
  `PACK` command picks one of up to 20 samples. The pack needs its own header.
  `specs/future_composer_14.py:SampleFromPack`

## Replay in the module

The music file carries its own replay code. The host calls the replay through
entry points at the start of the file.

- [David Whittaker](../players/DavidWhittaker.md): the module is the replay,
  with its entry points first. `specs/david_whittaker.py:InitSong`
- [Fred](../players/Fred.md): the module starts with jumps to its entries.
  `specs/fred.py:InitSong`
- [Rob Hubbard](../players/RobHubbard.md): the module starts with five jump
  entries. Every module repeats the 830 bytes of replay code.
  `specs/rob_hubbard.py:InitSong`

## Attach modes

An attach mode lets one channel's sample set the next channel's volume or
period. See [attach modes](../docs/paula-techniques.md#attach-modes).

- [SoundPlayer](../players/SoundPlayer.md): a row command turns an attach mode
  on or off. In the HRM, the modulating channel is silent and costs the song a
  voice. `specs/soundplayer.py:CmdPerModOn`

## Compared

- MIDI-Loriciel picks a sample by note range. MaxTrax picks a sample by octave.
  Each lower octave doubles the sample's size.
- A replay in the module gives each game the replay its music was written for.
