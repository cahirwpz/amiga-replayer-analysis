---
player: DigitalSonixChrome
control: { sequencer: tables, instrument: none }
themes: [tricks]
ideas: [counted-loops, fixed-pitch-instruments, effects-steal-voices]
streams: { song: 2 }
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
  `:SfxClaimVoice` `:ReadRow`
- A position repeats its pattern N times. `:CountRepeats`

## Streams

| Stream    | Scope | Role      | Carries                               | Control | Rate        |
| --------- | ----- | --------- | ------------------------------------- | ------- | ----------- |
| Positions | song  | sequencer | pattern, repeat count, pattern length | loop    | pattern end |
| Pattern   | song  | sequencer | instrument number per voice, or none  | none    | row         |

## Sequencer

| Aspect   | Value                 | Label                        |
| -------- | --------------------- | ---------------------------- |
| Time     | rows                  | `:Play`                      |
| Unit     | row                   | `:Play`                      |
| Note end | next note, loop count | `:SetLoopCount` `:LoopsDone` |
| Routing  | fixed                 | `:ReadRow`                   |
| Reuse    | patterns, loops       | `:CountRepeats`              |
| Tempo    | none                  | `:Play`                      |

## Generators

| Generator    | Scope | States         | Writes | Rate        | Set by     | Note-on |
| ------------ | ----- | -------------- | ------ | ----------- | ---------- | ------- |
| Loop counter | voice | counting, done | sample | sample wrap | instrument | restart |

## Channel outputs

| Output | Writers, in tick order            |
| ------ | --------------------------------- |
| Volume | Pattern (set)                     |
| Period | Pattern (set)                     |
| Sample | Pattern (set), Loop counter (set) |
| DMA    | Pattern (on)                      |

## Interactions

| From         | To      | Event                                                       |
| ------------ | ------- | ----------------------------------------------------------- |
| game         | Pattern | A sound effect takes a voice until it ends `:SfxClaimVoice` |
| Loop counter | Pattern | At zero it gives the voice back `:LoopsDone`                |

- Effect numbers are priorities: a request plays if its number is at most the
  playing one. A free voice holds `$FF`. `:SfxClaimVoice` `:LoopsDone`
- A new note busy-waits for the channel's audio interrupt. `:WaitAudioIrq`
- A position with zero repeats ends the subsong. `:NextPosition`

## State

| Scope      | Fields                                                      |
| ---------- | ----------------------------------------------------------- |
| Voice      | passes left, loop start and length, effect playing, request |
| Instrument | period, length, loop start, loop count, volume              |
| Global     | position, row, repeats left, speed counter                  |

## Open questions

- Did any other game use this format?
