# SoundPlayer commands

## How a command runs

- Each row holds three bytes per voice: note, instrument, command.
  `data/annot/SoundPlayer.yaml:ReadRow`
- A 256-byte table maps the command byte to a handler. `:RunCommand`
  `:CommandTable`
- Commands run once, on the row tick. `:RowCommands`
- "N" below is the command byte minus the first byte of its range.

## Commands

| Bytes     | Operation                                             | Label             |
| --------- | ----------------------------------------------------- | ----------------- |
| `01`      | Audio filter off                                      | `:CmdFilterOff`   |
| `02`      | Audio filter on                                       | `:CmdFilterOn`    |
| `03`–`42` | Set volume to N                                       | `:CmdVolume`      |
| `43`      | Stop this channel                                     | `:CmdStop`        |
| `57`–`88` | Wait N rows before reading the next row               | `:CmdWait`        |
| `A7`–`B0` | Slide volume up by 1 every N ticks, up to 63          | `:CmdSlideUp`     |
| `B1`–`BA` | Slide volume down by 1 every N ticks, down to 0       | `:CmdSlideDown`   |
| `BB`–`CE` | Set game flag N                                       | `:CmdSetFlag`     |
| `CF`      | Hold: keep looping the whole sample                   | `:CmdHold`        |
| `D0`      | Release: play the repeat part after the first pass    | `:CmdRelease`     |
| `D1`      | Clear all game flags                                  | `:CmdClearFlags`  |
| `D2`–`DB` | Mark a repeat start, N repeats                        | `:CmdRepeatStart` |
| `DC`      | Repeat end: jump back to the mark until N runs out    | `:CmdRepeatEnd`   |
| `DD`      | Step back one row, so this row plays again            | `:CmdStepBack`    |
| `DE`      | Restart this voice from the song start                | `:CmdRestart`     |
| `DF`–`E1` | Channel 0, 1 or 2 modulates the next channel's volume | `:CmdVolModOn`    |
| `E2`–`E4` | Channel 0, 1 or 2 modulates the next channel's period | `:CmdPerModOn`    |
| `E5`–`F8` | Clear game flag N                                     | `:CmdClearFlag`   |
| `F9`–`FB` | End volume modulation from channel 0, 1 or 2          | `:CmdVolModOff`   |
| `FC`–`FD` | End period modulation from channel 0 or 1             | `:CmdPerModOff`   |

Other bytes do nothing.

## Open questions

- A handler ends period modulation from channel 2. No command byte reaches it.
  `:CmdPerModOff2`
