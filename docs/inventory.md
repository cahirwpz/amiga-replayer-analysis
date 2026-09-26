# Inventory

Every replayer binary in `ext/uade/players`, and where its source is. Full list:
`data/inventory.csv`.

## Counts

| Group            | Players |
| ---------------- | ------- |
| Binaries in UADE | 176     |
| With source      | 131     |
| Binary only      | 45      |

Several players share one source directory, for example the `MED` and tracker
families. So 131 players map to 124 source directories.

## How source was found

| Method | Players | Meaning                                             |
| ------ | ------- | --------------------------------------------------- |
| hash   | 106     | A byte-identical binary sits next to the source.    |
| name   | 22      | Binary name matches a source file or directory.     |
| manual | 4       | Set by hand in `tools/inventory.py`.                |
| none   | 44      | Searched by name and version string. Nothing found. |

## Sources from outside UADE

`AbyssHighestExperience` (AHX) has no source in UADE. The original 68000 source
was never published. `ext/ahx2play` is a C port of the same replayer, used as
`evidence: port`.

## Source without a player binary

Four source directories have no binary in `ext/uade/players`:

- `other/max_trax`
- `uade/ps3m`
- `wanted_team/Musicline4V`, `wanted_team/Musicline8V`

## Caveats

- Line counts include old versions kept next to new ones. Treat them as upper
  bounds.
- Three binaries have no version string: `EMS-6`, `Mark_Cooksey_Old`,
  `ScottJohnston`.
- `SynthPack` matched a directory that holds no source. Hence 44 + 1
  binary-only.
- Binary-only players can still be classified from docs and sibling players.

## Regenerate

Run `python3 tools/inventory.py > data/inventory.csv` after moving the submodule
pin.
