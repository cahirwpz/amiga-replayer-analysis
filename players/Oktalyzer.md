---
player: Oktalyzer
template: 3
ideas: [voice-mixing]
---

# Oktalyzer

Up to eight sample tracks play on four channels. A channel plays one track or a
mixed pair.

## Unique ideas

- The song marks each channel single or mixed. A mixed channel plays two tracks
  from a buffer that the CPU fills each tick. `:MixChannel` `:Play1`
  - Limits: both tracks of a mixed channel share one volume. `:SetVolume`
- Samples for mixed tracks hold 7 bits. Two of them add up within 8 bits, with
  no clipping and no volume tables. `:SampleEntry`
- Replay 2 plays a buffer at the higher note's period. It adds that track
  unchanged and resamples only the lower one. `:PickHigher` `:MixPair`
  - Limits: the lower track repeats bytes, with no interpolation.
    `:ResampleLower`
- Replay 2 sizes each buffer to one frame at the buffer's period, from a table.
  A channel that runs ahead gets one word more. `:MixPair` `:DriftFix`
  - Limits: the tick busy-waits while a channel runs late. `:QueueBuffers`
- Replay 1 writes one resampler per note, from 36 routines of straight code.
  Repeated source bytes become means. `:BuildResamplers` `:RunResampler`
  - Limits: the code needs a buffer of 43,036 bytes. `:Replay1Init`
  - Limits: all mixed channels play at period 227, 15.6 kHz.

## How it plays

The copper, the display's coprocessor, runs the tick by an interrupt once per
frame. There is no audio interrupt. `:Play1` `:Play2`

Replay 2's tick sets periods, runs the sequencer, mixes and queues the buffers.
Replay 1's tick runs the sequencer and mixes. `:Play2` `:Play1`

### Player

The player holds the position, row, tick counter, `speed` and a jump target. It
holds the current row, the channel volumes and last tick's volumes. `:Module`

Each tick, in this order: `:ReplayHandler`

1. The single channels play their tick. See Single channel. `:SetHardware`
2. Each `AUDxVOL` gets its channel volume. `:SetHardware`
3. The counter counts up. At `speed`, the next row is read. `:NewRow`
   - After the last position, position 0 plays at the song's first `speed`.
4. On a new row, the mixed tracks' notes start. `:GetMixedNotes`
   - **Trap:** single channels ran before the new row. Their notes start at the
     next tick. `:SetHardware`
5. Each mixed track runs its command. `:TrackEffects`

Commands on any track change the player:

- `JUMP` reads its argument as decimal. $12 jumps to position 12.
  `:PositionJump`
- `SPEED` takes the argument's low nibble, at the row's first tick. `:SetSpeed`
- `VOLUME` up to 64 sets the channel volume. Above, it slides the volume up or
  down, each tick or once per row. `:SetVolume` `:VolumeSlide`
  - **Trap:** both tracks of a mixed channel write the same volume.

### Single channel

A single channel's track holds its note, period and loop. `:Track`

Each tick, in this order: `:SetHardware`

1. Last tick's notes get DMA on. After two scanline changes, `AUDxLC` and
   `AUDxLEN` get the loop, as a
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). `:TurnDmaOn`
2. At the row's first tick, a note turns DMA off. `:StartNotes`
   - `AUDxLC` and `AUDxLEN` get the sample up to its loop's end.
   - `AUDxPER` gets the note's period. The volume gets the sample's volume.
   - A sample for mixed tracks only is ignored.
   - **Trap:** DMA stays off for one tick. The channel is silent for one tick
     before each note. `:TurnDmaOn`
3. The command runs. `:ChannelEffects`
   - `PITCH_UP` and `PITCH_DOWN` slide the period, between 113 and 856.
   - The note commands move the note in semitones, each tick or once per row.
   - `OLD_VOLUME` restores last tick's volume. A new note keeps the old volume.
     `:OldVolume`

- Three arpeggio commands cycle in different orders. `ARPEGGIO` starts below the
  note. `ARPEGGIO3` keeps the last note on the row's first tick.
- **Trap:** a single note sounds one tick after the mixed notes of its row.
  `:SetHardware`

A sample without a loop ends on a
[silent loop](../docs/paula-techniques.md#silent-loop). There is no note-off.
`:StartNotes`

### Mixed track

A mixed track holds a sample pointer, the bytes left, a note and a base note.
`:Track`

- A note sets the sample, its whole length and both notes. It ignores the
  sample's loop and volume. `:GetMixedNotes`
  - A sample for single tracks only is ignored.
- **Trap:** a sample for both kinds of track also holds 7 bits. On a single
  channel, it plays at half amplitude. `:SampleEntry`
- Commands set the note in semitones, from the base note. There is no portamento
  and no `OLD_VOLUME`. `:TrackEffects`
- Replay 2 clamps the note to 0–33, up to A-3, and stores it. `:ClampNote`
- A track ends when its bytes run out. It never loops.
  - Replay 1 stops a track when fewer bytes are left than its tick needs. The
    rest never plays. `:ResampleTrack`
  - In replay 2, the higher track plays what is left. A lower track that runs
    short is silent for that tick. `:AddHigher` `:ResampleLower`

### Mixed channel in replay 2

A mixed channel holds its buffer, the buffer's period and length, and one extra
word. Two buffers per channel alternate. `:ChannelBuffer`

1. `AUDxPER` gets the period of the buffer queued last tick. `:SetPeriods`
2. If the channel already took that buffer, the next one gets the extra word.
   `:DriftFix`
3. Two playing tracks are mixed. One track alone is copied at its own period.
   `:MixChannel` `:CopySingle`
   - With no track, the buffer is silent, as at the start. `:Replay2Init`
   - On equal notes, the first track plays unchanged. `:PickHigher`
   - **Trap:** adds of 4 bytes at once let a carry spill into the byte before.
     `:AddHigher`
4. The tick busy-waits until each mixed channel took last tick's buffer.
   `AUDxLC` and `AUDxLEN` then get the new one. `:QueueBuffers`
   - The channel plays it after its next reload.

### Mixed channel in replay 1

Every channel loops a 626-byte buffer at period 227. A single channel's note
takes over its channel. `:Replay1Init`

- Each tick fills one half, 313 bytes. The halves alternate. `:Play1`
- Each track runs its note's resampler. Both outputs are added 4 bytes at once.
  `:ResampleTrack` `:AddPacked`
  - **Trap:** a carry spills into the byte before, as in replay 2.

## Open questions

- Replay 1 never syncs with the channel. Does the write position drift into the
  half that plays (guess)? `:Play1`
- Replay 2 writes the queued buffer's `AUDxPER` while the last buffer plays. Do
  its last bytes play at the new period (guess)? `:SetPeriods`
