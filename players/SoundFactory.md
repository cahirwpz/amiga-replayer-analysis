---
player: SoundFactory
template: 3
ideas:
  [
    voice-streams,
    stream-sync-counter,
    inline-instruments,
    wave-sweeps,
    length-tuned-waves,
  ]
---

# SoundFactory

Each voice runs its own stream of notes and opcodes, with no rows. The streams
sync through one shared counter.

## Unique ideas

- Each voice has its own stream. A note holds its length in ticks. `:ReadStream`
  - Streams call, jump and loop on a stack per voice. `:OpCall` `:OpLoopStart`
  - Limits: the composer keeps the voices in step by hand.
- One voice counts a shared counter up. Another waits until it holds a value.
  `:OpSignal` `:OpWaitSignal`
- An instrument is defined inside a stream. `:OpDefineInstrument`
- Effect opcodes write into the instrument, not into the voice. `:OpAdsr`
  - Limits: two voices cannot play one instrument with different effects.
- Phasing and a low-pass filter rebuild a short wave into a buffer per voice.
  Each sweeps its setting between two limits. `:WaveEffects`
  - CPU: medium. Each step rebuilds the whole wave.
- A wave's period divides by its length and multiplies by its cycles.
  `:NotePeriod`
- Each envelope phase takes its setting in ticks, whatever the levels. `:Attack`
  `:Release`

## How it plays

The host's timer tick runs the replay. There is no audio interrupt. `:Play`

A tick runs the fade, then voices 3 to 0. Last, after a short wait, DMA goes on
for the voices that started a note. `:Play`

### Player

The player holds the voice mask, the shared counter and the fade. It also holds
32 instrument slots. `:Module`

- A song is a voice mask and four stream offsets. A module holds up to 16 songs.
  `:InitSong`
- A song start fills every instrument slot with a quiet default instrument.
- A fade moves the master level by its speed / 4 per tick. `:Fade`
  - A fade-in starts near silence and ends at full.
  - A fade-out that reaches 0 stops the song. `:StopSong`
- **Trap:** voices run from 3 to 0. Voice 3 sees voice 0's signal a tick later.
  `:OpSignal`

### Voice

A voice holds its stream place, stack and ticks to the next event. It holds its
instrument number, note, period, envelope and a 256-byte wave buffer. `:Voice`

Each tick, the voice counts down its ticks to the next event: `:PlayVoice`

1. One tick before the next event, DMA goes off. This happens only for periods
   of 429 and above. `:EarlyStop`
   - It skips the stop when the next byte is `OpWait` or a `LEGATO` note.
   - **Trap:** it reads only the next byte. An opcode before a `LEGATO` note
     still stops DMA.
2. At the event, the voice reads its stream until a note, a wait or a rest. That
   tick runs no effects. `:ReadStream`
   - **Trap:** the envelope pauses for one tick at each event.

Stream bytes below `FIRST_OPCODE` are notes. A note byte is followed by a length
word. `:NoteOn`

1. The note turns DMA off. The note plus the transpose sets the period.
   `:NotePeriod`
   - **Trap:** a portamento starts from the last note's period, not from where
     the last slide stood. A new note during a slide jumps.
2. A length of 0 stops here. The stream reads on, and the next note sounds.
3. Half the length sets the hold: the ticks until the release.
4. Octave flip, vibrato and tremolo restart.
5. Without `LEGATO`, the envelope restarts. An attack starts at 0, a decay at
   full. Else it starts at the sustain level.
   - **Trap:** a `LEGATO` note still restarts the sample. It keeps only the
     envelope.
   - **Trap:** a `LEGATO` note after the release keeps releasing.
6. `AUDxLC` and `AUDxLEN` get the wave or the voice's buffer, up to the loop
   end. `AUDxVOL` and `AUDxPER` follow. `:WriteVoice`

Opcodes run in the same tick, until one ends it:

- `OpWait` waits N ticks, and the note sounds on. `OpRest` waits with DMA off.
  `:OpRest`
- `OpLoopStart` takes a count. A count of 0 plays 256 times. `:OpLoopEnd`
- `OpWaitSignal` takes a value. Until the counter holds it, the voice reads it
  again each tick. `:OpWaitSignal`
  - **Trap:** while it waits, the voice writes no registers. Its envelope and
    effects stand still.
- **Trap:** `OpVolume` 0 means full, not silence. So does tremolo level 0.
  `:OpVolume`

On the other ticks, the voice runs its effects in this order: `:VoiceEffects`

1. Two ticks after a note, the loop starts by
   [loop by reload](../docs/paula-techniques.md#loop-by-reload). A one-shot
   sample without a loop gets a
   [silent loop](../docs/paula-techniques.md#silent-loop).
   - **Trap:** a sample with no loop and no `ONE_SHOT` repeats as a whole.
2. Tremolo, portamento, octave flip and vibrato step. `:Tremolo` `:Portamento`
   `:Vibrato`
3. The envelope steps. `:EnvelopeTick`
   - After the hold, the release starts once the level reaches sustain.
     `:AutoRelease`
   - `HOLD` skips the release. There is no note-off.
   - A one-shot sample with a loop plays its tail at the release. Two ticks
     later it gets the silent loop.
4. Phasing moves its offset, and the filter its width. Either move rebuilds the
   buffer. `:BuildPhasing` `:BuildFilter`
   - **Trap:** with phasing on, the filter works in place. Its last means read
     bytes it already wrote.
   - **Trap:** a wave over 256 bytes runs into the next voice's buffer.
5. `AUDxVOL` gets the envelope level × tremolo × volume × fade, each a factor
   of 256. `:WriteVoice`
6. `AUDxPER` gets the slide or note period, plus vibrato. Octave flip halves it.
   The detune is added last.
   - `OpDetune` adds 0 to 255. Effects add in periods. Low notes move less.

A voice falls silent by `OpRest`, `OpStop`, a silent loop or the early stop. A
release to 0 leaves DMA on. `:OpStop`

### Instrument

An instrument holds a wave or sample, its loop, flags and envelope. It holds the
settings of every effect. `:Instrument`

- `OpDefineInstrument` puts the definition's address in a slot. The stream skips
  its bytes. `:OpDefineInstrument`
  - **Trap:** before a stream passes the definition, its number plays the
    default instrument. Another voice's stream may define it later.
- `OpInstrument` picks a slot by number, modulo 32. `:OpInstrument`
  - **Trap:** effects read the instrument every tick. A new number changes the
    playing note's effects and envelope.
- Effect opcodes switch a flag in the current instrument and write its settings.
  `:OpTremolo`
  - **Trap:** the change reaches every voice that plays the instrument, at once.
  - **Trap:** the opcodes write into the module's bytes. A song played again
    starts with the edited instruments.

## Open questions

- Which modules use the shared counter, and for what? `:OpWaitSignal`
- Why does the early DMA stop skip periods below 429? Short periods may restart
  in time anyway (guess). `:EarlyStop`
