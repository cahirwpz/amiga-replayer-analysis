# Open work

The hand-off between sessions. What belongs here: see
[`AGENTS.md`](AGENTS.md#sessions).

## Pilot

Twelve cards test the card template before the full survey.

Selection rules:

- Formats that did not prevail on the demoscene. No `ProTracker`-like players.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- `replay` must be `uade` or `port` in the output of `tools/inventory.py`.

All twelve pilot cards exist.

### Rejected

| Player                                                           | Reason                              |
| ---------------------------------------------------------------- | ----------------------------------- |
| `RobHubbard`, `BenDaglish-SID`, `JankoMrsicFlogel`, `Special-FX` | Replay code is in the module        |
| `PreTracker`                                                     | Replay code is a prebuilt binary    |
| `Pokeynoise`, `ADPCM_mono`                                       | Too primitive or already well known |
| `Mugician`                                                       | Covered by `MugicianII`             |
| `JochenHippel-7V`                                                | Mixing is covered by `MugicianII`   |
| `PTK-Prowiz`                                                     | `ProTracker`-like                   |

## After the pilot

- [ ] Review the cards with the user.
- [ ] Tune limits in `tools/cogload.py` and the card template.
- [ ] Fix the classification axes: control, themes, streams. They live in the
      glossary and the card template.
- [ ] Write the first technique pages in `ideas/`.
- [ ] Add a check that `ideas:` slugs in cards exist.
- [ ] Generate a technique index from the slugs, for the front page.

## Open questions

- [ ] Decide: bring `RobHubbard` back? Its Flod port has its own replay logic
      and meets the `replay: port` rule.
      `ext/c-flod/neoart/flod/hubbard/RHPlayer.c:RHPlayer_loader`
- [ ] AHX: does the UADE binary replayer differ from the tracker code in
      `ext/ahx2play`? Needs an IRA disassembly of the binary.

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
- [ ] Before disassembling a player, look for a port of it outside UADE.
- [ ] Module players: decide where sample modules come from.

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
