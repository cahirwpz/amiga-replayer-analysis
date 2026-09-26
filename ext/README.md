# Sources

The replayer code we read. Each folder here is a pinned git submodule.
`tools/inventory.py` maps every UADE player binary to its source.

## `uade`

The Unix Amiga Delitracker Emulator, from
[GitLab](https://gitlab.com/uade-music-player/uade).

- Player binaries: `ext/uade/players`, one file per format.
- Replayer sources: `ext/uade/amigasrc/players/<group>/<player>`.
- Groups: `defect`, `other`, `uade` and `wanted_team`. Wanted Team's sources are
  mostly disassemblies, adapted for EaglePlayer.
- Licences vary per work; see `ext/uade/COPYING`.
- Four source folders have no player binary: `other/max_trax`, `uade/ps3m`,
  `wanted_team/Musicline4V` and `wanted_team/Musicline8V`.

## `ahx2play`

A C port of the AHX 2.3d-sp3 replayer by Olav Sørensen, from
[GitHub](https://github.com/8bitbubsy/ahx2play). Licence: `BSD-3-Clause`.

- The original 68000 source was never published.

## `c-flod`

A C port of Flod 4.1, Christian Corti's replayers in ActionScript, from
[GitHub](https://github.com/rofl0r/c-flod). Licence: `CC-BY-NC-SA-3.0`. No
changes since 2019.

- Replayers: `ext/c-flod/neoart/flod/<folder>`.
- Its readme says 3–5% of Hippel tunes play wrong.
- Which player uses which port: `ports` and `source` in
  [`data/players.yaml`](../data/players.yaml).
- `trackers` and `fasttracker` hold `ProTracker`-like players: out of scope.
