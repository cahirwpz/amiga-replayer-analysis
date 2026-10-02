---
player: SynthDream
template: 3
ideas: [pulse-width-table, soft-edge-pulse, run-length-tables, glide-to-fit]
---

# Synth Dream

A 16-byte pulse wave gets finer width steps from a soft edge byte.

## Unique ideas

- A pulse table value picks the pulse width in sixteenths. Its second byte
  lowers the first high byte, for widths in between. `:PulseWalker`
  - Limits: the replay rebuilds the wave every tick.
- Each table is a list of runs, and a run can repeat. `:Runs`
  - Limits: every event restarts all four tables.
- An event holds its length in ticks. There are no rows and no speed.
  `:ReadEvent` `:NoteEvent`
- A portamento can fit its rate to the note. It then ends as the note ends.
  `:GlideToFit`
- The fine table, the portamento and the instrument's shift scale the period. A
  ratio step is 1/400 semitone, about 1/4 cent. `:FineWalker` `:Glide`
  `:ShiftPitch`
  - Detune and slides sound the same in every octave.
  - Limits: the ratio tables span a semitone. Larger values read past
    (estimate).
- A position can swap one instrument for another. `:LoadInstrument`

## How it plays

The host's timer calls the tick. There is no audio interrupt. `:Play`

A tick runs voices 0 to 3. A voice reads an event when its last one ends. Then
it runs its table switches, walkers, portamento and registers.

### Voice

A voice holds its positions, pattern, event, ticks left and length. It holds its
note, transpose, two volume offsets, instrument and flags. `:Voice`

Its flags are legato and rest. It also holds four walkers, a portamento and two
pending table switches.

An event is a word opcode and its arguments: length, note, volume, instrument or
portamento. `:NoteEvent`

At an event's end, the voice reads on: `:VoiceTick`

1. It clears the portamento, the note table's offset and the rest flag.
2. At `PATTERN_END`, it plays the pattern again while the position's repeats
   last. Then it reads the next position. `:RepeatPattern`
3. A position holds a pattern, a transpose, repeats, an instrument swap and a
   volume offset. `:ReadPosition`
   - `LOOP_POSITIONS` loops the voice's positions. `STOP_VOICE` stops the voice.
     `:NextPosition`
   - Each voice ends on its own. The song ends when all have looped or stopped.
   - **Trap:** a new position drops the pending table switches.
4. Ticks left get the event's length, or without one, the last length.
   `:NoteEvent`
   - A volume argument sets the event's volume offset.
   - An instrument argument loads the instrument. `:LoadInstrument`
   - **Trap:** the swap acts only when an event loads an instrument. An
     instrument loaded before the position keeps playing.
   - A portamento argument fits the rate: interval / (length − delay) ratio
     steps per tick. `:GlideToFit`
   - **Trap:** a delay equal to the length divides by zero.
   - `REST` sets the rest flag. `:RestEvent`
5. All four walkers restart at the instrument's tables. `:NoteEvent`
6. Opcodes from `FIRST_MODIFIER` up follow, and take no time. `:Modifier`
   - `LEGATO_ON` and `LEGATO_OFF` set the legato flag. `:LegatoOn`
   - `GLIDE_UP` and `GLIDE_DOWN` start a portamento after a delay, at a fixed
     rate.
   - `SWITCH_VOLUME` and `SWITCH_FINE` set a table switch after a delay.
     `:SwitchVolTable` `:SwitchFineTable`

With the rest flag set, a tick turns DMA off and counts down. It runs nothing
else, not even the switch delays. `:VoiceTick`

Each tick otherwise, in this order: `:VoiceTick`

1. A pending switch counts down. At 0, the walker jumps to the new table.
   `:SwitchTables`
   - **Trap:** the walker keeps the instrument's table as its start. At the new
     table's `TABLE_END`, it returns to the instrument's table.
   - **Trap:** the next event restarts the walker at the instrument's table. A
     switch lasts only to the event's end.
2. The level is the volume walker's value, or 64 without a table. It loses the
   event's and the position's volume offsets, down to 0. `:VolumeWalker`
   - **Trap:** the subtraction wraps at a byte. Offsets more than 128 above the
     value give a loud level, not 0.
3. The period comes from the event's note, plus the position's transpose and the
   note table's value. A fixed instrument skips the transpose. `:NoteWalker`
   - **Trap:** the note wraps at a byte. Notes past 143 read the ratio table
     after the periods.
4. The fine walker's value, a signed word of ratio steps, scales the period.
   `:FineWalker`
5. After its delay, the portamento multiplies its ratio by its rate. The ratio
   scales the period. `:Glide`
   - It has no target. It runs to the event's end.

Then it writes the wave and the registers:

1. The pulse walker rebuilds the wave. Without a pulse table, the instrument
   plays its sample.
2. The instrument's shift scales the period last. `:ShiftPitch`
3. `AUDxPER` gets the period. `AUDxVOL` gets the level. `:WriteChannel`
4. On the event's first tick, `AUDxLC` and `AUDxLEN` get the sample or the wave.
   On the second, they get the loop, a
   [loop by reload](../docs/paula-techniques.md#loop-by-reload).
5. DMA goes on. On the last tick, it goes off instead, unless legato is on. This
   gap restarts the next note, with no busy-wait.
   - **Trap:** an event of 1 or 2 ticks has no last-tick gap. It acts as legato.
   - **Trap:** with legato, the next sample waits for the old loop's end.

A voice falls silent at each event's last tick, `REST`,
[volume 0](../docs/paula-techniques.md#silence-by-volume) or `STOP_VOICE`.

- **Trap:** `STOP_VOICE` stops the ticks, not DMA. After a legato event, the
  wave loops on. `:NextPosition`

### Walker

A walker holds its table's start, a position, its run's values left and repeats
left. `:Runs`

- It steps once per tick, if it has a table.
- A run is a count, a repeat number, then the values. A count of 0 gives 256
  values.
- After the run, it plays the run again while repeats last. At `TABLE_END`, it
  restarts from its table's start.
- The volume and note tables hold bytes. The fine and pulse tables hold words.

### Wave buffer

Each voice owns a 16-byte wave, changed by
[live wave edits](../docs/paula-techniques.md#live-wave-edits). Each tick:
`:PulseWalker`

1. The pulse walker gives a word. Its high byte W picks pulse wave W of 16. That
   wave has W low bytes, then high bytes.
2. The 16 bytes are copied into the voice's wave.
3. The word's low byte A is subtracted from byte W, the first high byte. This
   soft edge lies between the widths W and W + 1.
   - **Trap:** the code does not limit W. A W above 15 reads past the pulse
     waves and writes past the voice's wave.

## Open questions

- Did any composers besides the authors use this format?
