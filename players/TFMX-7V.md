---
player: TFMX-7V
template: 3
base: TFMX-Pro
ideas: [voice-mixing]
---

# TFMX 7V

[TFMX Pro](TFMX-Pro.md) with seven voices: voices 4–7 are mixed into channel 3.

## Unique ideas

- Voices 4–7 write a shadow, not Paula. The instrument program code is the same
  on every voice. `:FakeChannel`
  - Limits: voice 3 is silent while the mix plays.
- The mixer sums voices 4–7 into one buffer per tick. The sum is clipped, not
  divided. `:MixLoop` `:BuildMixTables`
  - Limits: CPU high. At 16 kHz, mixing takes about 60% of a 7.09 MHz 68000
    (estimate).
  - Limits: the tables take 17,408 bytes.
- Channel 3's audio interrupt runs the whole replay. The tick and the buffer
  never drift apart. `:HookChannel3` `:MixTick`
  - Limits: the buffer length sets the tick rate. `:MixOn`

## How it plays

Channel 3's audio interrupt runs the replay, not a timer. `:HookChannel3` Each
interrupt, the mixer fills a buffer, then runs one TFMX Pro tick. `:MixTick`

- **Trap:** the speed command keeps only its `speed`. Its timer word does
  nothing. `:CmdMixSlow`

### Mixer

The mixer holds the mix rate, a slow-down in percent and two buffers. It also
holds a silent buffer, 64 volume tables and the clip table. `:Mixer`

- Bytes per tick = mix rate × 20 × (100 + slow-down) / 100, rounded to even. At
  the default 16 kHz, a tick lasts about 1/50 s (estimate). `:MixOn`
- A position command sets the slow-down, at least −32. Mixing then restarts.
  `:CmdMixSlow`
  - **Trap:** a longer buffer also makes a longer tick. The song slows down.

Each interrupt, in this order: `:MixTick`

1. `AUD3LC` and `AUD3LEN` get the other buffer. Paula takes them at its next
   reload.
2. Each shadow's volume and period become a volume table and a step. Step = mix
   period / voice period. `:VolumeAndStep`
   - A period of 0 keeps the last table and step.
   - A volume above 63 plays as 63.
3. Each shadow's DMA flag acts. `:FakeDma`
4. The mixer fills the buffer from step 1. `:MixLoop`
   - Each voice reads a byte, looks it up in its volume table and steps on.
   - Past the end, the voice's loop takes over.
   - The clip table maps the sum of four to a signed byte. One voice alone plays
     at full level.
5. The TFMX Pro tick runs. `:TickFromMixer`
   - **Trap:** the tick runs after the mix. Its writes reach the buffer of the
     next interrupt, which plays one interrupt later. Voices 4–7 sound two ticks
     after voices 0–2 (estimate).

### Shadow

A shadow holds a location, length, period, volume and DMA flag. It also holds a
restart flag, a loop, a read position and a step. `:FakeChannel`

- DMA off sets the step to 0 and arms a restart. `:FakeDma`
- DMA on makes location and length the loop. The loop takes over at the next
  wrap. After a restart, it plays at once.
  - **Trap:** on voices 4–7, DMA off and DMA on act at once. A delayed DMA off
    reads on, and DMA on ends the program's tick. A program can run a tick apart
    on voices 0–3 and 4–7 (guess).
- A length under 32 words plays the silent buffer instead. `:ShortLoopSilent`
  - **Trap:** short synth waves are mute on voices 4–7.
- A program cannot wait for sample passes, on any voice. The opcode reads on.
  `:WaitLoopsOff`

### Voice switch

The mixer holds a flag: mixing on or off. `:Mixer`

- A note to voices 4–7 turns mixing on. A note to voice 3 turns it off.
  `:SwitchMixing`
- While mixing, a tick visits voices 0–2 and 4–7. It skips voice 3. `:MixOn`
  - **Trap:** the fade moves at each voice visit. Seven visits per tick make a
    fade 7/4 as fast as in TFMX Pro.
- While mixing, a visit to voices 4–7 writes the fade level to `AUD3VOL`. The
  voice's volume goes to its shadow, unfaded. `:FadeToChannel3`
- Mixing off silences channel 3. The shadows play the silent buffer. `:MixOff`
  - **Trap:** mixing off also turns off channel 3's interrupt, the replay's only
    clock. Only mixing on turns it back on. A note to voice 3 stops the song,
    unless a sound effect locks voice 3.

## Open questions

- Which songs play voice 3 as a plain voice? Did the original then clock the
  replay from a timer (guess)?
- Is this TFMX Pro's source built with its `on7voice` switch (guess)?
- Did the original use the `killf1`–`killf4` wrap hooks for the sample-pass wait
  (guess)?
