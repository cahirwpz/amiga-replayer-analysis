---
player: DigitalSonixChrome
control: tables
themes: [tricks]
ideas: [counted-loops, fixed-pitch-instruments, effects-steal-voices]
streams: { song: 1, voice: 1 }
---

# Digital Sonix & Chrome

Audio interrupts count how often each instrument loops, so the tick does almost
nothing.

## Key ideas

- A row names only an instrument. Each instrument has a fixed period.
  `src/Digital Sonix & Chrome_v1.asm:1293`
- Each instrument loops a set number of times, then falls silent. `:1256`
  `:1320`
- Game sound effects take a voice from the music until they end. `:648` `:759`
- A position repeats its pattern N times. `:856`

## Streams

| Stream    | Scope | Carries                               | Control   | Rate        |
| --------- | ----- | ------------------------------------- | --------- | ----------- |
| Positions | song  | pattern, repeat count, pattern length | loop, end | pattern end |
| Pattern   | voice | instrument number, or nothing         | none      | row         |

## Generators and interactions

- Loop counter: the interrupt at each loop pass counts down. At zero it plays
  silence and frees the voice. `:1320` `:1353`
- A new note busy-waits for the channel's interrupt flag. `:1288`
- A position with zero repeats ends the subsong. `:876`

## State

| Scope      | Fields                                                      |
| ---------- | ----------------------------------------------------------- |
| Voice      | passes left, loop start and length, effect playing, request |
| Instrument | period, length, loop start, loop count, volume              |
| Global     | position, row, repeats left, speed counter                  |

## Open questions

- A lower instrument number wins a voice (`:651`). Is that a priority scheme?
- Did any other game use this format?
