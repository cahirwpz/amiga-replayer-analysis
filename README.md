# Amiga replayer analysis

How did Amiga musicians get so much out of four 8-bit sample channels? This repo
reads the source of the replayers in UADE and records their ideas, briefly.

The focus is on formats that did not become the demoscene standard. `ProTracker`
and its many relatives are left out.

## Techniques found so far

| Technique                | What it does                                                   | Seen in                                                                                                                |
| ------------------------ | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Waveform as table        | One small waveform serves as sound, envelope and vibrato curve | [Mugician II](players/MugicianII.md)                                                                                   |
| In-place wave effects    | Every few ticks the player rewrites a looping waveform         | [Mugician II](players/MugicianII.md), [all 15 effects](details/MugicianII-effects.md)                                  |
| Swing                    | Rows alternate between two lengths                             | [Mugician II](players/MugicianII.md)                                                                                   |
| Soft voice mixing        | The CPU sums extra voices into one channel                     | [Mugician II](players/MugicianII.md)                                                                                   |
| Instrument command lists | Volume and pitch are small programs: loop, jump, wait          | [Future Composer 1.3](data/inventory.csv?plain=1#L47 "FutureComposer1.3"), [MED](data/inventory.csv?plain=1#L84 "MED") |
| Macro programs           | Instruments run bytecode with conditions and calls             | [TFMX Pro](data/inventory.csv?plain=1#L161 "TFMX-Pro")                                                                 |
| Table walkers            | Four envelope tables per voice, each off, once or looping      | [SoundMon 2.2](data/inventory.csv?plain=1#L142 "SoundMon2.2")                                                          |
| Attach modes             | One channel modulates another channel's volume or period       | [SoundPlayer](data/inventory.csv?plain=1#L143 "SoundPlayer")                                                           |
| Counted loops            | Audio interrupts count sample repeats, then switch buffers     | [Digital Sonix & Chrome](data/inventory.csv?plain=1#L34 "DigitalSonixChrome")                                          |

Linked rows lead to a player card. The others are backed by source code alone.

## Where to start

1. [Paula in one page](docs/paula.md): the hardware every replayer works around.
2. The technique table above.
3. [Player cards](players/): one page per replayer.
4. [Details](details/): deep dives, only where a card needs one.

Unknown terms are in [the glossary](docs/glossary.md).

## What a card tells you

- What steps through data per song, per voice and per instrument.
- What state the player keeps, and what an instrument can carry.
- Key ideas, each with the source line that shows it.

The shape is fixed by [the card template](docs/card-template.md).

## Evidence

- Every claim in a player card cites a source line.
- Sources: UADE's replayers, original or disassembled, and a C port of `AHX`.
- Players whose replay code hides inside music files are left out.
- What you would hear is marked as "(inference)".

[The inventory](docs/inventory.md) lists every UADE replayer and its source.

## Contributing

- Run `source ./activate` in the repo root. It fetches the sources and installs
  the pre-commit checks.
- Writing rules and checks: [`AGENTS.md`](AGENTS.md).
- Open work: [`TODO.md`](TODO.md).
