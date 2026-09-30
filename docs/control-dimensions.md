# Control dimensions

Questions a card should answer when a player's answer is distinct. The
`card-coverage` agent reads the card, spec and listing against them.

One voice changes four things over time: pitch, volume, timbre and gate. The
sequencer decides timing and which voice plays a note.

| Dimension | Outputs     | Lifecycle events                    |
| --------- | ----------- | ----------------------------------- |
| pitch     | `Period`    | note-on, legato                     |
| volume    | `Volume`    | note-on, release                    |
| timbre    | `Sample`    | note-on, legato, release            |
| timbre    | `Wave data` | note-on, legato                     |
| gate      | `DMA`       | note-on, legato, release, hard stop |
| gate      | `Volume`    | release, program end                |

A plain answer earns no card line. "Distinct when" says what does.

## Gate

| Question                               | Distinct when                                       | Seen in                                                                                |
| -------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------------- |
| What ends a note?                      | Not the next note: a length, a note-off, a program. | [MIDI-Loriciel](../players/MIDI-Loriciel.md)                                           |
| What starts the release?               | A timer, a gate time or a missing hold flag.        | [Fred](../players/Fred.md), [SonicArranger](../players/SonicArranger.md)               |
| Does the release play a sample region? | A release plays sample data, not only lower volume. | [SoundFactory](../players/SoundFactory.md)                                             |
| What does a legato note keep?          | It keeps some state and restarts other state.       | [SoundMon 2.2](../players/SoundMon2.2.md), [Paul Robotham](../players/PaulRobotham.md) |
| Does a note restart DMA?               | A note keeps DMA on and the wave plays on.          | [AHX](../players/AbyssHighestExperience.md)                                            |
| Is there a gap before a note?          | The gap's length or rule is unusual.                | [Fred](../players/Fred.md)                                                             |

## Pitch

| Question                                     | Distinct when                                              | Seen in                                                                            |
| -------------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| In which unit does pitch move?               | Not in periods: semitones, cents, fractions of a semitone. | [Musicline Editor](../players/MusiclineEditor.md)                                  |
| Is a vibrato the same interval at any pitch? | Depth in periods, so low notes get a smaller interval.     | [Fred](../players/Fred.md), [Future Composer 1.4](../players/FutureComposer1.4.md) |
| How fine are notes?                          | Steps finer than a semitone, e.g. quarter tones.           | [MusicMaker 8V](../players/MusicMaker-8V.md)                                       |
| Is an ornament one command?                  | A trill or grace note is a fixed command, not a program.   | [Tim Follin](../players/TimFollin.md)                                              |
| How is an arpeggio written?                  | A program loop, a list opcode, or one command.             | [MED](../players/MED.md), [TFMX Pro](../players/TFMX-Pro.md)                       |
| How do glide and arpeggio combine?           | One adds on top of the other, or one replaces the other.   | [Fred](../players/Fred.md)                                                         |

## Volume

| Question                             | Distinct when                                   | Seen in                                                        |
| ------------------------------------ | ----------------------------------------------- | -------------------------------------------------------------- |
| What shapes the envelope?            | A table, a program, a wave read as a curve.     | [Mugician II](../players/MugicianII.md)                        |
| In which unit does the envelope run? | Milliseconds or a tempo-scaled time, not ticks. | [MaxTrax](../players/MaxTrax.md)                               |
| Who owns the envelope state?         | Voices share it through the instrument.         | —                                                              |
| Does a fade scale with voice count?  | A song fade steps once per playing voice.       | [Fred](../players/Fred.md), [TFMX Pro](../players/TFMX-Pro.md) |

## Timbre

| Question                                     | Distinct when                                             | Seen in                                                                                                 |
| -------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Does a note use more than one sample region? | Attack and sustain are separate regions, chosen per note. | [MaxTrax](../players/MaxTrax.md), [MusicMaker 8V](../players/MusicMaker-8V.md)                          |
| Can the loop move while a note plays?        | A program or command moves the loop start or length.      | [Jason Page](../players/JasonPage.md)                                                                   |
| When does a new region or wave start?        | At the loop end, at once, or a tick later.                | [MED](../players/MED.md)                                                                                |
| Does code rewrite wave bytes?                | Wave data changes in place or in a buffer per voice.      | [Fred](../players/Fred.md), [Sonic Arranger](../players/SonicArranger.md)                               |
| Are waves built ahead of time?               | The player precomputes a bank, e.g. filtered copies.      | [AHX](../players/AbyssHighestExperience.md), [Sonix Music Driver](../players/SonixMusicDriver.md)       |
| Does the wave depend on pitch?               | High notes play a shorter or different wave.              | [Sonix Music Driver](../players/SonixMusicDriver.md), [Musicline Editor](../players/MusiclineEditor.md) |

## Sequencer

| Question                            | Distinct when                                             | Seen in                                                                                    |
| ----------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| What is the time grain?             | Pulses, milliseconds or a timer rate, not ticks and rows. | [MaxTrax](../players/MaxTrax.md), [MIDI-Loriciel](../players/MIDI-Loriciel.md)             |
| Can rows have unequal lengths?      | Swing or a groove table alternates speeds.                | [Mugician II](../players/MugicianII.md), [Musicline Editor](../players/MusiclineEditor.md) |
| How is tempo made?                  | A fractional tick drop, a timer, a scale on all times.    | [David Whittaker](../players/DavidWhittaker.md)                                            |
| Does each voice have its own speed? | Speed is per voice, or one voice's command sets all.      | [Fred](../players/Fred.md)                                                                 |
| Which voice plays a note?           | Voice allocation or voice stealing, not a fixed track.    | [MaxTrax](../players/MaxTrax.md), [MIDI-Loriciel](../players/MIDI-Loriciel.md)             |
