# Sources

The replayer code we read, and one emulator we run it on. Each folder here is a
pinned git submodule. `tools/inventory.py` maps every UADE player binary to its
source.

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

## `oktalyzer`

Franck Charlet's disassembly of the Oktalyzer 1.57 tracker by Armin Sander, from
[GitHub](https://github.com/hitchhikr/oktalyzer). Licence: `BSD-2-Clause`.

- Pinned at the first commit with `src/okta.asm`. Later commits change the
  mixer.
- `original/sources` holds the author's replay objects, `okplay1.o` and
  `okplay2.o`. Our IRA configs: `data/disasm/okplay1.cnf` and
  `data/disasm/okplay2.cnf`.
- `replay/` in later commits is a new replay, not the author's.

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

## `nostalgicplayer`

NostalgicPlayer by Thomas Neumann, a music player in C#, from
[GitHub](https://github.com/neumatho/NostalgicPlayer). Licence: `MIT`.

- Replayers: `ext/nostalgicplayer/Source/Agents/Players/<folder>`. Each names
  the original player's author.
- `Format_Descriptions`: the author's notes on 23 module formats.
- A sparse, partial and shallow clone of only those two folders: about 9 of 162
  megabytes. `activate` sets it up; a plain `git submodule update` would not.
- Which player uses which port: `ports` and `source` in
  [`data/players.yaml`](../data/players.yaml).

## `vamiga`

vAmiga by Dirk W. Hoffmann, an Amiga 500, 1000 and 2000 emulator, from
[GitHub](https://github.com/dirkwhoffmann/vAmiga). Licence: `MPL-2.0`.

- Pinned at tag v4.5.
- Only `Core`: the emulator without its user interface. About 12 of 152
  megabytes. `activate` sets it up, as for `nostalgicplayer`.
- `tools/timing.py` builds its driver against it. vAmiga's CPU is cycle-exact.
  It also models bus slots and Paula.
