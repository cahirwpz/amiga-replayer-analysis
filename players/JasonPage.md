---
player: JasonPage
template: 3
ideas:
  [
    instrument-programs,
    effect-priority,
    game-branch-markers,
    song-save-slots,
    per-voice-positions,
    wave-morph,
  ]
---

# Jason Page

Notes and game sound effects ask for the same instrument programs. A priority
decides which one gets the voice.

## Unique ideas

- A request below the voice's priority is dropped, notes included.
  `:RequestProgram`
  - Limits: a voice keeps its priority until its program ends. `:OpEnd`
- Each voice has its own position list and row length: the rows a note lasts.
  `:Sequencer`
- Two branch entries take a position that the game wrote. One loops until then,
  the other plays on. `:BranchLoop` `:BranchPass`
  - Limits: every voice must reach its branch entry in the same row.
- The game can save the song's place in one of four slots, and restore it.
  `:SaveSong`
- A program can move the looped sample part every tick. `:OpMoveStart`
  `:OpAddOffset`
- A program can copy a wave, or morph it one step per byte towards another.
  `:OpMorph`
- The master volume caps each voice instead of scaling it. A fade reaches loud
  voices first. `:WriteChannel`

## How it plays

The host's timer tick runs the replay. There is no audio interrupt. `:Play`

A tick reads rows, then runs each voice's request, program, vibrato, portamento
and envelope. Last, it writes all four channels. `:TickVoices`

### Player

The player holds the song, `speed`, a tick counter and the game jump: a
requested position. It also holds four save slots, the master volume and a fade.
`:Module` `:SaveSlot`

- The game's command word picks the song, a slot, save or restore, and the first
  position. `:StartSong`
- A fresh start puts every voice at priority 0, in the idle program. The idle
  program sets volume 0 and yields forever.
- A save keeps each voice's position, pattern place, transpose, program number
  and row counter. It stops the song. `:SaveSong`
- A restore puts each voice in the idle program until its next note.
  `:RestoreSong`
  - **Trap:** a restore keeps each voice's priority. Notes below it stay lost.
- A fade moves the master volume by a step per tick, up to its target. `:FadeTo`
- A row comes every `speed` + 1 ticks. It copies the game jump for this row.
  `:Sequencer`

### Voice

A voice holds its position, pattern place, transpose, note and program number.
It holds a row counter, a row length and a portamento. `:Voice`

It holds a priority and a request: a program number and its delay. Its pattern
ceiling is a volume cap from the pattern.

At each row, the row counter counts down. At its end, it reloads, and:

1. The voice reads position words until a pattern. A word holds a pattern and a
   transpose, or a branch entry and its target. `:ReadPosition`
   - **Trap:** the first voice at `SONG_END` stops the song. Later voices skip
     this row.
   - **Trap:** the first `GAME_LOOP` or `GAME_PASS` that takes the game jump
     clears it. Voices that reach theirs a row later loop or play on.
     `:BranchLoop`
2. It reads pattern bytes until a note, a rest or a command. `:ReadPattern`
   - Other bytes set the row length or the program number. Both hold for later
     notes.
   - `SLIDE` starts a portamento with no target. `CEILING` sets the pattern
     ceiling. `PATTERN_END` moves to the next position.
3. A note requests the program, unless it is `SLIDE_TO_NOTE` or `FIRST_TIE`. If
   the request fails, the note is lost. `:NotePeriod`
   - **Trap:** a request takes the priority at once, before its delay ends.
4. The note plus the transpose sets the period. Notes above `HIGHEST_NOTE` play
   as it.
   - With `SLIDE_TO_NOTE`, a portamento runs to it, at the next byte's speed.
     `:NoteSlide`
   - With `FIRST_TIE`, the note is a tie. It sets only the period.

Each tick, a request waits out its delay. Then its program starts, and runs at
once. `:StartProgram`

- The start turns DMA off and writes 0 to `AUDxVOL`. It resets the window,
  envelope, vibrato, portamento, waits, loops and sustain cap.
  - **Trap:** a program start ends a `SLIDE` portamento. A tie keeps it.

### Instrument program

A program is a list of word opcodes, most with one word argument. It sets the
sample, length, period, volume, ADSR and vibrato. `:RunProgram`

It holds a wait, four loop slots and a window: the sample part the channel
loops. The window has a start, a length and an offset. `:OpSample` `:OpLength`

- Opcodes run until one yields. `OpWait` yields for N ticks. `:OpWait`
- `OpLoopStart` takes a count, 0 for ever. Four slots are reused in turn.
  `:OpLoopStart`
- `OpNote` sets a fixed note. `OpNoteOffset` plays note + offset, keeping the
  note. `:OpNoteOffset`
  - An arpeggio is a loop of `OpNoteOffset` and waits.
- `OpDmaOn` turns DMA on. A program must start the sound itself. `:OpDmaOn`
  - **Trap:** DMA goes on before this tick's `AUDxLC` write. The first pass may
    play the last window written (guess).
- `OpCeiling` copies the pattern ceiling into the sustain cap. `:OpCeiling`
  - **Trap:** a sound effect's `OpCeiling` takes the music's ceiling.
- `OpStop` silences the voice and keeps its priority. `OpEnd` also sets priority
  0 and runs the idle program. `:OpEnd`

After the program, in this order: `:VibratoSlide` `:EnvelopeTick`

1. Vibrato adds its step to the period, and turns after its length. It starts
   half-way.
   - **Trap:** vibrato adds to the period itself. An arpeggio step drops its
     offset.
2. The portamento adds its step to the period, up to its target. It stays on.
3. Attack adds its step for its count + 1 ticks, then decay subtracts. Sustain
   caps the volume at the sustain cap, for its ticks. Release subtracts to 0.
   - No note-off starts the release.
   - **Trap:** an envelope step overwrites the program's volume with its level.

Then each channel gets its registers: `:WriteChannel`

1. `AUDxVOL` gets the volume's high byte / 4, capped at the master volume / 4.
2. With a window, it writes `AUDxLC`, `AUDxLEN` and `AUDxPER` each tick, as
   [loop by reload](../docs/paula-techniques.md#loop-by-reload).
   - **Trap:** `AUDxLC` is start + length in bytes − offset. `OpAddLength` moves
     `AUDxLC`, too.

A voice falls silent by `OpStop`, `OpEnd` or a new program, with DMA off. A
release to 0 leaves DMA on. `:Silence`

### Sample memory

All voices share the samples. Programs edit them as
[live wave edits](../docs/paula-techniques.md#live-wave-edits). `:OpCopyWave`

- `OpCopyWave` copies 128 bytes from one sample over another. No note restores a
  wave.
- `OpMorph` moves 128 bytes of the last `OpSample` one step towards another
  sample. `OpMoveStart` does not move them. `:OpMorph`
  - **Trap:** bytes compare unsigned. A byte that crosses 0 sweeps through +127
    and -128.

## Open questions

- Restoring a slot writes into later slots, and from slot 1 into sample
  pointers. Did a game use those slots? `:RestoreSong`
- Which games used the branch entries, and for what? `:BranchLoop`
- Why does the header hold eight position lists, when voices use four?
  `:InitModule`
