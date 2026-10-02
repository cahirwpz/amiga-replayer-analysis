---
player: SoundPlayer
template: 3
ideas: [attach-modes, per-voice-positions, game-sync-flags, voice-masks]
---

# SoundPlayer

Row commands switch Paula's attach modes, and a song takes only the voices in
its mask.

## Unique ideas

- A command turns an [attach mode](../docs/paula-techniques.md#attach-modes) on
  or off. One channel's sample then sets the next channel's volume or period.
  `:CmdVolModOn` `:CmdPerModOn`
  - Limits: in the HRM, the modulating channel is silent. The song loses a
    voice.
- A song takes the voices in its mask. The other voices play on in their own
  songs. `:StartSong` `:ClaimVoices`
  - Limits: a voice returns to the music only when the game starts the music
    again.
- Each voice reads its own column of the rows, from its own place. Waits and
  repeats count per voice. `:Track` `:VoiceWait`
  - Limits: the columns drift apart. Rows no longer line up as written.
- Commands set and clear 20 flags that the game reads. `:CmdSetFlag`
  `:GameReadsFlag`
- An instrument is an IFF 8SVX sample with two sample regions: one played once,
  one looped. A hold command loops the playing region until a release command.
  `:CmdHold` `:HoldOrRelease`

## How it plays

A [CIA timer](../docs/paula-techniques.md#cia-timer) interrupt runs the tick. A
song's header sets the timer, unless its first byte is `KEEP_TIMER`.
`:ClaimVoices`

A tick runs volume slides, then note starts, for all four voices. `:Tick`

Every sixth tick is a row tick. It moves tracks on, reads rows, stops channels
for new notes and runs commands.

### Player

The player holds the tick counter, 20 game flags and the attach modes. It holds
the audio filter. `:Module`

- The counter runs 0, 5, 4, 3, 2, 1. A row comes every six ticks. `:RowTimer`
  - No command changes `speed`.
- A song start rewinds the song's four tracks. Each voice in its mask takes its
  track. `:StartSong` `:RewindSong`
  - A voice taken gets volume 0. Its first note is silent without a volume
    command. `:ClaimVoices`
  - **Trap:** hold and slide are voice state. They carry over from the last song
    on the voice.
- The game can silence voices. DMA goes off, and the voices play song 0.
  `:SilenceVoices`
- A game fade slides the voices in a mask down. `:GameFade`
  - **Trap:** during a fade, volume commands do nothing. A slide command still
    turns the fade around. The next song on the voice ends the fade.
- Attach modes and the audio filter are global. Any voice's command changes
  them, also in a sound effect song. `:CmdVolModOn`

### Track

A track is one voice's place in one song. Each song holds four. `:Track`

A track holds a position, a repeat mark, a repeat count and a wait.

- A song holds 12-byte rows: a note, an instrument number and a command per
  voice. `:Song`
- A track starts one row before the first. A row tick moves on before it reads.
  `:Track`
- The repeat state and the wait belong to the track, not the voice. A song start
  rewinds only its own tracks. `:RewindSong`

### Voice

A voice holds its track, its row bytes and the instrument. `:Voice`

It holds two sample regions: the one to start, and the looped one. It holds the
period, volume, hold and a volume slide.

Each tick, before the row: `:Tick`

1. Unless held, `AUDxLC` and `AUDxLEN` get the looped region, or one empty word.
   Paula takes it when the playing region ends. `:HoldOrRelease`
   - **Trap:** held, nothing is written. After a note, its first region loops.
2. A volume slide steps every 1 to 10 ticks, between 0 and 63. It writes
   `AUDxVOL`. `:VolumeSlide`
   - At the limit, the next step ends the slide.
3. A pending note writes `AUDxLC`, `AUDxLEN`, `AUDxPER` and `AUDxVOL` from the
   voice. It turns DMA on. `:NoteRestart`
   - It sets the instrument's played flag, which the game reads.
   - **Trap:** an instrument without a first region never starts. DMA stays off.

At a row tick, in this order for all voices, then the next step:

1. A waiting voice counts its wait down. Else it moves one row on. `:VoiceWait`
2. A voice that does not wait reads its three bytes. `:ReadRow`
   - A waiting voice reads nothing, so its row's note does not repeat.
3. A note turns DMA off and sets the period. It takes the instrument's regions.
   `:NoteStop`
   - **Trap:** the note starts one tick later. Every note has a silent tick
     before it.
   - An instrument has no volume. A note keeps the voice's volume.
   - The period table skips B-0. Note 3 is A#0, note 4 is C-1. Notes 38 and 39
     are above Paula's period limit.
4. The command runs. `:RunCommand`
   - A range of bytes names a command. The byte's place in its range is the
     argument.
   - One command per voice per row.

Commands that change flow:

- A wait command makes a row last 1 to 50 rows. A running wait is kept.
  `:CmdWait`
- A repeat start marks the row. A repeat end goes back to the row after it.
  `:CmdRepeatStart` `:CmdRepeatEnd`
  - With N repeats, the rows play N + 1 times.
  - **Trap:** while a repeat is open, a repeat start does nothing. Repeats do
    not nest.
- A step back plays its own row again at every row tick. Its note restarts each
  time. `:CmdStepBack`
  - The voice stays there until the game starts another song on it.
- A restart sends only its own voice back to the first row. `:CmdRestart`

A voice falls silent in four ways:

- A stop command turns DMA off. `:CmdStop`
- A sample without a looped region ends on one empty word, a
  [silent loop](../docs/paula-techniques.md#silent-loop). `:HoldOrRelease`
- A slide down or a game fade reaches volume 0. `:VolumeSlide`
- The game silences the voice. `:SilenceVoices`

## Open questions

- Did the Lemmings songs use modulation for timbre or for effects?
- Do sound effect songs end on a step back, to park the voice (guess)?
  `:CmdStepBack`
- Period modulation from channel 2 has an off handler, but no command byte
  reaches it. Is this a bug? `:CmdPerModOff2`
