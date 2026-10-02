# Score streams

In these players, voices do not read shared rows. Each voice steps through its
own stream, list of events or program. Voices can then differ in length and
timing.

## Positions per voice

Each voice keeps its own position in the song. Its patterns can differ in length
from the other voices' patterns.

- [Jason Page](../players/JasonPage.md): each voice has its own position list
  and row length. `specs/jason_page.py:Sequencer`
- [Musicline Editor](../players/MusiclineEditor.md): each voice also has its own
  `speed` and swing. `specs/musicline.py:PlayVoice`
- [SoundPlayer](../players/SoundPlayer.md): each voice reads its own column of
  the rows. Waits and repeats count per voice. `specs/soundplayer.py:VoiceWait`

## Streams per voice

Each voice reads one byte stream of notes and commands. Calls and loops replace
patterns.

- [Paul Robotham](../players/PaulRobotham.md): loops nest on a stack. A part
  that two voices play is stored twice. `specs/paul_robotham.py:LoopEnd`
- [SoundFactory](../players/SoundFactory.md): a stack per voice holds calls,
  jumps and loops. `specs/sound_factory.py:ReadStream`
- [Voodoo Supreme Synthesizer](../players/VoodooSupremeSynthesizer.md): calls
  and loops share one stack of 20 entries. Nothing checks for overflow.
  `specs/voodoo_supreme_synthesizer.py:CmdCall`

## Track programs

A track program runs beside the notes and sets the sound.

- [Face The Music](../players/FaceTheMusic.md): a program is a list of 4-byte
  lines. It runs until a line waits. `specs/face_the_music.py:ScriptRun`
- [Tim Follin](../players/TimFollin.md): the track sets the voice's envelope,
  vibrato and sweeps. The instrument is only a sample.
  `specs/tim_follin.py:ReadTrack`

## Tracks, not voices

The score has more tracks than Paula has channels. A track is not tied to one
voice.

- [Face The Music](../players/FaceTheMusic.md): two tracks share each channel by
  [mixing](voice-mixing.md). `specs/face_the_music.py:MixPairs`
- [TFMX Pro](../players/TFMX-Pro.md): eight tracks share four voices. Each note
  names its voice. `specs/tfmx_pro.py:NoteToVoice`

## Event score

The score is a list of events, not rows. A wait event holds the time to the next
event.

- [Sonix Music Driver](../players/SonixMusicDriver.md): a wait event counts
  ticks, like a MIDI sequencer's delta time. Every note is stored, with no
  patterns. `specs/sonix_music_driver.py:ReadEvent`

## MIDI score

The score follows a MIDI sequencer's model: timed note-on and note-off events.

- [MIDI-Loriciel](../players/MIDI-Loriciel.md): the score is an SMF. Only
  note-on, note-off, program change and tempo act.
  `specs/midi_loriciel.py:ChannelEvent`
- [MaxTrax](../players/MaxTrax.md): one list of timed events. Each note carries
  its length, so no note-off event is needed. `specs/maxtrax.py:ReadEvents`

## Packed lengths

A note length fits one byte as a value and a shift.

- [Paul Robotham](../players/PaulRobotham.md): 5 bits of value and 3 bits of
  shift give 1 to 3968 pulses. A length with more than five significant bits
  needs a tie. `specs/paul_robotham.py:ReadLength`

## Length remainder

Lengths count in pulses, but the replay runs in ticks. The division leaves a
remainder.

- [Paul Robotham](../players/PaulRobotham.md): each voice keeps the remainder
  for its next length. Voices never drift apart, at any tempo.
  `specs/paul_robotham.py:ReadLength`

## Shared counter

Voices with their own streams lose step. A shared counter lets one voice wait
for another.

- [SoundFactory](../players/SoundFactory.md): one voice counts the counter up.
  Another waits until it holds a value. `specs/sound_factory.py:OpWaitSignal`

## Counted loops

A note ends after a set number of loop passes. Its length is not set in time.

- [Digital Sonix & Chrome](../players/DigitalSonixChrome.md): the audio
  interrupt counts the passes. The tick does no work for it.
  `specs/digital_sonix_chrome.py:CountLoopPass`

## Random offset loops

A loop plays a list of note offsets over the playing note.

- [TFMX Pro](../players/TFMX-Pro.md): an offset loop, TFMX's `riff`, reads
  another program's bytes as offsets. It can jump at random and echo on the next
  voice. `specs/tfmx_pro.py:RiffTick`

## Compared

- Streams per voice drift apart unless the composer counts ticks. Paul Robotham
  keeps the length remainder, so its voices stay in step.
- SoundFactory keeps voices in step with a shared counter instead.
- SoundPlayer's columns drift apart. Rows no longer line up as written.
