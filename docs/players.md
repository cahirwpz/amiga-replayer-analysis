# Players

Facts per player that a code scan cannot find: provenance, lineage, authors. The
source is [`data/players.yaml`](../data/players.yaml). `tools/players.py`
generates the tables below; edit the YAML, not the tables.

## Cards

Provenance says where the replay code we read comes from. Its values are in
[the glossary](glossary.md#provenance).

<!-- cards:begin -->

| Player                                                                         | Card                                     | Provenance       | Who, when, where                                            | Links                                                 |
| ------------------------------------------------------------------------------ | ---------------------------------------- | ---------------- | ----------------------------------------------------------- | ----------------------------------------------------- |
| [`DigitalSonixChrome`](../data/inventory.csv?plain=1#L34 "DigitalSonixChrome") | [card](../players/DigitalSonixChrome.md) | disassembly      | Andrew E. Bailey and David M. Hanlon, 1990, Dragon's Breath |                                                       |
| [`FutureComposer1.4`](../data/inventory.csv?plain=1#L48 "FutureComposer1.4")   | [card](../players/FutureComposer1.4.md)  | original (guess) |                                                             |                                                       |
| [`MugicianII`](../data/inventory.csv?plain=1#L91 "MugicianII")                 | [card](../players/MugicianII.md)         | disassembly      | Reinier van Vliet                                           | [page](https://proofofconcept.nl/portfolio/mugician/) |
| [`SoundMon2.2`](../data/inventory.csv?plain=1#L142 "SoundMon2.2")              | [card](../players/SoundMon2.2.md)        | original         | Brian Postma                                                |                                                       |
| [`SoundPlayer`](../data/inventory.csv?plain=1#L143 "SoundPlayer")              | [card](../players/SoundPlayer.md)        | disassembly      | Scott Johnston, 1991, Lemmings                              |                                                       |

<!-- cards:end -->

## Lineages

A lineage is a chain of replayers where each version grows from the one before.
The card rule for lineages is in [`AGENTS.md`](../AGENTS.md#depth). Evidence
values are in [the glossary](glossary.md#lineage-evidence).

### Shared code

One card covers the lineage. Versions are listed oldest first where known.

<!-- lineages:begin -->

| Lineage          | Versions                                                                                                                                                                                                                                         | Card                                                        | Evidence                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Delta Music      | [`DeltaMusic1.3`](../data/inventory.csv?plain=1#L30 "DeltaMusic1.3"), [`DeltaMusic2.0`](../data/inventory.csv?plain=1#L31 "DeltaMusic2.0")                                                                                                       | `DeltaMusic2.0`                                             | name                                                                                                              |
| Future Composer  | [`FutureComposer1.3`](../data/inventory.csv?plain=1#L47 "FutureComposer1.3"), [`FutureComposer1.4`](../data/inventory.csv?plain=1#L48 "FutureComposer1.4")                                                                                       | `FutureComposer1.4` [card](../players/FutureComposer1.4.md) | code: 1.4 adds opcodes; waveforms move from player to module, `ext/uade/amigasrc/players/defect/fc14/FC1.4.s:203` |
| Jochen Hippel    | [`JochenHippel_UADE`](../data/inventory.csv?plain=1#L69 "JochenHippel_UADE"), [`JochenHippelCOSO`](../data/inventory.csv?plain=1#L70 "JochenHippelCOSO"), [`JochenHippel-CoSo_UADE`](../data/inventory.csv?plain=1#L68 "JochenHippel-CoSo_UADE") | open                                                        | —                                                                                                                 |
| Digital Mugician | [`Mugician`](../data/inventory.csv?plain=1#L90 "Mugician"), [`MugicianII`](../data/inventory.csv?plain=1#L91 "MugicianII")                                                                                                                       | `MugicianII` [card](../players/MugicianII.md)               | port, `ext/c-flod/neoart/flod/digitalmugician/DMPlayer.c:652`                                                     |
| SIDMon           | [`SIDMon1.0`](../data/inventory.csv?plain=1#L130 "SIDMon1.0"), [`SIDMon2.0`](../data/inventory.csv?plain=1#L131 "SIDMon2.0")                                                                                                                     | `SIDMon2.0`                                                 | name                                                                                                              |
| SoundMon         | [`SoundMon2.0`](../data/inventory.csv?plain=1#L141 "SoundMon2.0"), [`SoundMon2.2`](../data/inventory.csv?plain=1#L142 "SoundMon2.2")                                                                                                             | `SoundMon2.2` [card](../players/SoundMon2.2.md)             | code: 2.2 adds the MOD walker and wave effects, `ext/uade/amigasrc/players/uade/soundmon/Soundmon2.2.s:758`       |
| TFMX             | [`TFMX`](../data/inventory.csv?plain=1#L158 "TFMX"), [`TFMX-Pro`](../data/inventory.csv?plain=1#L161 "TFMX-Pro"), [`TFMX_ST`](../data/inventory.csv?plain=1#L164 "TFMX_ST")                                                                      | `TFMX-Pro`                                                  | —                                                                                                                 |

<!-- lineages:end -->

### Distinct ideas

These versions get their own card, although they belong to a lineage above.

<!-- distinct:begin -->

| Player                                                                     | Lineage       | Distinct idea                                  |
| -------------------------------------------------------------------------- | ------------- | ---------------------------------------------- |
| [`JochenHippel-7V`](../data/inventory.csv?plain=1#L67 "JochenHippel-7V")   | Jochen Hippel | seven voices, some mixed                       |
| [`Jochen_Hippel_ST`](../data/inventory.csv?plain=1#L65 "Jochen_Hippel_ST") | Jochen Hippel | Atari ST sound chip emulated on Paula          |
| [`TFMX-7V`](../data/inventory.csv?plain=1#L159 "TFMX-7V")                  | TFMX          | seven voices, some mixed (guess from the name) |

<!-- distinct:end -->

### History only

These authors built on older programs, but no code is shared that we know of.
Cards stay separate.

<!-- history:begin -->

| Older program                                                 | Player                                                        | Evidence                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------- |
| [`SIDMon1.0`](../data/inventory.csv?plain=1#L130 "SIDMon1.0") | [`Mugician`](../data/inventory.csv?plain=1#L90 "Mugician")    | docs: [page](https://proofofconcept.nl/portfolio/sidmon/) |
| Hülsbeck's C64 Soundmonitor                                   | [`SIDMon1.0`](../data/inventory.csv?plain=1#L130 "SIDMon1.0") | docs: [page](https://proofofconcept.nl/portfolio/sidmon/) |

<!-- history:end -->
