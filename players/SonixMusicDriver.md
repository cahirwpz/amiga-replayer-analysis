---
player: SonixMusicDriver
template: 3
ideas:
  [
    event-scores,
    instrument-drivers,
    filter-bank,
    subtractive-synth,
    tempo-independent-rates,
  ]
---

# Sonix Music Driver

A synth note plays through a bank of 64 low-pass copies of its wave. It sounds
like an analog synth (inference).

## Unique ideas

- A score is four tracks of events, not rows. A wait event counts ticks, like a
  MIDI sequencer's delta time. `:ReadEvent`
  - Limits: there are no patterns. Every note is stored.
- Each instrument type has a driver with a tick routine and a register routine.
  `:TickInstruments`
- At load, each synth's wave is filtered into 64 low-pass copies. Each tick,
  envelope and LFO set the filter position. `:SetFilter` `:SelectFilter`
  - Limits: the bank costs 8 kB per synth instrument.
- High notes skip wave bytes, instead of a shorter period. The period stays
  between 214 and 428. `:OctaveShift`
  - Limits: the top octave plays a
    [4-byte wave](../docs/paula-techniques.md#short-wave-loops).
- A wave mode rebuilds the wave each tick. `:BlendCopy` `:StretchHalves`
  - A blend averages the wave with a copy read from a moving offset. It sounds
    like phasing (inference).
  - A stretch plays one half of the wave in more bytes and the other in fewer.
    It sounds like a pulse width sweep (inference).
- Every rate step is multiplied by the tick length, a constant divided by the
  tempo. A tempo change keeps envelopes, LFOs and portamento at their speed.
  `:SetTempo`

## How it plays

One [CIA timer](../docs/paula-techniques.md#cia-timer) interrupt runs the tick.
The tempo sets its rate. There is no audio interrupt.

A tick steps the master volumes, then reads all tracks. Then each voice runs its
driver's tick, and each voice its register routine. `:PlaySNX`

### Player

The player holds the tempo, the tick length and a master volume per voice.
`:Module`

- A `SET_TEMPO` event sets the tempo and the timer rate at once. Tempo 125 gives
  50 Hz. `:TempoEvent`
- When all four tracks have ended, every voice gets a release. All tracks
  restart in the same tick. `:ReadTracks` `:RestartScore`
  - **Trap:** the restart keeps the last `SET_TEMPO`. `:RestartScore`

### Track

Track N drives voice N. It holds its event position, wait, instrument, volume
and pitch bend. `:Voice`

Each tick, a track reads events up to the next `WAIT`, once its wait runs out.
`:ReadEvent`

1. A note with velocity 0 releases the voice's note, whatever its note number.
   `:NoteEvent`
2. Other notes get a volume from track volume × velocity, 0 to 255. The voice
   gets a start request with the track's instrument. `:NoteEvent`
3. `SET_INSTRUMENT`, `SET_VOLUME` and `SET_BEND` set the track's state.
   `:InstrumentEvent`
   - Pitch bend picks one of 64 period factors, × 1.52 to × 0.67. All drivers
     apply it.
4. `TRACK_END` stops the track. `:ReadEvent`
   - **Trap:** a track's end releases nothing. Its last note sounds until all
     four tracks end.

### Voice

A voice holds a request, a state, its note, its instrument and its note volume.
`:Voice`

- The request is start or release.
- The state is off, held or released.

Each tick, in this order: `:TickInstruments`

1. A voice with a request or a state runs its driver's tick. A start request
   makes the state held, a release request released.
2. Each voice that is not off runs its register routine.
3. After a [DMA restart wait](../docs/paula-techniques.md#dma-restart-wait), DMA
   goes on for the new notes.

- A start on a held voice of another instrument type stops it first. DMA goes
  off, and `AUDxPER` gets 2. `:StartNote` `:StopNote`
- A note outside the driver's range is dropped. A held note then sounds on.
  `:SynthTick` `:SampledTick`

A released voice keeps DMA on. It falls silent at
[volume 0](../docs/paula-techniques.md#silence-by-volume). Only another type's
note turns DMA off.

### Synth driver

A synth voice holds a period, portamento steps, an envelope and an LFO phase. It
owns a wave phase and two 128-byte buffer halves. `:SynthState`

A start request: `:SynthStart`

1. From an off voice, the level starts at 0. Unless held, the envelope restarts
   at attack. `:Legato`
   - A note on a held voice is legato and keeps its envelope.
   - **Trap:** driver state belongs to the voice. A new synth instrument on a
     held voice keeps the level.
2. The period starts at the last synth period and steps to the new note. The
   steps last the portamento time. `:Portamento`
   - **Trap:** the last synth period outlives sample notes in between. Every
     synth note but a voice's first glides.
3. The LFO restarts after its delay, unless its mode is 0. `:Lfo`
4. The wave phase restarts only without a wave mode. `:SynthStart`

Each tick, in this order: `:SynthTick`

1. The LFO steps and reads its table. `:Lfo`
2. The level moves towards the stage's level. `:EnvelopeSetup`
3. While the period is above 428, it halves. `:OctaveShift`
4. `AUDxPER` gets the period × LFO × pitch bend. `:OctaveShift`
5. `AUDxVOL` gets the volume minus the LFO, × level, × note volume and master
   volume. `:OctaveShift`
   - The sum wraps at 256. A large LFO amount turns a loud note quiet.
   - Without envelope-to-volume, a release sets volume 0 at once.
6. The filter position is the base minus envelope and plus LFO. Its copy goes
   into the other buffer half. `:SelectFilter`
   - **Trap:** the filter position wraps. Past the brightest copy, it jumps to
     the darkest.
7. `AUDxLC` gets that half. Paula takes it at the loop's end, with no restart.
   `:SynthWrite`
   - **Trap:** above tempo 162, a tick is shorter than a 128-byte loop at 428
     (estimate). The driver then rewrites the half that Paula plays (guess).

### Sample drivers

A sample voice holds a period, an envelope stage and level, and a vibrato phase.
`:SampleState`

1. A note picks an octave of the sample. `:SampledTick`
2. The tick turns DMA off and sets `AUDxPER` to 2. The register routine writes
   the whole octave to `AUDxLC` and `AUDxLEN`. `:SampleWrite`
3. The next tick writes the loop, as a
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). Without a loop,
   it writes a [silent loop](../docs/paula-techniques.md#silent-loop).
4. Each tick, a `.ss` voice runs vibrato and the envelope. `:SampledTick`
5. An 8SVX voice has no envelope. A release sets volume 0. `:IffTick`
