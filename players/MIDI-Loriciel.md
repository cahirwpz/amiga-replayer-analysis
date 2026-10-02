---
player: MIDI-Loriciel
template: 3
ideas: [midi-score, voice-allocation, multisamples]
---

# MIDI-Loriciel

An SMF plays on four allocated voices, and each note plays its sample once.

## Unique ideas

- The score is an SMF. Only note-on, note-off, program change and tempo act.
  `:ChannelEvent` `:ReadMeta`
  - Limits: no CC, no pitch bend, no running status.
  - Limits: at most 16 tracks. A 17th overwrites the player's state.
    `:InitTrack`
- Voice allocation takes the first free voice. Voice stealing prefers the MIDI
  channel's own voices. `:AllocateVoice`
  - Limits: age and volume play no part. A fifth note cuts a playing note.
- A sample bank (`BNKS`) gives each MIDI program a multisample. A zone is one of
  its samples, with a top note and a note offset. `:Bank` `:Zone`
  - Limits: a note above the last zone reads past the list.
  - Limits: the period table has 60 entries. Its 11 shortest periods are too
    fast for DMA.
- Velocity sets the volume once, through a fixed curve. `:SetVelocity`
  - Limits: the volume never changes during a note.
- A sample plays once. Each tick, every voice that holds a note queues silence.
  `:SilentTail`
  - Limits: a held note falls silent when its sample ends.
  - Limits: the bank's loops are never used.
- A tick is four pulses. Tempo sets the timer's rate. `:TrackTick` `:SetTempo`
  - Limits: events closer than four pulses slip to a later tick.

## How it plays

A [CIA timer](../docs/paula-techniques.md#cia-timer) interrupt runs the tick.
There is no audio interrupt and no VBL work. `:PlayTick`

A tick advances each active track by four pulses, in file order. Then every busy
voice queues silence. `:PlayTick`

### Player

The player holds the PPQ, the count of active tracks and the passes left.
`:Module`

- Tempo sets the tick rate: the pulses per second, divided by four. `:SetTempo`
  - The rate is a whole number of ticks per second. At 48 Hz, it can be 2 % off.
  - The timer's rate assumes the NTSC clock. On PAL, the song plays 0.9 % slow.
    `:SetTimer`
  - Before the first tempo event, a quarter note lasts half a second.
    `:StartSound`
- The header's division gives the PPQ. A negative division gives 192 PPQ.
  `:InitTracks`
- Once every track has ended, a tick restarts the tracks, voices, programs and
  tempo. That tick plays no event. `:RestartSong`
- The game sets how many passes play. After the last, the timer stops.
  `:PlayTick`
  - All voices get DMA off and volume 0. `:ResetVoices`

### Track

A track is one `MTrk` chunk. It holds its position, its wait in pulses and its
MIDI channel. `:Track`

Each tick, an active track runs these steps: `:TrackTick`

1. At its first visit, it reads its first delta time. Later visits subtract four
   pulses from the wait.
2. At a wait of zero or less, the waiting event runs. `:ReadEvent`
3. It reads the next delta time. A zero delta runs the next event in this visit.
   `:ReadDelta`
4. A positive delta adds to the wait and ends the visit. `:SaveWait`
   - The wait keeps its negative remainder. The average stays in time.
   - A positive delta ends the visit, even when the new wait is zero or less.

- **Trap:** events in one tick play in track order, not in time order. That
  order decides voice allocation. `:PlayTick`

Each event needs its status byte. `:ReadEvent`

- **Trap:** with running status, a data byte reads as a status byte. It sets the
  track's MIDI channel and skips two bytes. `:ChannelEvent`
- Other channel and system events skip two bytes. Channel pressure has one.
  `:SkipTwoBytes`
- Sysex and other meta events skip their length. `:SkipSysex` `:SkipMeta`
- A channel prefix meta event sets the track's MIDI channel. The next channel
  event overwrites it. `:ChannelPrefix`
- The end meta event stops the track. Without it, the track reads on into the
  next chunk. `:EndTrack`
- A note-on with velocity 0 is a note-off. `:NoteOnEvent`

### MIDI channel

Each of the 16 holds its instrument and its latest voice. The latest voice is
the voice of its last note-on. `:MidiChannel`

- All start with the bank's first program. `:ResetMidiChannels`
- A program change sets the instrument for later notes. Playing notes keep their
  sample. `:SelectProgram`
  - A program beyond the bank reads past it.
- A note-off reaches only the latest voice. It acts only if that voice still
  plays this MIDI channel and note. `:MatchNoteOff`
  - **Trap:** after two notes of different pitch, the first note's note-off does
    nothing. Its voice stays busy until it is stolen.
  - **Trap:** after two notes of the same pitch, the first note-off ends the
    second note.

### Voice

A voice is busy from its note-on until a note-off frees it. It holds its MIDI
channel and note. `:Voice`

A note-on runs these steps: `:StartNote`

1. Voice allocation takes the first free voice, from voice 0 up.
   `:AllocateVoice`
   - With none free, it steals the MIDI channel's last busy voice, else voice 0.
   - The voice becomes its MIDI channel's latest voice.
2. The first zone whose top note is at or above the note wins. `:FindSampleZone`
3. `AUDxLC` and `AUDxLEN` get the zone's whole sample. `:SelectSample`
4. `AUDxPER` gets the period of the note minus the zone's note offset.
5. `AUDxVOL` gets the curve's value plus the game's offset, within 0 to 31,
   doubled. `:SetVelocity`
   - The curve is steep up to velocity 32 and flat above. Velocity 64 gives
     volume 40, with the default offset.
   - **Trap:** the game's offset is global. Only notes that start later hear a
     change. `:SetVolumeOffset`
6. DMA goes on. A busy-wait of about 3,600 CCK follows (estimate).
   - **Trap:** a stolen voice gets no DMA off. Its new sample waits for a
     reload.
   - **Trap:** the tick's end queues silence over that sample. `:SilentTail`
   - Without that reload, the note is silent. Or the old sample plays on at the
     new period and volume.

At each tick's end, every busy voice's `AUDxLC` and `AUDxLEN` get 8 words of
zeros. Paula takes them at the next reload, as a
[silent loop](../docs/paula-techniques.md#silent-loop). `:SilentTail`

A note-off turns DMA off at once, with no release. A busy-wait follows.
`:StopNote`

A voice falls silent at its sample's end, at its note-off, or at the song's end.

## Open questions

- Do the scores overlap notes on one MIDI channel? The note-off traps depend on
  it.
