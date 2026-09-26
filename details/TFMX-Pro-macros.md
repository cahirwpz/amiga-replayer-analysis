# TFMX Pro macros and patterns

## How a macro runs

- A note starts macro M on voice V at step 0.
  `data/annot/TFMX-Pro.yaml:NoteToVoice`
- A statement is 4 bytes: opcode, then 3 argument bytes. `:MacroStep`
- Each tick, the macro runs statements until a wait, a stop or a pitch change.
- After the macro, the voice's generators run: start sweep, IMS, vibrato,
  portamento, envelope, riff. `:SweepStart`
- The voice keeps one return address, so calls do not nest. `:MacroCall`

## Macro opcodes

"S" is a step in a macro. "M" is a macro number.

| Opcode      | Operation                                                             | Label             |
| ----------- | --------------------------------------------------------------------- | ----------------- |
| `$00`       | Stop the sample; clear envelope, vibrato, portamento, riff, IMS       | `:mdmaoff`        |
| `$13`       | Stop the sample only                                                  | `:mdmaoff2`       |
| `$01`       | Start the sample. The argument can hold the generators back           | `:mdmaon`         |
| `$02` `$03` | Set sample start, length                                              | `:msetbegin`      |
| `$11` `$12` | Add to start, length. `$11` can repeat the add each tick, swinging    | `:maddbegin`      |
| `$18`       | Move the start forward, shorten the length by the same amount         | `:msampleloop`    |
| `$19`       | Play the empty one-word sample                                        | `:msetone`        |
| `$04`       | Wait N ticks, or wait for a flagged riff note                         | `:MacroWait`      |
| `$1a`       | Wait for N passes of the sample, counted by audio interrupt           | `:WaitLoops`      |
| `$14`       | Wait for note-off, at most N ticks                                    | `:WaitNoteOff`    |
| `$05`       | Loop N times to step S                                                | `:mloop`          |
| `$10`       | Like `$05`, but only while the note is held                           | `:LoopWhileKey`   |
| `$06` `$15` | Go to, or call, macro M at step S                                     | `:MacroGoto`      |
| `$16`       | Return from a call                                                    | `:mreturn`        |
| `$30`       | Go on the first time; jump to S when the same macro starts again      | `:SkipFirstPass`  |
| `$07` `$2a` | Stop the macro; do nothing                                            | `:mstop`          |
| `$1c` `$1d` | Jump to S if the note, or the volume, is above the argument           | `:SplitByNote`    |
| `$08` `$09` | Pitch: note plus offset; fixed note. Both take a detune               | `:maddnote`       |
| `$1f`       | Pitch: the previous note plus offset                                  | `:mlastnote`      |
| `$17`       | Set the period directly                                               | `:msetperiod`     |
| `$0b` `$0c` | Portamento; vibrato                                                   | `:mporta`         |
| `$0d` `$0e` | Add to the volume, or set it. The add starts from 3 × note volume     | `:maddvolume`     |
| `$0f`       | Envelope: slide the volume to a target, by N every M ticks            | `:menvelope`      |
| `$0a`       | Clear envelope, vibrato, portamento, riff, start sweep, IMS           | `:mclear`         |
| `$21` `$31` | Start macro M on voice V with this note; note-off on voice V          | `:PlayOtherVoice` |
| `$1b` `$1e` | Start a riff: macro, speed, flags; set the random step mask           | `:StartRiff`      |
| `$22`–`$29` | IMS setup, see below                                                  | `:ImsSource`      |
| `$20`       | Set one of four flags that the game reads                             | `:msendflag`      |
| `$2e`       | Write any custom chip register                                        | `:WriteChipReg`   |
| `$2c` `$2d` | Write a byte at an absolute address; skip one statement if it matches | `:CheckByte`      |
| `$2b`       | If the byte does not match, write a random byte to low memory         | `:CheckByteTrap`  |
| `$2f`       | Copy the next statement into macro M at step S                        | `:CopyToMacro`    |
| `$32` `$33` | Add to, or mask, a word of this macro                                 | `:AddToMacro`     |

The author's build options call the byte checks "cracker nightmares" (guess:
these are `oncheck`). `:CheckByte`

## IMS

The author calls it "interference modulation synthesis". It rebuilds a wave of
up to 256 bytes every tick. `:ImsRender`

| Opcode | Sets                                                                 |
| ------ | -------------------------------------------------------------------- |
| `$22`  | Source sample start. Paula plays the voice's own buffer instead      |
| `$23`  | Buffer length; source length mask, a power of two minus one          |
| `$24`  | Start step: how fast the source is read                              |
| `$25`  | Start step sweep: add per tick, reverse after N ticks                |
| `$26`  | Step change, added to the step after every byte                      |
| `$27`  | Step change sweep, like `$25`                                        |
| `$28`  | Filter: each byte moves towards the source by at most `delta`; sweep |
| `$29`  | IMS off. Or reset all IMS settings and set the negated copy flag     |

- A positive step change reads the source faster and faster within one wave.
- The filter smooths steep edges (inference: a low-pass filter). `:ImsFilter`
- The start sweep `$11` also moves the source window. `:SweepStart`
- The negated copy goes into the next voice's buffer. `:ImsRender`

## Pattern opcodes

A pattern entry is 4 bytes: note, macro, volume and voice, detune. `:TrackNote`

| Note        | Meaning                                            | Label              |
| ----------- | -------------------------------------------------- | ------------------ |
| `$00`–`$7f` | Note                                               | `:TrackNote`       |
| `$80`–`$bf` | Note, then wait; the detune byte is the wait       | `:TrackNote`       |
| `$c0`–`$ef` | Portamento to this note                            | `:PortaNote`       |
| `$f0`       | End: the whole song moves to the next position     | `:PatternEnd`      |
| `$f1` `$f3` | Loop N times to step S; wait N rows                | `:PatternOpcode`   |
| `$f2` `$f8` | Go to, or call, pattern P at step S; `$f9` returns | `:PatternCall`     |
| `$f4` `$fe` | Stop this track                                    | `:PatternOpcode`   |
| `$f5`–`$f7` | Note-off, vibrato, envelope for a voice            | `:NoteToVoice`     |
| `$fa`       | Fade the master volume                             | `:PatternOpcode`   |
| `$fb`       | Start pattern P on another track                   | `:StartOtherTrack` |
| `$fc`       | Lock a voice for N ticks: it ignores other notes   | `:NoteToVoice`     |
| `$fd`       | Set a flag that the game reads                     | `:PatternOpcode`   |

Special positions stop the song, loop N times, set speed and tempo, or fade.
`:PositionSpecials`
