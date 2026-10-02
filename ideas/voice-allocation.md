# Voices for music and effects

These players share Paula's four channels between the music, sound effects and
the game. They decide who gets a voice, and they pass signals between the music
and the game.

## Voice allocation

The player picks a voice for each note at note-on. No MIDI channel or track owns
a fixed voice. When no voice is free, voice stealing cuts a busy one.

- [MIDI-Loriciel](../players/MIDI-Loriciel.md): a note takes the first free
  voice. Voice stealing prefers a voice of the note's own MIDI channel.
  `specs/midi_loriciel.py:AllocateVoice`
  - Age and volume play no part.
- [MaxTrax](../players/MaxTrax.md): the note's pan picks a side with two voices.
  The freer voice of that side is taken. `specs/maxtrax.py:PickVoice`
  - A voice is freer when its envelope stage is closer to its end.
  - A voice with a sound effect or a higher priority is skipped.

## Voice masks

A song names the voices it may use. The other voices keep playing their own
songs.

- [SoundPlayer](../players/SoundPlayer.md): a song start claims the voices that
  the song names. A claimed voice stays silent until a volume command.
  `specs/soundplayer.py:ClaimVoices`
  - A voice returns to the music only when the game starts the music again.

## Effects take music voices

A sound effect takes a voice from the music while it plays. The players differ
in what the music does meanwhile.

- [David Whittaker](../players/DavidWhittaker.md): the music writes its
  registers to a shadow. When the sound effect ends, the shadow goes to Paula.
  `specs/david_whittaker.py:Shadow`
  - The music's current note keeps sounding.
- [Digital Sonix & Chrome](../players/DigitalSonixChrome.md): a sound effect is
  an instrument number. It holds the voice until its loops end.
  `specs/digital_sonix_chrome.py:SfxClaimVoice`
  - The music's notes on that voice are lost.

## Effect voice limit

The music keeps reading its stream on a voice that a sound effect holds. Paula
gets nothing from the music. Only the sound effect sounds on that voice.

- [Paul Robotham](../players/PaulRobotham.md): the muted stream stays in time.
  The music comes back at the voice's next note start.
  `specs/paul_robotham.py:MutedVoice`

## Effect priority

Notes and sound effects ask for a voice with a priority. A lower request loses.

- [Jason Page](../players/JasonPage.md): a request below the voice's priority is
  dropped, notes included. `specs/jason_page.py:RequestProgram`
  - The voice keeps its priority until its program ends.
  - A request can wait some ticks before its program starts.
  - The request takes the voice's priority at once, during that wait.

## Game sync flags

The music sets values that the game reads. The game can time its events to the
music.

- [Art Of Noise 8V](../players/ArtOfNoise-8V.md): `EXTERNAL_EVENT` passes a byte
  to the game, on the row's first tick.
  `specs/art_of_noise_8v.py:CmdExternalEvent`
- [SoundPlayer](../players/SoundPlayer.md): commands set and clear 20 flags. The
  game reads them. `specs/soundplayer.py:CmdSetFlag`

## Game branch markers

The game writes a position. The music jumps there at a marked place in the song.

- [Jason Page](../players/JasonPage.md): a looping branch entry repeats until
  the game writes a position. A passing branch entry plays on without one.
  `specs/jason_page.py:BranchLoop`
  - The first voice to take the jump clears the game's position.
  - A voice that reaches its branch entry a row later misses the jump.

## Song save slots

The game stores the song's place and returns to it later.

- [Jason Page](../players/JasonPage.md): a save stores each voice's place in one
  of four slots. `specs/jason_page.py:SaveSong`
  - The place is the position, pattern place, transpose, program and row
    counter.
  - A restore keeps each voice's priority. Later notes below that priority are
    dropped.

## Compared

When a sound effect ends, the music comes back in three ways:

- David Whittaker writes the shadow to Paula at once.
- Paul Robotham waits for the voice's next note start.
- Digital Sonix & Chrome drops the music's notes during the sound effect. The
  voice stays silent until its next music note.
