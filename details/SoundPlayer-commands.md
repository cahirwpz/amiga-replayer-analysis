# SoundPlayer commands

Source:
`ext/uade/amigasrc/players/wanted_team/SoundPlayer/src/SoundPlayer_v1.asm`. All
line numbers refer to this file.

## How a command runs

- Each row holds three bytes per voice: note, instrument, command (line 1045).
- A 256-byte table maps the command byte to a handler (lines 1226, 1624).
- Commands run once, on the row tick (line 1206).
- "N" below is the command byte minus the first byte of its range.

## Commands

| Bytes     | Operation                                             | Line |
| --------- | ----------------------------------------------------- | ---- |
| `01`      | Audio filter off                                      | 1288 |
| `02`      | Audio filter on                                       | 1291 |
| `03`–`42` | Set volume to N                                       | 1294 |
| `43`      | Stop this channel                                     | 1401 |
| `57`–`88` | Wait N rows before reading the next row               | 1419 |
| `A7`–`B0` | Slide volume up by 1 every N ticks, up to 63          | 1304 |
| `B1`–`BA` | Slide volume down by 1 every N ticks, down to 0       | 1310 |
| `BB`–`CE` | Set game flag N                                       | 1316 |
| `CF`      | Hold: keep looping the whole sample                   | 1322 |
| `D0`      | Release: play the repeat part after the first pass    | 1325 |
| `D1`      | Clear all game flags                                  | 1328 |
| `D2`–`DB` | Mark a repeat start, N repeats                        | 1334 |
| `DC`      | Repeat end: jump back to the mark until N runs out    | 1341 |
| `DD`      | Step back one row, so this row plays again            | 1350 |
| `DE`      | Restart this voice from the song start                | 1353 |
| `DF`–`E1` | Channel 0, 1 or 2 modulates the next channel's volume | 1359 |
| `E2`–`E4` | Channel 0, 1 or 2 modulates the next channel's period | 1368 |
| `E5`–`F8` | Clear game flag N                                     | 1377 |
| `F9`–`FB` | End volume modulation from channel 0, 1 or 2          | 1383 |
| `FC`–`FD` | End period modulation from channel 0 or 1             | 1392 |

Other bytes do nothing.

## Open questions

- A handler ends period modulation from channel 2 (line 1398). No command byte
  reaches it.
