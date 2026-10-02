---
player: FaceTheMusic
template: 3
ideas: [track-programs, voice-mixing, tracks-not-voices]
---

# Face The Music

Eight mixed tracks run track programs that react to note events and steer any
track.

## Unique ideas

- A track program is a list of 4-byte lines. It runs until a line waits.
  `:ScriptRun` `:ScriptWait`
  - Limits: a loop without a wait hangs the player.
  - Limits: loops do not nest. A track has one loop counter. `:ScriptLoop`
- A program names a handler line per event. Events are a new pitch, volume or
  sample, a release, a portamento and a fade. `:PatternEvent` `:ScriptEvent`
- A program can act on any track, its work track. `:SelectTrack` `:CopyPitch`
  `:CloneTrack`
- Each track has four LFOs. A target is pitch, volume, or an LFO's speed or
  depth. `:Lfos`
- Two tracks share each channel. Only the quieter one goes through a volume
  table, at the ratio of the two volumes. `:MixPairs` `:MixPair`
  - Limits: CPU is high. Each output byte costs two reads, a table read and an
    add.

## How it plays

A [CIA timer](../docs/paula-techniques.md#cia-timer) runs the tick. `:Tick`

Each audio interrupt mixes its channel's two tracks, as
[mixing](../docs/paula-techniques.md#mixing). The mix masks the timer's
interrupt. `:MixPairs`

A tick reads a row every `speed` ticks. Then each track runs its fade,
portamento, program and LFOs. `:Tick` `:TrackTick`

### Player

The player holds the row counter `SongLine`, the speed, the tempo and the global
volume. It holds the track mask and a stack of repeats. `:Module`

1. Each row, each track in the track mask reads its events. `:PlayRows`
2. The row counter advances. At a repeat's end or the song's end, every track
   seeks. `:SeekTrack`
3. A `REPEAT` with a count opens a repeat at the measure's start. Without a
   count, it closes the repeat. `:Repeat`
   - At the next measure, every track seeks back. Repeats nest.
   - **Trap:** the row counter is global. A `REPEAT` on one track repeats every
     track.

### Track

A track holds its events and wait, sample, play position, volume and pitch. It
holds the fade, the portamento, the program and four LFOs. `:Track`

Each row, its wait counts down. At its end, the next event plays: `:TrackRow`

1. A wait word after the event sets the rows to the next one. Without one, the
   track's spacing applies.
2. `START_SCRIPT` starts a program and clears its handlers. The work track
   becomes the program's own track. `:PatternEvent`
   - **Trap:** the LFOs keep running from the last program.
3. `PORTAMENTO` slides to a pitch over N rows. `FADE` slides the volume to 0.
   `:Portamento` `:Fade`
4. A note event holds a sample, a volume and a pitch in one word.
   - It holds 34 pitches, a semitone apart. One more value is the release.
   - Volume value 3 gives 0 (guess: a typo for 14).
   - A volume stops a fade. A pitch stops a portamento.
5. A new sample, a silent track or a sample without a loop restarts the sample.
   Otherwise the looping sample plays on at the new pitch. `:StartSample`
6. Each set part raises its handler. A release does nothing without one.
   `:PatternEvent`
   - **Trap:** one handler per track can wait. Pitch beats volume, and volume
     beats sample.

Each tick, the fade, the portamento and the program run, in this order. A
pending handler moves the program to its line. `:ScriptEvent`

A sample without a loop ends on a silent sample. `SilenceSample` or a fade to 0
also silences a track, with DMA on. `:MixPair`

### Program

A line holds an op and two arguments. Ops act on the work track. `:ScriptRun`

- Programs jump, loop, chain and branch on pitch or volume. A wait of 0 waits
  for a handler. `:ScriptChain` `:ScriptWait`
- Ops set or move pitch, in steps of 1/8 semitone. Others change volume, sample,
  play position and loop length. `:SetPitch` `:AddLoopLength`
- Two ops that move the sample start store the wrong register. `:AddSampleStart`
  `:SubSampleStart`
- **Trap:** a clone copies the whole track, also its events, program and detune
  pointer. The clone's detune changes the source's pair. `:CloneTrack`
- **Trap:** tempo, speed, global volume and `JumpToLine` are global. Any program
  changes the song. `:SetTempo` `:JumpToLine`
  - A jump's seek takes one row. No track reads events in it. `:PlayRows`

### LFO

An LFO holds a target, a limit, a wave, its position, speed, depth and last
value. `:Lfo`

Each tick, the target gets the wave value × depth / 128, minus the last value.
So LFOs stack. `:Lfos`

- A pitch target gets the change twice. With `once` set, an LFO stops at its
  wave's end.
- **Trap:** the target is on the work track. An LFO can move another track.
- **Trap:** a note sets the pitch, and the LFO's offset is lost. Its swing then
  centres off the note.
- **Trap:** the sum stays between 0 and the limit. A clamped change is lost. The
  centre drifts.
- **Trap:** LFO 4 does not reload the work track. Without a program, it can act
  on the previous track's work track.

### Mixer

Tracks 0 and 1 form pair 0, and so on. A pair holds two buffer halves, the next
period, the next volume and a detune. `:Module`

Each audio interrupt, in this order: `:MixPairs`

1. All four channels' `AUDxPER` and `AUDxVOL` get the values of their last mix.
   - **Trap:** a mix's values belong to its half. Another channel's interrupt
     can apply them before that half plays.
2. The higher-pitched track sets the next period. The lower track gets a skip
   step from the pitch difference plus the detune.
3. The louder volume × global volume / 64 is the next volume. The quieter track
   is scaled by their ratio. `:Scaled`
4. `AUDxLC` gets the other half. The pair mixes 100 words into it. `:MixPair`

The higher track gives one byte per output byte. The lower track repeats its
last byte when its skip step carries. `:MixPair`

- Nothing clips a pair's sum. A loud pair wraps around.
- **Trap:** the lower track loops early, by its pitch ratio. Its count of words
  left drops by one word per output word.

## Open questions

- Which modules use handlers and cross-track programs?
- Do real modules keep samples at half level to avoid the wrap-around?
