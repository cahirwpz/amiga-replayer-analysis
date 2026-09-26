# Inventory

Every replayer binary in `uade/players`, and where its source is. Full list:
`data/inventory.csv`.

## Counts

| Group                 | Players |
| --------------------- | ------- |
| Binaries in UADE      | 176     |
| With assembler source | 130     |
| Binary only           | 46      |

Several players share one source directory, for example the `MED` and tracker
families. So 130 players map to 123 source directories.

## How source was found

| Method | Players | Meaning                                             |
| ------ | ------- | --------------------------------------------------- |
| hash   | 106     | A byte-identical binary sits next to the source.    |
| name   | 22      | Binary name matches a source file or directory.     |
| manual | 3       | Set by hand in `tools/inventory.py`.                |
| none   | 45      | Searched by name and version string. Nothing found. |

## Source without a player binary

Four source directories have no binary in `uade/players`:

- `other/max_trax`
- `uade/ps3m`
- `wanted_team/Musicline4V`, `wanted_team/Musicline8V`

## Caveats

- Line counts include old versions kept next to new ones. Treat them as upper
  bounds.
- Three binaries have no version string: `EMS-6`, `Mark_Cooksey_Old`,
  `ScottJohnston`.
- `SynthPack` matched a directory that holds no source. Hence 45 + 1
  binary-only.
- Binary-only players can still be classified from docs and sibling players.

## Regenerate

Run `python3 tools/inventory.py > data/inventory.csv` after moving the submodule
pin.
