# Tim Follin commands

## How a command runs

- Each voice reads its own byte track. `data/annot/TimFollin.yaml:ReadTrack`
- A byte from `01` to `7F` is a note, then a length byte. `:PlayNote`
- Byte `00` and bytes from `80` up are commands. A table picks the handler.
  `:CommandTable`
- Commands run until the next note, all in one tick.
- Arguments follow the command byte. Addresses are 4 bytes, word-aligned.

## Commands

| Byte | Arguments                                  | Operation                                              | Label                 |
| ---- | ------------------------------------------ | ------------------------------------------------------ | --------------------- |
| `80` | —                                          | Nothing (also byte `00`)                               | `:CmdNop`             |
| `81` | instrument                                 | Select instrument                                      | `:CmdInstrument`      |
| `82` | address                                    | Call; four return addresses per voice                  | `:CmdCall`            |
| `83` | —                                          | Return                                                 | `:CmdReturn`          |
| `84` | count                                      | Mark a loop start                                      | `:CmdLoopStart`       |
| `85` | —                                          | Jump back to the mark until the count runs out         | `:CmdLoop`            |
| `86` | start, sustain; attack, decay speed; phase | Set the volume envelope; nibbles, then a byte          | `:CmdEnvelope`        |
| `87` | speed                                      | Portamento: next notes become targets; 0 turns it off  | `:CmdPortamento`      |
| `88` | interval, upper ticks, lower ticks         | Trill between the note and the note plus the interval  | `:CmdTrill`           |
| `89` | delay, step, half-cycle ticks, direction   | Vibrato in period units; half-cycle 0 gives a sweep    | `:CmdVibrato`         |
| `8A` | semitones                                  | Transpose                                              | `:CmdTranspose`       |
| `8B` | ticks                                      | Fixed note length; notes then carry no length byte     | `:CmdFixedLength`     |
| `8C` | on/off                                     | Notes restart the envelope                             | `:CmdEnvelopeRestart` |
| `8D` | flags                                      | Bits 0–5: second sample; bit 6: chain; bit 7: gate off | `:CmdFlags`           |
| `8E` | ticks                                      | Pulse sweep speed; resets the sweep                    | `:CmdPulseSpeed`      |
| `8F` | —                                          | Stop the voice: channel off, volume 0                  | `:CmdEnd`             |
| `90` | step                                       | Envelope step size                                     | `:CmdEnvelopeStep`    |
| `91` | —                                          | The next note ignores the transpose                    | `:CmdNoTranspose`     |
| `92` | address                                    | Jump                                                   | `:CmdJump`            |
