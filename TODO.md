# Open work

The hand-off between sessions. What belongs here: see
[`AGENTS.md`](AGENTS.md#sessions).

## Pilot

Twelve cards test the card template before the full survey.

Selection rules:

- Formats that did not prevail on the demoscene. No `ProTracker`-like players.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- `replay` must be `uade` in the output of `tools/inventory.py`.

All twelve pilot cards exist.

### Rejected

| Player                     | Reason                              |
| -------------------------- | ----------------------------------- |
| `PreTracker`               | Replay code is a prebuilt binary    |
| `Pokeynoise`, `ADPCM_mono` | Too primitive or already well known |
| `Mugician`                 | Covered by `MugicianII`             |
| `JochenHippel-7V`          | Mixing is covered by `MugicianII`   |
| `PTK-Prowiz`               | `ProTracker`-like                   |

## After the pilot

- [ ] Review the cards with the user.
- [ ] Tune limits in `tools/cogload.py` and the card template.
- [ ] Fix the classification axes: control, themes, streams. They live in the
      glossary and the card template.
- [ ] Write the first technique pages in `ideas/`.
- [ ] Write a `TimFollin` card. Source is a `disassembly`. Replay:
      `ext/uade/amigasrc/players/other/timfollin/DP_TimFollin.asm:_play1`.
- [ ] Add a check that `ideas:` slugs in cards exist.
- [ ] Generate a technique index from the slugs, for the front page.

## Open questions

### Needs outside material

- Modules: which songs use a feature? MED list jumps, TFMX Pro riffs and byte
  checks, SoundPlayer `DD` and modulation in Lemmings.
- Docs or credits: Sonic Arranger's `AMF` name. Other games with Digital Sonix &
  Chrome. Other Synth Dream composers.
- The sound chip's datasheet: compare the Hippel ST volume table with the chip.

## Later

- [ ] Full survey of the remaining players with readable source.
- [ ] Compare code for the `name` lineage links in `data/players.yaml`.
- [ ] Note `ProTracker`-like players in `data/players.yaml`.
- [ ] Pick the first binary-only player to disassemble. Filter by scope first.
- [ ] Before disassembling a player, look for a port of it outside UADE. Use it
      as a map, not as evidence.
- [ ] Module players: decide where sample modules come from.

## Reading notes: `TimFollin`

Source: `ext/uade/amigasrc/players/other/timfollin/DP_TimFollin.asm`. Read in
full; no card yet.

- Streams: one byte track per voice, no positions or patterns. Byte `> 0` is a
  note, then a duration byte (`L_103E`). Byte `<= 0` is an opcode via `bratab`.
- Control: `program` level. Call, return, goto, counted loop (`L_1120`,
  `L_1150`, `L_113E`, `L_10E6`, `L_10F2`).
- Instruments carry only a sample: length word and data at `+$32` (`L_D8E`). The
  track sets all expression.

| Opcode | Label    | Effect                                                       |
| ------ | -------- | ------------------------------------------------------------ |
| 1      | `L_11F2` | Select instrument                                            |
| 6      | `L_1166` | Envelope: start, attack and decay speed, sustain level       |
| 7      | `L_11AE` | Portamento speed; next note becomes the target (`L_F98`)     |
| 8      | `L_119E` | Trill: note +n / −n, separate up and down times (`L_F5E`)    |
| 9      | `L_11B6` | Delayed vibrato or sweep in period units (`L_F1C`)           |
| 10     | `L_115E` | Transpose                                                    |
| 11     | `L_1102` | Fixed duration; notes then carry no duration byte            |
| 13     | `L_11E2` | Flags: next wave index (bits 0–5), chain (6), early gate (7) |
| 14     | `L_1218` | Pulse-width sweep speed; resets the pulse (`L_1226`)         |
| 17     | `L_11CA` | Next note ignores transpose                                  |

- Pulse-width modulation: `L_E1E` moves the edge of a 32-byte pulse between
  indexes 4 and `$1E`. Only instruments 0–3.
- Sample chaining (flag bit 6): one frame after the note starts, `L_D40` sets a
  second sample. The first sample plays once.
- Open: `L_1226` resets bytes at `+2`, but the pulse edits and playback use
  `+$32`. Adapter bug or format detail? Not yet known.
- Song hacks: subsong 13 volume (`L_DFA`), subsong 14 start volume (`L_B78`).
- Guess: "Mike D." is Mike Follin. Guess: the 15 fixed subsongs tie it to one
  game.

## Disassembly queue

A port is not evidence (see [`AGENTS.md`](AGENTS.md#evidence)). These players
need 68k code first.

| Player                   | Why                                          | Map                              |
| ------------------------ | -------------------------------------------- | -------------------------------- |
| `AbyssHighestExperience` | Card rests on a port; re-check it            | `ext/ahx2play`                   |
| `RobHubbard`             | Replay code is in the module; needs a module | `ext/c-flod/neoart/flod/hubbard` |
| `BenDaglish-SID`         | Replay code is in the module; needs a module | —                                |
| `JankoMrsicFlogel`       | Replay code is in the module; needs a module | —                                |
| `Special-FX`             | Replay code is in the module; needs a module | —                                |

## Disassembly notes

Tooling works; no config is committed yet. Workflow:
[`tools/disasm.py`](tools/disasm.py).

- Seeding was tried on `DeltaMusic2.0`, `SIDMon2.0`, `Laxity` and
  `TFMX-7V-TFHD`.
- `-preproc` misses code reached by jump tables or pointers. Example:
  `TFMX-7V-TFHD` keeps `4e75` (`rts`) inside data at `$060c`. Add `CODE` ranges
  by hand.
- IRA 2.11 refuses `-preproc` over an existing `.cnf`. So `seed` runs once per
  tag entry and merges the areas.
- Many binary-only players are 1–3 kB. Some may be wrappers (guess). Check each
  one when its config is made.
