# MIDI-Loriciel events and limits

[MIDI-Loriciel](../players/MIDI-Loriciel.md) reads an SMF score and a separate
`BNKS` sample bank. The loader pairs `MIDI.name` with `SMPL.name`, or `.MID`
with `.BSP`. `data/annot/MIDI-Loriciel.yaml:InitPlayer` `:CopyName`

## Source scope

The card uses Wanted Team's `V2.0` Amplifier source, dated 17 March 2008. Its
header identifies the replay as Entity's intro player, credited to Loriciel
in 1993. `:Creator` `:Init_1`

`V1.0` and `V2.0` share the track parser, timing and voice-allocation rules.
`V2.0` sends outputs through EaglePlayer calls instead of writing Paula
registers.
`ext/uade/amigasrc/players/wanted_team/MIDI-Loriciel/MIDI - Loriciel_v1.asm:lbC000B30`
`data/annot/MIDI-Loriciel.yaml:AllocateVoice` `:PokeAdr` `:PokeDMA`

## Channel events

`n` is a MIDI channel, 0–15. Every event needs an explicit status byte.
`data/annot/MIDI-Loriciel.yaml:ReadEvent` `:ChannelEvent`

| Status            | Event            | Action                                                                   | Label                               |
| ----------------- | ---------------- | ------------------------------------------------------------------------ | ----------------------------------- |
| `$8n`             | note-off         | Match the channel's latest voice and note; stop DMA                      | `:NoteOffEvent`, `:StopNote`        |
| `$9n`             | note-on          | Allocate a voice; select sample, period and velocity volume              | `:NoteOnEvent`, `:StartNote`        |
| `$9n`, velocity 0 | note-off         | Same handler as `$8n`                                                    | `:NoteOnEvent`                      |
| `$Cn`             | program change   | Select bank instrument for future notes on this MIDI channel             | `:ProgramEvent`, `:SelectProgram`   |
| `$An`             | note pressure    | Skip both data bytes                                                     | `:ChannelHandlers`, `:SkipTwoBytes` |
| `$Bn`             | CC               | Skip number and value; no CC is implemented                              | `:ChannelHandlers`, `:SkipTwoBytes` |
| `$Dn`             | channel pressure | Skip two bytes, although the event has only one; parsing loses alignment | `:SkipTwoBytes`                     |
| `$En`             | pitch bend       | Skip both data bytes                                                     | `:ChannelHandlers`, `:SkipTwoBytes` |

There is no dedicated arpeggio command or pitch walker. A score can write
successive note-ons and note-offs instead. Without intervening note-offs, those
note-ons can take separate voices. `:ChannelHandlers` `:AllocateVoice`

## System and meta events

| Event                    | Action                                                              | Label                              |
| ------------------------ | ------------------------------------------------------------------- | ---------------------------------- |
| `$F0` sysex              | Read a variable-length size and skip the payload                    | `:SkipSysex`                       |
| `$F7` sysex continuation | No handler; the two-byte fallback cannot skip this reliably         | `:SystemHandlers`, `:SkipTwoBytes` |
| `$FF $20` channel prefix | Store a channel in this track; later channel events overwrite it    | `:ChannelPrefix`, `:ChannelEvent`  |
| `$FF $2F` end of track   | Clear the active flag and reduce the active-track count             | `:EndTrack`                        |
| `$FF $51` tempo          | Read three bytes as microseconds per quarter note; change the timer | `:TempoEvent`, `:SetTempo`         |
| Other `$FF` meta events  | Read a variable-length size and skip the payload                    | `:ReadMeta`, `:SkipMeta`           |

End, prefix and tempo handlers assume the usual fixed payload lengths. They skip
the length byte without validating it. `:EndTrack` `:ChannelPrefix`
`:TempoEvent`

## Clock and reuse

| Property        | Behavior                                                                                              | Label                         |
| --------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------- |
| Header division | Positive division supplies PPQ; a negative division substitutes 192 PPQ, not timecode timing          | `:InitTracks`                 |
| Initial tempo   | 500000 microseconds per quarter note                                                                  | `:StartSound`                 |
| Tick            | Subtract four pulses from each active track's wait                                                    | `:TrackTick`                  |
| Zero delta      | Read another event during the same track visit                                                        | `:ReadDelta`                  |
| Positive delta  | Save the wait and leave the track; preserve any negative remainder from the previous wait             | `:SaveWait`                   |
| Track order     | Visit tracks in file order, not by merging their events into one sorted stream                        | `:TrackTick`                  |
| Song end        | On the next tick after all tracks end, signal the host and restart tracks, voices, programs and tempo | `:RestartSong`, `:StartSound` |
| Storage         | Space for 16 track records; no check prevents a larger count                                          | `:TrackStates`, `:InitTrack`  |

Positive deltas shorter than four pulses still defer their event until a later
tick. Negative timing residue does not trigger immediate catch-up. `:SaveWait`

The wrappers disagree on format validation. `V1.0` accepts formats 0 and 1;
`V2.0` rejects 0 but fails to reject higher formats.
`ext/uade/amigasrc/players/wanted_team/MIDI-Loriciel/MIDI - Loriciel_v1.asm:Check2`
`data/annot/MIDI-Loriciel.yaml:Check5`

## Instrument and voice lifetime

| Component          | Data or rule                                                                                                   | Label                               |
| ------------------ | -------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| Bank               | Program pointers, then sample zones; loading relocates pointers in place and clears the signature into silence | `:InitSamples`                      |
| Zone               | First upper bound at least as high as the note wins; its tuning offset selects the period-table index          | `:FindSampleZone`, `:SelectSample`  |
| Bounds             | Program numbers and notes beyond the final zone have no safe fallback                                          | `:SelectProgram`, `:FindSampleZone` |
| Volume             | Index a 64-byte curve with velocity divided by two; double its result to 0–62                                  | `:SetVelocity`, `:VelocityTable`    |
| Instrument control | No envelope, vibrato, sample program or independent table walker                                               | `:StartNote`, `:SilentTail`         |
| Silent tail        | At tick end, replace each busy voice's reload sample with four zero bytes                                      | `:SilentTail`, `:InitSamples`       |
| Freeing            | Only a matching note-off frees the voice; sample completion does not                                           | `:MatchNoteOff`                     |

Each MIDI channel stores one pointer to its latest allocated voice. A second
note replaces that pointer without freeing the earlier voice.

With different pitches, the earlier note-off finds the wrong note and does
nothing. With repeated pitches, it stops the latest note instead. Even after its
sample falls silent, the earlier voice remains busy until stolen or reset.
`:AllocateVoice` `:MatchNoteOff` `:SilentTail`

This is not strict mono mode: overlapping notes can occupy several voices. It is
not full poly mode either: note-off cannot find every held note.
`:AllocateVoice` `:MatchNoteOff`
