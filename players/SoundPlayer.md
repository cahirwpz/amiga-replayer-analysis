---
player: SoundPlayer
template: 2
ideas: [attach-modes, per-voice-positions, game-sync-flags, voice-masks]
---

# SoundPlayer

Row commands switch Paula's attach modes, and a song takes only the voices in
its mask.

## Context

| Fact      | Value                                                            |
| --------- | ---------------------------------------------------------------- |
| Player    | `SoundPlayer`                                                    |
| Author    | Scott Johnston                                                   |
| Year      | 1991                                                             |
| Game      | Lemmings                                                         |
| Code read | disassembly: `ext/uade/amigasrc/players/wanted_team/SoundPlayer` |
| Spec      | [specs/soundplayer.py](../specs/soundplayer.py)                  |

## Key ideas

- A command turns an attach mode on or off. In an attach mode, one channel's
  sample sets the next channel's volume or period. `:CmdVolModOn` `:CmdPerModOn`
  - Enables: volume or period curves from sample data, with no CPU work.
  - Costs: the modulating channel is silent. The song loses a voice. See
    [Paula](../docs/paula.md).
- A song takes the voices in its mask. The other voices play on in their own
  songs. `:StartSong` `:ClaimVoices`
  - Enables: a sound effect as a song on one voice, while the music keeps the
    others.
  - Costs: the voice returns to the music only when the game restarts the music.
- Each voice reads its own column of the rows, from its own place. Waits and
  repeats count per voice. `:VoiceWait` `:ReadRow`
  - Enables: a short loop on one voice under a long line on another.
  - Costs: the columns drift apart. Rows no longer line up as written.
- Commands set and clear 20 flags that the game reads. `:CmdSetFlag`
  `:GameReadsFlag`
  - Enables: game events in time with the music.
- An instrument is an IFF 8SVX sample with a one-shot region and a loop region.
  A hold command loops the playing region until a release command.
  `:HoldOrRelease`
  - Enables: a held sound and its ending from one sample.

## Composer's view

The composer writes one list of rows. Each row gives each voice a note, an
instrument and a command. The song's header sets the tick rate and the voice
mask.

| Aspect   | Answer                                                                       | Source          |
| -------- | ---------------------------------------------------------------------------- | --------------- |
| Notation | A range of bytes names a command.                                            | `:RunCommand`   |
| Notation | The byte's place in its range is the argument.                               | `:RunCommand`   |
| Notation | The header sets a CIA timer value.                                           | `:ClaimVoices`  |
| Notation | `KEEP_TIMER` keeps the running rate.                                         | `:ClaimVoices`  |
| Cost     | One command per voice per row.                                               | `:ReadRow`      |
| Cost     | A wait command makes a row last 1 to 50 rows.                                | `:CmdWait`      |
| Cost     | A note starts one tick after its row. The tick before is silent.             | `:NoteStop`     |
| Cost     | A song starts its voices at volume 0. The first note needs a volume command. | `:ClaimVoices`  |
| Cost     | A repeat of N plays its rows N + 1 times.                                    | `:CmdRepeatEnd` |
| Cost     | Repeats do not nest.                                                         | `:CmdRepeatEnd` |
| Cost     | A row lasts six ticks. No command changes that.                              | `:RowTimer`     |
| Cost     | An instrument without a one-shot region never sounds.                        | `:NoteRestart`  |

## What is unique

- An instrument has no volume. A note keeps the voice's volume. `:NoteStop`
- One command plays its own row again at every row. The voice stays there until
  the game starts a new song on it. `:CmdStepBack`
- One command sends only its own voice back to the first row. `:CmdRestart`
- Any voice's command can link any channel to the next one. `:CmdVolModOn`
- During a game fade, volume commands do nothing until a song takes the voice
  again. `:GameFade`

## Open questions

- Did the Lemmings songs use modulation for timbre or for effects?
- Do sound effect songs end by replaying their last row, to park the voice
  (guess)? `:CmdStepBack`
- Period modulation from channel 2 has a handler but no command byte. Is this a
  bug? `:CmdPerModOff2`
