# Glossary

One line per term. Every acronym used in this repo must appear here.

| Term        | Meaning                                                                            |
| ----------- | ---------------------------------------------------------------------------------- |
| **ADKCON**  | Paula control register. Selects attach modes, among other things.                  |
| **AHX**     | Abyss Highest eXperience: Amiga chiptune tracker, 1990s.                           |
| **AUDxLC**  | Channel x sample start address. Reloaded into the pointer at each wrap.            |
| **AUDxLEN** | Channel x sample length, in words.                                                 |
| **AUDxPER** | Channel x period: clock divider that sets pitch.                                   |
| **AUDxVOL** | Channel x volume, 0 to 64.                                                         |
| **C1**      | Advanced level of the CEFR language scale. Our target reader.                      |
| **C64**     | Commodore 64: 8-bit home computer with the SID sound chip.                         |
| **CCK**     | Colour clock, 3.546895 MHz on PAL. Paula's time unit.                              |
| **CIA**     | Timer chip. Replayers use it for tempo independent of the display.                 |
| **CPU**     | The Motorola 68000 family processor.                                               |
| **DMA**     | Direct memory access. Paula fetches samples without the CPU.                       |
| **FK**      | Flesch-Kincaid grade: a readability score. Lower is easier.                        |
| **HRM**     | Commodore's Amiga Hardware Reference Manual.                                       |
| **IRA**     | Portable 68000 reassembler. Turns a player binary into assembler source.           |
| **MED**     | Music editor by Teijo Kinnunen, later OctaMED. Tracker with synth sounds.          |
| **MIDI**    | Standard protocol for sending notes to synthesizers.                               |
| **PAL**     | European TV standard. Sets the Amiga clock and 50 Hz frame rate.                   |
| **PCM**     | Sampled sound: a stream of stored amplitude values.                                |
| **PWM**     | Pulse-width modulation. Paula uses it to apply volume.                             |
| **SMUS**    | Simple Music Score: note score format from Electronic Arts.                        |
| **ST**      | Atari ST: home computer with a YM2149 sound chip.                                  |
| **TFMX**    | The Final Musicsystem eXtended, by Chris Hülsbeck. Instruments are macro programs. |
| **UADE**    | Unix Amiga Delitracker Emulator. Plays Amiga music on other systems.               |
| **VBL**     | Vertical blank interrupt, once per frame. The usual replayer tick.                 |

## Tracker terms

| Term           | Meaning                                                |
| -------------- | ------------------------------------------------------ |
| **tick**       | One run of the replayer, usually once per frame.       |
| **row**        | One line of a pattern. It lasts `speed` ticks.         |
| **speed**      | Ticks per row.                                         |
| **track**      | One column of note data, often one per voice.          |
| **pattern**    | A block of rows, played by one or more tracks.         |
| **transpose**  | Offset added to every note of a track or instrument.   |
| **arpeggio**   | Fast cycle of note offsets, making a chord-like sound. |
| **portamento** | Slide of the pitch, often towards a target note.       |
| **vibrato**    | Periodic pitch change.                                 |

## Card terms

| Term            | Meaning                                                              |
| --------------- | -------------------------------------------------------------------- |
| **stream**      | A position in some data that the player steps through.               |
| **scope**       | Where a stream's position lives: song, track, voice or instrument.   |
| **generator**   | Stateful process that is not a stream, e.g. a vibrato state machine. |
| **interaction** | One stream acting on another, e.g. a jump or a trigger.              |
| **tables**      | Control level: data walked in order, no opcodes.                     |
| **commands**    | Control level: data with opcodes, but no conditions.                 |
| **program**     | Control level: opcodes with conditions or calls.                     |
| **code**        | Evidence: original or disassembled replayer source.                  |
| **port**        | Evidence: a port of the original replayer.                           |
| **docs**        | Evidence: documentation only.                                        |
| **disasm**      | Evidence: our own IRA disassembly of a player binary.                |
| **module**      | Replay code ships inside the music file.                             |

## Control vocabulary

Words used in the Control column of player cards.

| Word     | Meaning                                   |
| -------- | ----------------------------------------- |
| **loop** | Go back to a loop point.                  |
| **jump** | Go to another position or another stream. |
| **call** | Jump, then return.                        |
| **wait** | Pause for N ticks.                        |
| **cond** | Branch on a condition.                    |
| **end**  | Stop the stream.                          |
| **mode** | Off, play once, or loop.                  |
| **none** | No flow control.                          |

## Rate vocabulary

| Word              | Meaning                    |
| ----------------- | -------------------------- |
| **tick**          | Steps every tick.          |
| **every N ticks** | N is set per instrument.   |
| **row**           | Steps every row.           |
| **pattern end**   | Steps when a pattern ends. |
