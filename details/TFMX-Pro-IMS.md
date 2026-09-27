# TFMX Pro IMS

IMS rebuilds one voice's waveform every tick from a source in the sample file.
The model is `specs/tfmx_pro.py:ImsTick`.

## How it sounds

- Paula loops the voice's buffer. The buffer's length and the period set the
  pitch. `:ImsLength`
- Each tick, the read position starts at 0. Paula plays the buffer many times
  per tick, so every pass restarts the source. This is a hard sync. `:ImsTick`
- The step sets how much of the source fits in one pass. It changes the timbre,
  not the pitch. `:ImsSetStep`
- The step change bends the step within one pass. `:ImsSetStepChange`
- The filter limits each byte's move from the last byte: a slew limiter. Sharp
  edges become ramps. `:ImsFilter`

## Stages, per output byte

| Stage  | What it does                                       | Opcode | Label               |
| ------ | -------------------------------------------------- | ------ | ------------------- |
| Bend   | Adds the step change to the step                   | `$26`  | `:ImsSetStepChange` |
| Read   | Adds the step to the position; reads the source    | `$24`  | `:ImsSetStep`       |
| Wrap   | Masks the position with the source mask, `2^n - 1` | `$23`  | `:ImsLength`        |
| Filter | Moves the output towards the source byte, limited  | `$28`  | `:ImsFilter`        |
| Mirror | Writes a negated copy into the next voice's buffer | `$29`  | `:ImsOff`           |

## Sweeps, per tick

Each sweep adds a value every tick. Its sign turns every N ticks, so the value
swings. `:Swing`

| Value        | Opcode | Label                 |
| ------------ | ------ | --------------------- |
| Step         | `$25`  | `:ImsSweepStep`       |
| Step change  | `$27`  | `:ImsSweepStepChange` |
| Filter limit | `$28`  | `:ImsFilter`          |
| Source start | `$11`  | `:SweepTick`          |

A filter limit that sweeps down to 0 stays off. `:ImsTick`

## Examples

We ran the model on test sources. A 32-byte buffer and a 64-byte source:

| Source | Setting          | Result                                      |
| ------ | ---------------- | ------------------------------------------- |
| Sine   | step 1.5         | ¾ of a cycle, then a jump back to the start |
| Sine   | step change      | The cycle gets shorter along the buffer     |
| Square | step 2, limit 40 | Each edge becomes a ramp of five bytes      |

## Memory

- Voice n's buffer is in the sample file at `4 + $100 × n`. `:Ims`
- Voice 3's mirror writes past the four buffers, into the sample file (guess:
  the editor keeps this space free).
- Each voice builds up to 256 bytes per tick, so four voices build up to 1024.

## The mirror

The negated copy plays only if the next voice plays its own buffer. Paula puts
channels 0 and 3 on the left, 1 and 2 on the right. So voice 0 mirrors to the
other side, and voice 1 to the same side. The field is called `ims_dolby`. A
Dolby Surround decoder sends the difference of left and right to the rear
speakers (inference).
