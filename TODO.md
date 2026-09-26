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
| `JochenHippel-7V`          | Same mixer as `TFMX-7V`             |
| `PTK-Prowiz`               | `ProTracker`-like                   |

## After the pilot

### Fix the current cards

- [ ] Re-check the `AbyssHighestExperience` card against a disassembly. See the
      disassembly queue.
- [ ] Tune limits in `tools/cogload.py` and the card template.
- [ ] Fix the classification axes: control, themes, streams. They live in the
      glossary and the card template.

### New cards: MIDI model

- [ ] `MIDI-Loriciel` card. Reading notes below. The MIDI events it handles, CCs
      included, go to a `details/` page.

### Then

- [ ] Review the cards with the user.
- [ ] Write more technique pages in `ideas/`; `voice-mixing` is the first.
- [ ] Add a check that `ideas:` slugs in cards exist.
- [ ] Generate a technique index from the slugs, for the front page.

## Open questions

### Needs outside material

- Modules: which songs use a feature? MED list jumps, TFMX Pro riffs and byte
  checks, SoundPlayer `DD` and modulation in Lemmings. TFMX 7V notes to voice 3.
- Releases: did a game or demo ship Oktalyzer's replay 1? Which games used
  MaxTrax?
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

## Reading notes: MIDI model

`MIDI-Loriciel` source: `MIDI - Loriciel_v1.asm`. Labels are Wanted Team's.

- `lbC00001C`: reads an SMF; one state per `MTrk`. Tempo from the header.
- `Play`: per track, subtract 4 pulses per tick; read events when due.
- `lbW00052A`: note-on, note-off, program change. Note-on with velocity 0 is a
  note-off (`lbC0001C8`).
- `lbW00053E`: meta events. Tempo `$51` sets the timer (`lbC00024C`); end of
  track `$2F`; `$20` sets the MIDI channel. Other events are skipped.
- `lbC000B30`: voice allocation. It takes a free voice first. Else it steals a
  voice of the same MIDI channel, else voice 0.
- `lbC000B66`: note-off frees the voice only if the MIDI channel's last note
  matches.
- `lbC000844`: program change picks a multisample; note ranges choose the
  sample. `lbC000904`: velocity curve to volume.

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

Tooling works for player binaries, executables and object files. vlink links
objects; `listing` checks that vasm rebuilds the input. Workflow:
[`tools/disasm.py`](tools/disasm.py).

- Committed configs: `okplay1` and `okplay2`, Oktalyzer's replay objects. They
  match `okta.asm`. No player config yet.
- `seed` on an object makes every code symbol an entry. `ChannelModes`,
  `SH_Speed` and `SH_Len` are data. Their bogus `CODE` range in `okplay1` and
  `okplay2` was removed by hand.

- Seeding was tried on `DeltaMusic2.0`, `SIDMon2.0`, `Laxity` and
  `TFMX-7V-TFHD`.
- `-preproc` misses code reached by jump tables or pointers. Example:
  `TFMX-7V-TFHD` keeps `4e75` (`rts`) inside data at `$060c`. Add `CODE` ranges
  by hand.
- IRA 2.11 refuses `-preproc` over an existing `.cnf`. So `seed` runs once per
  tag entry and merges the areas.
- Many binary-only players are 1–3 kB. Some may be wrappers (guess). Check each
  one when its config is made.
