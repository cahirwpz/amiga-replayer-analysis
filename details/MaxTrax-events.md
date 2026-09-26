# MaxTrax score events and CCs

## Score events

An event is 6 bytes: command, data, start time, stop time.
`data/annot/MaxTrax.yaml:MusicServer`

- The start time is the delta from the previous event, in pulses.
- The data byte holds the MIDI channel in its low 4 bits.
- Other commands use the stop time field for their arguments.

| Command     | Meaning      | Data and stop time                                                    | Label                                      |
| ----------- | ------------ | --------------------------------------------------------------------- | ------------------------------------------ |
| `$00`–`$7F` | note-on      | Note number; data high 4 bits: velocity in steps of 8; stop: length   | `:NoteOn`                                  |
| `$80`       | tempo        | Data: beats per minute. Stop: slide length; shorter than a tick: jump | `:TempoSlide`                              |
| `$A0`       | special      | Stop high byte: kind, low byte: value; kinds below                    | `:SyncEvent`                               |
| `$B0`       | CC           | Stop: CC number and value                                             | `data/annot/MaxTrax-shared.yaml:ControlCh` |
| `$C0`       | program      | Stop low byte: patch, 0–63                                            | `data/annot/MaxTrax.yaml:ProgramCh`        |
| `$E0`       | pitch bend   | Stop: 14-bit value                                                    | `data/annot/MaxTrax-shared.yaml:PitchBend` |
| `$FF`       | end          | Loop to the start if looping is on, else stop                         | `data/annot/MaxTrax.yaml:ScoreEnd`         |
| `$F0` `$F8` | sysex, clock | Declared in `driver.i`; the score reader skips them                   | `:MusicServer`                             |

| Special | Meaning                                                      | Label           |
| ------- | ------------------------------------------------------------ | --------------- |
| 0       | Mark: `AdvanceSong` skips to the next mark                   | `:advance_song` |
| 1       | Sync: signal the game's task with the value                  | `:SyncEvent`    |
| 2       | Begin repeat: play the section value + 1 times; up to 4 nest | `:BeginRepeat`  |
| 3       | End repeat                                                   | `:EndRepeat`    |

- Velocity 0 does not end a note; only the length does.
- Velocity counts only if the game turns it on; else every note has 128.
  `:NoteOn`

## CCs

All in `data/annot/MaxTrax-shared.yaml:ControlCh`. This build has no modulation
and no microtonal tuning; their CCs do nothing.

| CC       | Effect                                                                 | Label                                         |
| -------- | ---------------------------------------------------------------------- | --------------------------------------------- |
| 5, 37    | Portamento time in ms, high and low 7 bits. Default 500                | `:ControlCh`                                  |
| 6        | Data entry: pitch bend range for RPN 0, up to 24 semitones. Default 24 | `:ControlCh`                                  |
| 7        | Channel volume. Only new notes use it                                  | `:ControlCh`                                  |
| 10       | Pan: picks a side for new notes, not a level                           | `:PanSide`                                    |
| 64       | Damper pedal: note-offs wait until it is released                      | `:DamperPedal`                                |
| 65       | Portamento on or off. Only mono mode glides                            | `:PortaOffBug`                                |
| 81       | Audio filter: below 64 off, above on, 64 the song's start setting      | `:ControlCh`                                  |
| 100, 101 | RPN select; only RPN 0 has an effect                                   | `:RpnSelect`                                  |
| 120      | All sound off: cut at once                                             | `data/annot/MaxTrax.yaml:AllSoundsOff`        |
| 121      | Reset all controllers                                                  | `data/annot/MaxTrax-shared.yaml:ResetChannel` |
| 123      | All notes off: release, or hold while the damper pedal is down         | `data/annot/MaxTrax.yaml:AllNotesOff`         |
| 126, 127 | Mono or poly mode; both send all notes off first                       | `:AllNotesOff`                                |

- CC 10 below 64 sets the right side, though the source comment says left.
  Channel reset gives even channels the left side.
- CC 65 off writes `$FF` through the wrong register. From the score, it lands 17
  bytes into the score, past the current event.
