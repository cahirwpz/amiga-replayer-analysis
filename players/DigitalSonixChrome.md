---
player: DigitalSonixChrome
template: 3
ideas:
  [counted-loops, fixed-pitch-instruments, effects-steal-voices, stop-signal]
---

# Digital Sonix & Chrome

Audio interrupts count how often each instrument loops. The tick only reads
rows.

## Unique ideas

- An instrument fixes the period. A row names only an instrument per voice.
  `:SetFixedPeriod` `:ReadRow`
  - Limits: every pitch of a sound takes its own instrument.
  - Limits: there are no commands. Nothing changes a note once it plays.
- After a set number of loop passes, an instrument falls silent. The audio
  interrupt counts the passes, with no work in the tick. `:CountLoopPass`
  - Limits: a note's length is set in passes, not in rows.
- A game sound effect is an instrument number. It takes a voice until its loops
  end. `:SfxClaimVoice` `:LoopsDone`
  - Limits: the voice's music notes are lost while the sound effect plays.
- A note start waits for the channel's interrupt request, a
  [stop signal](../docs/paula-techniques.md#stop-signal). `:WaitAudioIrq`
  - Limits: the CPU busy-waits up to two periods of the old word per note.

## How it plays

The host's tick runs `:Play`. The four audio interrupts run `:CountLoopPass` for
their channel. This is
[loop counting](../docs/paula-techniques.md#loop-counting).

A tick reads a row every `speed` ticks. Then it serves the game's sound effect
requests, voice 0 to 3. `:Play`

### Player

The player holds the position, the row, the rows played and the repeats left. It
holds the subsong's first position and the tick counter. `:Module`

- `speed` is 1500 / the module's tempo, rounded. No command changes it.
  `:LoadModule`
- A position holds a pattern, its rows and its repeat count. `:Position`
- A pattern row holds one instrument number per voice, or `NO_NOTE`. `:ReadRow`

Each row, in this order: `:ReadRow`

1. Each voice reads its byte. A voice that plays a sound effect reads `NO_NOTE`.
2. Voices 0 to 3 start their notes, one after the other. `:StartNote`
3. After the pattern's last row, the pattern plays again. Its repeat count sets
   how often. `:CountRepeats`
4. Then the next position follows. `:NextPosition`
   - A position with 0 repeats ends the subsong. Play returns to the subsong's
     first position, and the host gets `SongEnd`.
   - Subsongs follow each other in the positions. `:StartSubsong`

The original replay had a song fade, which halved the volume of new notes per
step. Wanted Team's version comments it out. `:Play`

### Voice

A voice holds its passes left, its loop, its sound effect and the game's
request. A pass is one play of the sample or of its loop. `:Voice`

A note start, from the instrument: `:StartNote`

1. `NO_NOTE` changes nothing, and the voice plays on.
2. DMA goes off, and `AUDxPER` gets 1. The audio interrupt goes off, and
   `INTREQ` is cleared. `AUDxDAT` gets 0.
3. `AUDxVOL` gets the volume. `AUDxLC` and `AUDxLEN` get the whole sample.
4. The passes left get the loop count + 1. With loops, the voice keeps the loop.
   `:SetLoopCount`
5. The CPU busy-waits for the channel's interrupt request. `:WaitAudioIrq`
6. `AUDxPER` gets the instrument's period. DMA goes on, and the audio interrupt
   goes on. `:SetFixedPeriod`

Each audio interrupt, at each reload: `:CountLoopPass`

1. With passes left, it counts one down.
2. With passes still left, `AUDxLC` and `AUDxLEN` get the loop.
3. Otherwise, they get a 2-word
   [silent loop](../docs/paula-techniques.md#silent-loop).
4. With no passes left, the voice is done. Its audio interrupt goes off, and its
   sound effect becomes `FREE`. `:LoopsDone`

- With 0 loops, the sample plays once. The first interrupt already queues
  silence. `:SetLoopCount`
- Every note falls silent on its own. A voice then plays its silent loop until
  its next note.

### Sound effects

The game writes an instrument number as a voice's request. A lower number has
the higher priority. `:SfxClaimVoice`

Each tick, for each voice: `:SfxClaimVoice`

1. A request from `FIRST_IGNORED` up is ignored. It stays in place.
2. Otherwise the request is cleared.
3. A request up to the playing sound effect's number starts its note. A free
   voice holds `FREE`, and any request beats it. `:StartNote`
4. The request becomes the voice's sound effect.

- An equal number restarts the sound effect.
- **Trap:** an instrument number is both a sound and a priority. Moving a sound
  in the instrument list changes which effects win.
- **Trap:** on a row tick, a music note starts first. A sound effect then
  replaces it. Both starts busy-wait.
- **Trap:** the music reads on under a sound effect. When it ends, the voice
  stays silent until its next music note. `:ReadRow`
- **Trap:** the audio interrupt frees the voice, not the tick. A music note's
  end also sets its sound effect to `FREE`. `:LoopsDone`

## Open questions

- Wanted Team's interrupt handlers first wait for the next scanline. Did the
  original do this too?
- Did any other game use this format?
