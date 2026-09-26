# Sources

The replayer code we read. Each folder here is a pinned git submodule.
`tools/inventory.py` maps every UADE player binary to its source in
[`data/inventory.csv`](../data/inventory.csv).

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
- `trackers` and `fasttracker` hold `ProTracker`-like players: out of scope.

## Players per port

Generated from `ports` and `source` in
[`data/players.yaml`](../data/players.yaml).

- "source": the inventory points here.
- "cross-check": UADE has the source; the port is a second opinion.
- "possible source": UADE keeps this replay code in the music files.

<!-- ports:begin -->

| Player                                                                                | Port                                     | Use             |
| ------------------------------------------------------------------------------------- | ---------------------------------------- | --------------- |
| [`AbyssHighestExperience`](../data/inventory.csv?plain=1#L2 "AbyssHighestExperience") | `ext/ahx2play`                           | source          |
| [`DavidWhittaker`](../data/inventory.csv?plain=1#L29 "DavidWhittaker")                | `ext/c-flod/neoart/flod/whittaker`       | source          |
| [`DeltaMusic1.3`](../data/inventory.csv?plain=1#L30 "DeltaMusic1.3")                  | `ext/c-flod/neoart/flod/deltamusic`      | source          |
| [`DeltaMusic2.0`](../data/inventory.csv?plain=1#L31 "DeltaMusic2.0")                  | `ext/c-flod/neoart/flod/deltamusic`      | source          |
| [`Fred`](../data/inventory.csv?plain=1#L44 "Fred")                                    | `ext/c-flod/neoart/flod/fred`            | cross-check     |
| [`FutureComposer1.3`](../data/inventory.csv?plain=1#L47 "FutureComposer1.3")          | `ext/c-flod/neoart/flod/futurecomposer`  | cross-check     |
| [`FutureComposer1.4`](../data/inventory.csv?plain=1#L48 "FutureComposer1.4")          | `ext/c-flod/neoart/flod/futurecomposer`  | cross-check     |
| [`JochenHippel_UADE`](../data/inventory.csv?plain=1#L69 "JochenHippel_UADE")          | `ext/c-flod/neoart/flod/hippel`          | cross-check     |
| [`JochenHippelCOSO`](../data/inventory.csv?plain=1#L70 "JochenHippelCOSO")            | `ext/c-flod/neoart/flod/hippel`          | cross-check     |
| [`Mugician`](../data/inventory.csv?plain=1#L90 "Mugician")                            | `ext/c-flod/neoart/flod/digitalmugician` | cross-check     |
| [`MugicianII`](../data/inventory.csv?plain=1#L91 "MugicianII")                        | `ext/c-flod/neoart/flod/digitalmugician` | cross-check     |
| [`RobHubbard`](../data/inventory.csv?plain=1#L124 "RobHubbard")                       | `ext/c-flod/neoart/flod/hubbard`         | possible source |
| [`SIDMon1.0`](../data/inventory.csv?plain=1#L130 "SIDMon1.0")                         | `ext/c-flod/neoart/flod/sidmon`          | cross-check     |
| [`SIDMon2.0`](../data/inventory.csv?plain=1#L131 "SIDMon2.0")                         | `ext/c-flod/neoart/flod/sidmon`          | source          |
| [`Sound-FX`](../data/inventory.csv?plain=1#L136 "Sound-FX")                           | `ext/c-flod/neoart/flod/soundfx`         | cross-check     |
| [`SoundMon2.0`](../data/inventory.csv?plain=1#L141 "SoundMon2.0")                     | `ext/c-flod/neoart/flod/soundmon`        | cross-check     |
| [`SoundMon2.2`](../data/inventory.csv?plain=1#L142 "SoundMon2.2")                     | `ext/c-flod/neoart/flod/soundmon`        | cross-check     |

<!-- ports:end -->
