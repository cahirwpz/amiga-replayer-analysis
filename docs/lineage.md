# Replayer lineages

A lineage is a chain of replayers where each version grows from the one before.
The card rule for lineages is in [`AGENTS.md`](../AGENTS.md#depth).

The Evidence column says how the link between versions is known:

| Evidence | Meaning                                        |
| -------- | ---------------------------------------------- |
| code     | We compared the replay code of both versions.  |
| port     | One port plays both versions with one player.  |
| docs     | The author or another first-hand page says so. |
| name     | Only the player names match. Not compared yet. |

## Shared code

One card covers the lineage. Versions are listed oldest first where known.

| Lineage          | Versions                                                                                                                                                                                                                                         | Card | Evidence                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---- | ----------------------------------------------------------------------------------------------------------------- |
| Future Composer  | [`FutureComposer1.3`](../data/inventory.csv?plain=1#L47 "FutureComposer1.3"), [`FutureComposer1.4`](../data/inventory.csv?plain=1#L48 "FutureComposer1.4")                                                                                       | 1.4  | code: 1.4 adds opcodes; waveforms move from player to module, `ext/uade/amigasrc/players/defect/fc14/FC1.4.s:203` |
| Digital Mugician | [`Mugician`](../data/inventory.csv?plain=1#L90 "Mugician"), [`MugicianII`](../data/inventory.csv?plain=1#L91 "MugicianII")                                                                                                                       | II   | port: `ext/c-flod/neoart/flod/digitalmugician/DMPlayer.c:652`                                                     |
| SoundMon         | [`SoundMon2.0`](../data/inventory.csv?plain=1#L141 "SoundMon2.0"), [`SoundMon2.2`](../data/inventory.csv?plain=1#L142 "SoundMon2.2")                                                                                                             | 2.2  | code: 2.2 adds the MOD walker and wave effects, `ext/uade/amigasrc/players/uade/soundmon/Soundmon2.2.s:758`       |
| Delta Music      | [`DeltaMusic1.3`](../data/inventory.csv?plain=1#L30 "DeltaMusic1.3"), [`DeltaMusic2.0`](../data/inventory.csv?plain=1#L31 "DeltaMusic2.0")                                                                                                       | 2.0  | name                                                                                                              |
| SIDMon           | [`SIDMon1.0`](../data/inventory.csv?plain=1#L130 "SIDMon1.0"), [`SIDMon2.0`](../data/inventory.csv?plain=1#L131 "SIDMon2.0")                                                                                                                     | 2.0  | name                                                                                                              |
| TFMX             | [`TFMX`](../data/inventory.csv?plain=1#L158 "TFMX"), [`TFMX-Pro`](../data/inventory.csv?plain=1#L161 "TFMX-Pro"), [`TFMX_ST`](../data/inventory.csv?plain=1#L164 "TFMX_ST")                                                                      | Pro  | name                                                                                                              |
| Jochen Hippel    | [`JochenHippel_UADE`](../data/inventory.csv?plain=1#L69 "JochenHippel_UADE"), [`JochenHippelCOSO`](../data/inventory.csv?plain=1#L70 "JochenHippelCOSO"), [`JochenHippel-CoSo_UADE`](../data/inventory.csv?plain=1#L68 "JochenHippel-CoSo_UADE") | open | name                                                                                                              |

## Distinct ideas

These versions get their own card, although they belong to a lineage above.

| Player                                                                     | Lineage       | Distinct idea                                  |
| -------------------------------------------------------------------------- | ------------- | ---------------------------------------------- |
| [`TFMX-7V`](../data/inventory.csv?plain=1#L159 "TFMX-7V")                  | TFMX          | seven voices, some mixed (guess from the name) |
| [`JochenHippel-7V`](../data/inventory.csv?plain=1#L67 "JochenHippel-7V")   | Jochen Hippel | seven voices, some mixed                       |
| [`Jochen_Hippel_ST`](../data/inventory.csv?plain=1#L65 "Jochen_Hippel_ST") | Jochen Hippel | Atari ST sound chip emulated on Paula          |

## History only

These authors built on older programs, but no code is shared that we know of.
Cards stay separate.

| Chain                                                                                                                                                            | Evidence                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Hülsbeck's C64 Soundmonitor, then [`SIDMon1.0`](../data/inventory.csv?plain=1#L130 "SIDMon1.0"), then [`Mugician`](../data/inventory.csv?plain=1#L90 "Mugician") | docs: [SIDMon page](https://proofofconcept.nl/portfolio/sidmon/) |
