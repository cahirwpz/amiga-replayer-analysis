# Open work

The hand-off between sessions. What belongs here: see
[`AGENTS.md`](AGENTS.md#sessions).

## Pilot

Twelve cards test the card template before the full survey.

Selection rules:

- Formats that did not prevail on the demoscene. No `ProTracker`-like players.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- `replay` must be `uade` or `port` in the output of `tools/inventory.py`.

### Cards: synthesis

- [ ] `TFMX-Pro`: macro language with conditions and calls
- [ ] `MED`: synth volume and waveform command lists
- [ ] `SonicArranger`: synth instruments
- [ ] `SonixMusicDriver`: note score, synth with filter bank
- [ ] `SynthDream`: synth format, not yet read

### Cards: port, emulation, tricks

- [ ] `AbyssHighestExperience`: synthesis, read from `ext/ahx2play`
- [ ] `Jochen_Hippel_ST`: Atari ST sound chip emulated on Paula

### Rejected

| Player                                                           | Reason                              |
| ---------------------------------------------------------------- | ----------------------------------- |
| `RobHubbard`, `BenDaglish-SID`, `JankoMrsicFlogel`, `Special-FX` | Replay code is in the module        |
| `PreTracker`                                                     | Replay code is a prebuilt binary    |
| `Pokeynoise`, `ADPCM_mono`                                       | Too primitive or already well known |
| `Mugician`                                                       | Covered by `MugicianII`             |
| `JochenHippel-7V`                                                | Mixing is covered by `MugicianII`   |
| `PTK-Prowiz`                                                     | `ProTracker`-like                   |

## Reading notes

Findings so far, for the cards above. Paths are relative to
`ext/uade/amigasrc/players`. Delete a section when its card exists.

### `TFMX-Pro`: `wanted_team/TFMX-Pro/src/TFMX Pro_v5.asm`

- Each position lists 8 tracks. Special positions stop, loop, set speed or fade.
  `data/annot/TFMX-Pro.yaml:newtrack`
- Tracks are not voices: a note names a macro and a channel. `:TrackNote`
- Pattern opcodes: end, loop, jump, wait, call, return, key-up. `:PatternOpcode`
- Macro opcode table has 52 entries. `:jumptable1`
- Conditions: split by note or volume `:msplitk`, test memory bytes
  `:mbytecheck`.
- Macros start notes and key-ups on other channels. `:mplaynote`
- The `ims` opcodes set up runtime sample synthesis. `:mimssstart`

### `MED`: `uade/med/common/proplayer.a`

- Original source, not a disassembly.
- Synth sounds run two lists per voice: volume and waveform.
  `ext/uade/amigasrc/players/uade/med/common/proplayer.a:synth_start2`
- Volume opcodes: `:synth_vtbl`. Waveform opcodes: `:synth_wfctbl`.
- Jumps between the two lists are expected. Not yet seen in code.
- Synth notes start at `:handleSynthnote`. Notes can also go out as MIDI.
  `:handleMIDInote`

### `SonixMusicDriver`: `wanted_team/SonixMusicDriver/src/Sonix Music Driver_v1.asm`

- Plays `SMUS` note scores, not patterns. Source: its readme.
- Synth sounds allocate a filter bank
  `data/annot/SonixMusicDriver.yaml:AddFilterBank`; setup at `:SetFilter`.
- Synthesis code starts at `:SYNTHTECH`. Not read yet.

### `AbyssHighestExperience`: `ext/ahx2play/replayer.c`

- Not read yet.
- The original 68000 source was never published. The official release ships only
  a binary replayer.
- Sources: [ahx2play](https://github.com/8bitbubsy/ahx2play),
  [AHX tools on scene.org](https://files.scene.org/view/resources/code/utils/winuaedemotoolchain5v3.zip).

### `Jochen_Hippel_ST`

- Its readme says it uses Hippel's Atari ST sound chip emulator. Code not read.

### `SonicArranger`, `SynthDream`

- Not read yet.

## After the pilot

- [ ] Review the cards with the user.
- [ ] Tune limits in `tools/cogload.py` and the card template.
- [ ] Fix the classification axes: control, themes, streams. They live in the
      glossary and the card template.
- [ ] Write the first technique pages in `ideas/`.
- [ ] Add a check that `ideas:` slugs in cards exist.
- [ ] Generate a technique index from the slugs, for the front page.

## Open questions

- [ ] Mugician II: cross-check effect numbers with
      `ext/c-flod/neoart/flod/digitalmugician/DMPlayer.c`.
- [ ] Mugician II: can mixed voices play synth waves?
      `ext/c-flod/neoart/flod/digitalmugician/DMPlayer.c:DMPlayer_process` takes
      mixed voices from a sample pointer:
      `voice->mixPtr = sample->super.pointer` (not verified).
- [ ] Mugician II: card says mixing uses channel 0, `:DMPlayer_initialize` uses
      channel 3: `chan = &self->super.amiga->channels[3]`. Resolve.
- [ ] Inventory: read the five players marked `check`.
- [ ] `RobHubbard` was rejected: UADE keeps its code in modules. Does
      `ext/c-flod/neoart/flod/hubbard/RHPlayer.c` reopen it?

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
