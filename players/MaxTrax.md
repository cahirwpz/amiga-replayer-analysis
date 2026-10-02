---
player: MaxTrax
template: 3
ideas: [midi-score, voice-allocation, multisamples, log-pitch]
---

# MaxTrax

A MIDI-like score for 16 MIDI channels plays on 4 voices, through audio.device.

## Unique ideas

- The score is one list of timed events. Each note carries its length.
  `:ReadEvents`
  - Limits: each event costs 6 bytes.
  - `MARK` events split one score into subsongs. `:PlaySong` `:SkipMarks`
- Voice allocation picks a voice per note, by side, status and priority. Pan
  picks a side, not a level. `:PickVoice` `:PanSide`
  - Limits: voice stealing cuts a busy voice off at once. `:StealVoice`
- The game plays notes and sound effects on the music's voices. A `SYNC` event
  signals the game. `:ExtraNote` `:ExtraSound` `:SyncEvent`
- An instrument is a multisample with one sample per octave. `:OctaveShift`
  - Limits: each lower octave doubles the sample's size.
- Pitch adds note, pitch bend, portamento and tuning in 1/256 semitones. A log
  table of 257 words gives the period. `:CalcNote` `:IntAlg`
- Envelopes count in ms, the same at any tempo. `:EnvelopeRamp`
  - Limits: each segment is a straight line to a target volume.

## How it plays

The vertical blank interrupt causes a software interrupt that runs the tick.
Each game call causes a second one and busy-waits for it. `:MusicServer`

The replay writes no Paula register. Its requests to audio.device set `AUDxLC`,
`AUDxLEN`, `AUDxPER`, `AUDxVOL` and DMA. `:AudioDevice`

A tick runs the stop events, the due events, the tempo slide, then the voices.

### Player

The player holds the score, the next event, the score clock in pulses and the
tempo. Each voice has one stop event: a note, a MIDI channel and a countdown.
`:Module` `:StopEvent`

Each tick: `:MusicServer`

1. The score clock gains one tick's pulses, from the tempo at 192 PPQ.
   `:ScoreClock`
2. Each stop event counts down, in pulses or in ms for a game note. At 0, it
   releases its voice, if the voice still plays its note. `:StopCountdown`
3. The due events run. Past scanline 128, the rest wait a tick. `:BeamBudget`
4. The tempo slides linearly. `:ContinueTempo`
   - A slide to a slower tempo overshoots high until its end (bug).
5. Each voice runs its envelope. `:EnvelopeManager`

An event holds a command, a data byte, a start delta and a stop field. `:Event`

- A note's velocity is the data byte's high nibble. Its stop field becomes its
  voice's stop event. `:SetStopEvent`
  - A note with velocity 0 never plays. Only lengths end notes. `:NoteOn`
- A tempo event sets the tempo, or slides over its length. `:TempoSlide`
- `BEGIN_REPEAT` and `END_REPEAT` repeat a section, nested 4 deep. A jump back
  sets the clock to 0. `:EndRepeat`
  - **Trap:** a fifth `BEGIN_REPEAT` is ignored. Its `END_REPEAT` acts on the
    fourth section. `:BeginRepeat`
- The end event loops the score or stops it. `:ScoreEnd`
  - **Trap:** a loop keeps the last tempo, unless the score sets one.

A song start stops all voices and resets the controllers. It starts at a marker,
at the score's start tempo. `:PlaySong`

- **Trap:** each MIDI channel keeps its program from before. Events before the
  marker never run.
- The game's skip to a marker keeps the clock. `:AdvanceSong`

### MIDI channel

A MIDI channel holds its instrument, called `patch`, and its controllers. Its
altered flag makes its voices recompute pitch and volume this tick. `:Channel`
`:PitchBend`

| Event | Effect                                         |
| ----- | ---------------------------------------------- |
| CC 6  | Below center, a new bend range bends up (bug). |
| CC 7  | Scales only notes that start later.            |
| CC 10 | Below 64, the right side.                      |
| CC 10 | At 64, even MIDI channels go right.            |
| CC 64 | While down, a release waits.                   |
| CC 65 | Portamento works only in mono mode.            |

- **Trap:** CC 65 off writes `NO_NOTE` through the wrong register, into the
  score. The last note stays. `:PortaOffBug`

### Voice

A voice holds its MIDI channel, instrument, status, envelope, base note and end
note. A lower status is freer: `ENV_FREE` first, `ENV_START` last. `:Voice`

A note start: `:NoteOn`

1. In mono mode with portamento, a voice not yet released moves to the new note.
   It keeps sample and envelope. `:MonoLegato`
2. Otherwise voice allocation picks a voice. A busy one gets `CMD_FLUSH`.
   `:StealVoice`
3. The note volume is the velocity, if `MUSIC_VELOCITY` is set. CC 7 scales it.
4. The octave sample is the first whose period is at most `PREF_PERIOD`, about
   508\. `:CalcNote`
5. The attack region plays once. The sustain region loops after it, at
   `AUDxVOL` 0. `:QueueAttack` `:QueueSustain`

Each tick, a voice in sustain waits for a pitch change. Otherwise: `:DoOneVoice`

1. The status moves to the attack or release segments. `:EnvelopeStep`
2. The envelope volume ramps to the segment's target. `:EnvelopeRamp`
3. `AUDxVOL` is the scaled product of game, note and envelope volume, at most
   64\. `:CalcVolume`
4. Portamento moves to the end note in the portamento time, at any interval.
   - **Trap:** a recompute keeps the octave sample. A wide bend plays it far
     from its range. `:CalcNote`
5. `ADCMD_PERVOL` sends `AUDxPER` and `AUDxVOL`. A period out of range plays at
   volume 0.

A voice falls silent when its release segments end. Next tick, `CMD_FLUSH` frees
it. `:NoteOff` `:KillVoice`

### Voice allocation

Voices 0 and 3 are the left side, 1 and 2 the right. Each side holds a
round-robin value. `:PickVoice`

1. A side with no voice at `ENV_RELEASE` or freer yields to the other side.
2. On a side, the lower status wins. A tie goes by the round-robin.
   `:PickSibling`
3. A voice with a sound effect, or a higher priority, is skipped.
   - **Trap:** a sound effect's voice has status `ENV_FREE`. Its side looks
     free. A note may steal its busy sibling instead.

### Game

- A game note plays at `PRI_NOTE`. Its length counts in ms. `:ExtraNote`
  - **Trap:** its volume counts only while `MUSIC_VELOCITY` is set.
- A sound effect plays a raw sample at `PRI_SOUND`. Each tick checks its end.
  `:SoundPlaying`
  - A stereo sound takes a left and a right voice. `:ExtraSound`
