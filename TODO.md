# Open work

The hand-off between sessions. What belongs here: see
[`AGENTS.md`](AGENTS.md#sessions).

## Pilot

Twelve cards test the card template before the full survey.

Selection rules:

- Formats that did not prevail on the demoscene. No `ProTracker`-like players.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- `replay` must be `uade` or `port` in [the inventory](docs/inventory.md).

### Cards: synthesis

- [ ] [`SoundMon2.2`](data/inventory.csv?plain=1#L142 "SoundMon2.2"): four table
      walkers per voice
- [ ] [`TFMX-Pro`](data/inventory.csv?plain=1#L161 "TFMX-Pro"): macro language
      with conditions and calls
- [ ] [`MED`](data/inventory.csv?plain=1#L84 "MED"): synth volume and waveform
      command lists
- [ ] [`SonicArranger`](data/inventory.csv?plain=1#L134 "SonicArranger"): synth
      instruments
- [ ] [`SonixMusicDriver`](data/inventory.csv?plain=1#L135 "SonixMusicDriver"):
      note score, synth with filter bank
- [ ] [`SynthDream`](data/inventory.csv?plain=1#L154 "SynthDream"): synth
      format, not yet read

### Cards: port, emulation, tricks

- [ ] [`AbyssHighestExperience`](data/inventory.csv?plain=1#L2 "AbyssHighestExperience"):
      synthesis, read from `ext/ahx2play`
- [ ] [`Jochen_Hippel_ST`](data/inventory.csv?plain=1#L65 "Jochen_Hippel_ST"):
      Atari ST sound chip emulated on Paula
- [ ] [`SoundPlayer`](data/inventory.csv?plain=1#L143 "SoundPlayer"): attach
      modes, confirmed in code
- [ ] [`DigitalSonixChrome`](data/inventory.csv?plain=1#L34 "DigitalSonixChrome"):
      audio interrupts count loop repeats

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

### `SoundMon2.2`: `uade/soundmon/Soundmon2.2.s`

- Four table walkers per voice: volume, vibrato, wave offset, modulation.
  `:573-880`
- Each has a table, delay, speed, length and mode: off, once or loop.
- Voice state layout is commented at `:895-903`.
- Not read yet: note handling and wave effects.

### `TFMX-Pro`: `wanted_team/TFMX-Pro/src/TFMX Pro_v5.asm`

- Song steps list 8 tracks. Special steps stop, loop, set speed or fade.
  `:2362-2388`
- Tracks are not voices: a note names a macro and a channel. `:2189-2199`
- Pattern opcodes: end, loop, jump, wait, call, return, key-up. `:2211-2226`
- Macro opcode table has 52 entries. `:2607`
- Conditions: split by note or volume `:2932`, test memory bytes `:2834`.
- Macros start notes and key-ups on other channels. `:3036-3048`
- The `ims` opcodes set up runtime sample synthesis. `:3232-3300`

### `MED`: `uade/med/common/proplayer.a`

- Original source, not a disassembly.
- Synth sounds run two lists per voice: volume and waveform. `:603-779`
- Volume opcodes from `:649`, waveform opcodes from `:736`.
- Jumps between the two lists are expected. Not yet seen in code.
- Synth notes start at `:560`. Notes can also go out as MIDI. `:517`

### `SonixMusicDriver`: `wanted_team/SonixMusicDriver/src/Sonix Music Driver_v1.asm`

- Plays `SMUS` note scores, not patterns. Source: its readme.
- Synth sounds allocate a filter bank `:651`; setup at `:2810`.
- Synthesis code starts at `:5175`. Not read yet.

### `SoundPlayer`: `wanted_team/SoundPlayer/src/SoundPlayer_v1.asm`

- Sets and clears attach bits for channels 0–2. `:1359-1392`
- Rest not read.

### `DigitalSonixChrome`: `wanted_team/DigitalSonixChrome/src/Digital Sonix & Chrome_v1.asm`

- One audio interrupt handler per channel. `:497`
- The handler counts loop repeats, then loads the next buffer. `:1305-1343`

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
- [ ] Fix the classification axes in `docs/method.md`.
- [ ] Write the first technique pages in `ideas/`.
- [ ] Add a check that `ideas:` slugs in cards exist.

## Open questions

- [ ] Mugician II: cross-check effect numbers with
      `ext/c-flod/neoart/flod/digitalmugician/DMPlayer.c`.
- [ ] Mugician II: can mixed voices play synth waves? `DMPlayer.c:136` takes
      mixed voices from a sample pointer (not verified).
- [ ] Mugician II: card says mixing uses channel 0, `DMPlayer.c:612` uses
      channel 3. Resolve.
- [ ] Inventory: read the five players marked `check`.

## Later

- [ ] Full survey of the remaining players with readable source.
- [ ] Compare code for the `name` rows in `docs/lineage.md`.
- [ ] Tag `ProTracker`-like players in the inventory.
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
