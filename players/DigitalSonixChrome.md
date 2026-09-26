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
  `data/annot/DigitalSonixChrome.yaml:SetFixedPeriod`
- Each instrument loops a set number of times, then falls silent.
  `:SetLoopCount` `:CountLoopPass`
- Game sound effects take a voice from the music until they end.
  `:SfxClaimVoice` `:CheckSfxVoice`
- A position repeats its pattern N times. `:CountRepeats`

## Streams

| Stream    | Scope | Carries                               | Control   | Rate        |
| --------- | ----- | ------------------------------------- | --------- | ----------- |
| Positions | song  | pattern, repeat count, pattern length | loop, end | pattern end |
| Pattern   | voice | instrument number, or nothing         | none      | row         |

## Generators and interactions

- Loop counter: the interrupt at each loop pass counts down. At zero it plays
  silence and frees the voice. `:CountLoopPass` `:LoopsDone`
- A new note busy-waits for the channel's audio interrupt. `:WaitAudioIrq`
- A position with zero repeats ends the subsong. `:NextPosition`

## State

| Scope      | Fields                                                      |
| ---------- | ----------------------------------------------------------- |
| Voice      | passes left, loop start and length, effect playing, request |
| Instrument | period, length, loop start, loop count, volume              |
| Global     | position, row, repeats left, speed counter                  |

## Open questions

- A lower instrument number wins a voice (`:SfxClaimVoice`). Is that a priority
  scheme?
- Did any other game use this format?
