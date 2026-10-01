"""Self-tests for the Markdown checkers in tools/.

Run: python3 -m unittest discover -s tests
"""

import ast
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def run(tool, *files):
    """Run a checker; return (exit code, set of reported rule names)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / tool), *map(str, files)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    rules = {line.split(": ")[1] for line in proc.stdout.splitlines() if ": " in line}
    return proc.returncode, rules, proc.stdout


class Help(unittest.TestCase):
    TOOLS = sorted(
        p.name
        for p in (ROOT / "tools").glob("*.py")
        if "def main(" in p.read_text(encoding="utf-8")
    )

    def test_help_prints_the_docstring(self):
        for tool in self.TOOLS:
            with self.subTest(tool=tool):
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / tool), "--help"],
                    capture_output=True,
                    text=True,
                    cwd=ROOT,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                doc = ast.get_docstring(ast.parse((ROOT / "tools" / tool).read_text()))
                self.assertEqual(proc.stdout.strip(), (doc or "").strip())

    def test_tools_are_executable(self):
        for tool in self.TOOLS:
            with self.subTest(tool=tool):
                path = ROOT / "tools" / tool
                self.assertTrue(os.access(path, os.X_OK))
                self.assertTrue(path.read_text().startswith("#!/usr/bin/env python3\n"))

    def test_a_bad_option_shows_the_usage(self):
        for tool in self.TOOLS:
            with self.subTest(tool=tool):
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / tool), "--no-such-option"],
                    capture_output=True,
                    text=True,
                    cwd=ROOT,
                )
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertIn("Usage:", proc.stderr)


class GoodCard(unittest.TestCase):
    def test_all_checkers_accept_a_good_card(self):
        for card in ("MED.md", "Jochen_Hippel_ST.md"):
            good = FIXTURES / "good" / card
            for tool in ("cogload.py", "links.py", "cards.py"):
                with self.subTest(card=card, tool=tool):
                    code, _, out = run(tool, good)
                    self.assertEqual(code, 0, out)


class Cogload(unittest.TestCase):
    def test_reports_each_rule(self):
        code, rules, out = run("cogload.py", FIXTURES / "cogload_bad.md")
        self.assertEqual(code, 1)
        expected = {
            "sentence-words",
            "list-items",
            "list-depth",
            "cell-words",
            "acronym",
            "avoid",
        }
        self.assertTrue(expected <= rules, out)
        self.assertEqual(out.count("`sequence`: use"), 1, out)

    def test_tables_can_skip_the_file_limit(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import cogload

        path = FIXTURES / "cogload_tables.md"
        saved = cogload.PROFILES
        try:
            for count, expected in ((True, 1), (False, 0)):
                limits = {"file_words": 10, "count_tables": count}
                cogload.PROFILES = [("tests/fixtures/", limits)]
                errors = cogload.check(path, cogload.glossary.terms())
                found = [e for e in errors if "file-words" in e]
                self.assertEqual(len(found), expected, errors)
        finally:
            cogload.PROFILES = saved


class Numbered(unittest.TestCase):
    """Numbers that stand in for names; see tools/numbered.py."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import numbered

        self.numbered = numbered
        self.consts = {0x80: ["HOLD"], 0x32: ["SAMPLE_DATA"], 0xE8: ["SIZE"]}

    def found(self, text):
        return [d for _, d in self.numbered.find(text, self.consts)]

    def test_rejects_a_command_by_number(self):
        for text in ("command 4 slides", "Effects 2 and 3", "opcode $e0"):
            with self.subTest(text=text):
                self.assertEqual(len(self.found(text)), 1)

    def test_rejects_a_hex_number_equal_to_a_constant(self):
        self.assertEqual(self.found("rows marked $80 hold"), ["`$80` is HOLD"])
        self.assertEqual(self.found("if 0x80 is set"), ["`0x80` is HOLD"])
        self.assertEqual(self.found("$81 is free"), [])

    def test_allows_offsets(self):
        for text in ("the wave plays from +$32", "`$e8` bytes", "$e8 bytes each"):
            with self.subTest(text=text):
                self.assertEqual(self.found(text), [])

    def test_passes_a_wrong_name_with_the_right_value(self):
        self.assertEqual(self.found("GAME_LOOP ends it"), [])

    def test_reads_constants_of_a_spec(self):
        code = "A, B = 0x80, 1 << 4\nC = A + 1\nD, E = range(2, 4)\nx = 5\n"
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            spec = Path(tmp) / "spec.py"
            spec.write_text(code, encoding="utf-8")
            consts = self.numbered.constants(spec)
        self.assertEqual(
            consts, {0x80: ["A"], 16: ["B"], 0x81: ["C"], 2: ["D"], 3: ["E"]}
        )

    def test_finds_layout_lines(self):
        banner = "Record, 8 bytes:\n  $00 flag   $02 wave\n  $04 length\n"
        self.assertEqual(
            self.numbered.layout(banner), {"  $00 flag   $02 wave", "  $04 length"}
        )
        self.assertEqual(self.numbered.layout("Text.\n$80 is a rest."), set())
        self.assertEqual(self.numbered.layout("4 list, $16 pos"), {"4 list, $16 pos"})
        self.assertEqual(self.numbered.layout("$80 is a rest, $81 is not"), set())

    def test_specs_allow_definitions_and_leading_hex(self):
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location(
            "specs_tool", ROOT / "tools/specs.py"
        )
        specs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(specs)
        code = "HOLD = 0x80  # $80 in a row\n"
        code += "TABLE = (\n    HOLD,  # $80\n)\n"
        code += "class Voice:\n    note: int = 0  # $80: the note\n"
        code += "    pos: int = 0  # -$80\n"
        code += '    """Hold with $80; command 4 slides."""\n'
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            path = Path(tmp) / "med.py"
            path.write_text(code, encoding="utf-8")
            found = [(n, d) for n, rule, d in specs.check_prose(path, "MED")]
        self.assertEqual(
            found,
            [
                (8, "`$80` is HOLD"),
                (8, "`command 4`: name it by its constant or handler"),
            ],
        )

    def test_annotations_allow_layout_banners(self):
        import annot

        spec = {
            "comments": {3: "$80: hold"},
            "banners": {5: "Record:\n  $00 flag\n  $80 hold\n", 9: "Command 4."},
        }
        self.assertEqual(
            list(annot.check_numbers(spec, self.consts)),
            [
                "comments: line 3: `$80` is HOLD",
                "banners: line 9: `Command 4`: name it by its constant or handler",
            ],
        )
        self.assertEqual(annot.player_of(Path("MaxTrax-shared.yaml")), "MaxTrax")
        self.assertEqual(annot.player_of(Path("TFMX-Pro.yaml")), "TFMX-Pro")

    def test_cards_check_code_spans(self):
        import cogload

        self.assertIn(0x80, cogload.card_constants("players/MED.md"))
        self.assertIsNone(cogload.card_constants("docs/card-template.md"))
        saved = cogload.card_constants
        try:
            cogload.card_constants = lambda rel: self.consts
            errors = cogload.check(FIXTURES / "numbered_card.md", set())
        finally:
            cogload.card_constants = saved
        found = [e.split(": ", 1)[1] for e in errors if ": number: " in e]
        self.assertEqual(
            found,
            [
                "number: `$80` is HOLD",
                "number: `command 4`: name it by its constant or handler",
            ],
        )


class Links(unittest.TestCase):
    def test_reports_each_rule(self):
        code, rules, out = run("links.py", FIXTURES / "links_bad.md")
        self.assertEqual(code, 1)
        self.assertEqual({"link", "cite", "path"}, rules, out)
        self.assertIn("docs/nope.md does not exist", out)
        self.assertIn("`src/Mugician II_v8.asm:99999` names a line", out)
        self.assertIn("src/nope.asm not found", out)
        self.assertIn("Mugician II_v8.asm has no label NoSuchLabel", out)
        self.assertIn("README.md#L3 names a line", out)
        self.assertIn("replayer.c#L10-L20 names a line", out)
        self.assertIn("sample.cnf has no label NoSuchLabel", out)
        self.assertIn("none.cnf does not exist", out)
        self.assertIn("good.yaml has no label next", out)

    def test_checks_labels_against_the_spec(self):
        code, _, out = run("links.py", FIXTURES / "links_spec.md")
        self.assertEqual(code, 1)
        self.assertIn("GetBlockAddr is not a function or class in specs/med.py", out)
        self.assertIn("paula.py has no label NoSuchClass", out)
        self.assertNotIn("SynthTick", out)
        self.assertNotIn("Voice", out)

    def test_accepts_label_citations(self):
        code, _, out = run("links.py", FIXTURES / "good" / "labels.md")
        self.assertEqual(code, 0, out)


class Annot(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import annot

        self.annot = annot
        self.dir = FIXTURES / "annot"

    def test_renders_labels_and_comments(self):
        self.assertEqual(self.annot.process(self.dir / "good.yaml", write=False), [])
        spec = self.annot.load(self.dir / "good.yaml")
        lines = (self.dir / "sample.s").read_bytes().decode("latin-1").split("\n")
        out = self.annot.render(spec, lines)
        self.assertEqual(out[1:3], ["Call:", " bsr\tNextNote\t; appel\xe9"])
        self.assertEqual(out[5:7], [";; NextNote: read one note.", "NextNote:"])
        self.assertEqual(
            out[7], " move.w\t#NextNote-Play,d0\t;; distance between the labels"
        )
        self.assertEqual(
            self.annot.listing_labels(self.dir / "good.yaml"),
            {"Play", "Call", "NextNote", "Tune"},
        )

    def test_reports_bad_annotations(self):
        out = "\n".join(self.annot.process(self.dir / "bad.yaml", write=False))
        for text in (
            "unknown field `colour`",
            "sha1 is 0000",
            "label nope is not in the source",
            "NextNote is the new name of several labels",
            "label null is not in the source",
            "rts already occurs",
            "line 99 is not in the source",
            "refs: tests/fixtures/annot/none.txt does not exist",
            "types: lower is not a CamelCase name",
            "Ghost: nowhere_word is in neither the source nor refs",
            "types: NextNote is also a label",
        ):
            self.assertIn(text, out)

    def test_accepts_types_for_a_config(self):
        self.assertEqual(self.annot.process(self.dir / "config.yaml", write=False), [])
        self.assertEqual(
            self.annot.listing_labels(self.dir / "config.yaml"),
            {"DTP_Interrupt", "NextNote", "Voice"},
        )

    def test_reports_bad_types_for_a_config(self):
        out = "\n".join(self.annot.process(self.dir / "config_bad.yaml", write=False))
        for text in (
            "`labels` needs a source",
            "`sha1` needs a source",
            "types: NextNote is also a label",
            "Ghost: nowhere_word is in neither the source nor refs",
        ):
            self.assertIn(text, out)

    def test_cites_resource_strings(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            path = Path(tmp) / "Resources.resx"
            path.write_text('<data name="IDS_A" xml:space="preserve">\n')
            self.assertEqual(self.annot.cited_labels(path), {"IDS_A"})

    def test_rejects_duplicate_keys(self):
        out = "\n".join(self.annot.process(self.dir / "duplicate.yaml", write=False))
        self.assertIn("duplicate key 2", out)

    def test_reports_bad_layouts(self):
        spec = {
            "types": {"Voice": ["x"]},
            "layouts": {
                "Voice": {
                    "size": 4,
                    "fields": {
                        "period": [0, "w"],
                        "volume": [1, "b"],
                        "start": [3, "w"],
                        "Bad": [2, "b"],
                    },
                },
                "Ghost": {"size": 4, "fields": {}},
            },
        }
        out = "\n".join(self.annot.check_layouts(spec))
        for text in (
            "Voice: volume overlaps period",
            "Voice: start lies outside 4 bytes",
            "Voice: start is a w at an odd offset",
            "Voice: Bad is not an attribute name",
            "layouts: Ghost is not in types",
        ):
            self.assertIn(text, out)

    def test_accepts_the_repo_files(self):
        self.assertEqual(self.annot.main(["--check"]), 0)


class Cards(unittest.TestCase):
    def test_reports_each_rule(self):
        code, rules, out = run("cards.py", FIXTURES / "cards_bad.md")
        self.assertEqual(code, 1)
        expected = {"front-matter", "player", "section", "context", "composer"}
        expected |= {"cell", "label", "code", "unique"}
        self.assertEqual(expected, rules, out)
        for text in (
            "unknown `control`",
            "unknown `## Extra`",
            "order should be ['Context'",
            "out of date",
            "aspects must be ['Notation'",
            "no code on a card",
            "one fact per cell",
            "`plr_loop2` is no readable name",
            "must be (manual) or labels",
            "no subheadings",
        ):
            self.assertIn(text, out)

    def test_writes_context(self):
        good = (FIXTURES / "good" / "MED.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            card = Path(tmp) / "MED.md"
            stale = good.replace("Teijo Kinnunen", "Nobody")
            self.assertNotEqual(stale, good)
            card.write_text(stale, encoding="utf-8")
            self.assertEqual(run("cards.py", card)[0], 1)
            run("cards.py", "--write", card)
            self.assertEqual(card.read_text(encoding="utf-8"), good)
            run("cards.py", "--write", card)
            self.assertEqual(card.read_text(encoding="utf-8"), good)

    def test_rejects_a_card_without_a_template(self):
        good = (FIXTURES / "good" / "MED.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            card = Path(tmp) / "MED.md"
            card.write_text(good.replace("template: 2\n", ""), encoding="utf-8")
            code, _, out = run("cards.py", card)
            self.assertEqual(code, 1)
            self.assertIn("`template` must be one of", out)

    def test_accepts_a_delta_card(self):
        delta = FIXTURES / "good" / "Jochen_Hippel_ST.md"
        code, _, out = run("cards.py", delta)
        self.assertEqual(code, 0, out)


class Specs(unittest.TestCase):
    def setUp(self):
        # By path: the name `specs` also names the specs/ package.
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location(
            "specs_tool", ROOT / "tools/specs.py"
        )
        self.specs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.specs)

    def test_accepts_the_repo_specs(self):
        code, _, out = run("specs.py")
        self.assertEqual(code, 0, out)

    def test_reports_names_without_an_anchor(self):
        code = "def SynthTick() -> None: ...\n"
        code += "def NoSuchLabel() -> None: ...\n"
        code += "def helper() -> None: ...\n"
        code += "class Voice: ...\n"
        code += "class Ghost: ...\n"
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            spec = Path(tmp) / "med.py"
            spec.write_text(code, encoding="utf-8")
            found = list(self.specs.check_names(spec, "MED"))
        self.assertEqual(
            [(2, "label"), (5, "type")], [(n, rule) for n, rule, _ in found]
        )

    def test_reports_a_docstring_without_card_or_annotations(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            spec = Path(tmp) / "med.py"
            spec.write_text('"""Card: players/MED.md."""\n', encoding="utf-8")
            found = list(self.specs.check_docstring(spec, "MED"))
        self.assertEqual(
            ["does not name data/annot/MED.yaml"], [d for _, _, d in found]
        )

    def test_reports_old_labels_in_prose(self):
        code = '"""Reads mmd_pline; see PlayRow."""\n'
        code += "row = 0  # a loop over _Wait1line\n"
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            spec = Path(tmp) / "med.py"
            spec.write_text(code, encoding="utf-8")
            found = list(self.specs.check_prose(spec, "MED"))
        self.assertEqual(
            [(1, "mmd_pline"), (2, "_Wait1line")],
            [(n, detail.split()[0]) for n, _, detail in found],
        )

    def test_reports_type_errors_and_unowned_specs(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            (Path(tmp) / "orphan.py").write_text('x: int = "a"\n', encoding="utf-8")
            code, rules, out = run("specs.py", tmp)
        self.assertEqual(code, 1)
        self.assertEqual({"types", "owner"}, rules, out)


class Players(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import players

        self.players = players

    def test_accepts_the_repo_file(self):
        self.assertEqual(self.players.validate(), [])

    def test_reports_a_missing_spec(self):
        out = "\n".join(self.players.validate({"MED": {"spec": "specs/nope.py"}}))
        self.assertIn("spec `specs/nope.py` is not a file under specs/", out)

    def test_reports_bad_skips(self):
        facts = {
            "SIDMon2.0": {"skip": "boring"},
            "MED": {"skip": "protracker"},
            "SIDMon1.0": {"skip": "covered"},
            "Mugician": {"skip": "covered", "covered_by": ["SIDMon1.0"]},
            "Synth": {"skip": "lineage", "family": "Nobody"},
            "TFMX-7V-TFHD": {"skip": "lineage", "distinct": "x"},
        }
        out = "\n".join(self.players.validate(facts))
        for text in (
            "SIDMon2.0: `skip` not in",
            "MED: `skip` but players/ has its card",
            "SIDMon1.0: `skip: covered` and `covered_by` go together",
            "Mugician: covered_by `SIDMon1.0` has no card",
            "Synth: `skip: lineage` needs a family with a head",
            "TFMX-7V-TFHD: `skip` and `distinct` contradict",
        ):
            self.assertIn(text, out)
        good = {"Mugician": {"skip": "covered", "covered_by": ["MugicianII"]}}
        self.assertEqual(self.players.validate(good), [])

    def test_accepts_a_source_only_player(self):
        facts = {"MaxTrax": {"replay": "source", "source": "other/max_trax"}}
        self.assertEqual(self.players.validate(facts), [])

    def test_reports_bad_facts(self):
        out = "\n".join(
            self.players.validate(
                {
                    "NoSuchPlayer": {},
                    "SourceOnly": {"replay": "source", "source": "other/nowhere"},
                    "MED": {"replay": "source", "source": "other/max_trax"},
                    "SoundMon2.2": {
                        "provenance": "rumour",
                        "family": "SoundMon",
                        "after": {
                            "player": "Mugician",
                            "evidence": "vibes",
                            "cite": "data/annot/SoundMon2.2.yaml:758",
                        },
                        "colour": "blue",
                    },
                }
            )
        )
        for text in (
            "NoSuchPlayer: not a binary",
            "`provenance` not in",
            "evidence `vibes`",
            "same family",
            "unknown field `colour`",
            "SoundMon2.2.yaml has no label 758",
            "SourceOnly: `replay: source` needs an existing `source`",
            "MED: `replay: source` is for players without a binary",
        ):
            self.assertIn(text, out)


class Inventory(unittest.TestCase):
    """Known results, so a change to the matching does not go unnoticed."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import inventory

        self.table = inventory.table()

    def test_known_players(self):
        expected = {
            "SonicArranger": ("wanted_team/Sonic_Arranger", "hash", "uade"),
            "RobHubbard": ("wanted_team/RobHubbard", "hash", "module"),
            "SoundMon2.2": ("uade/soundmon", "name", "uade"),
            "FutureComposer1.4": ("defect/fc14", "manual", "uade"),
            "SIDMon2.0": ("ext/c-flod/neoart/flod/sidmon", "manual", "port"),
            "TFMX-Pro": ("wanted_team/TFMX-Pro", "hash", "uade"),
        }
        for player, (source, match, replay) in expected.items():
            with self.subTest(player=player):
                row = self.table[player]
                self.assertEqual(
                    (row["source"], row["match"], row["replay"]),
                    (source, match, replay),
                )


class Disasm(unittest.TestCase):
    """Tag lists and linking; IRA and vasm are not run here."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import disasm

        self.disasm = disasm

    def test_finds_tags_by_address(self):
        found = dict(self.disasm.tags(self.disasm.PLAYERS / "DeltaMusic2.0"))
        self.assertEqual(found["DTP_PlayerName"], 0xB2)
        self.assertEqual(found["DTP_Interrupt"], 0x1B8)

    def test_links_an_object_file(self):
        if not self.disasm.VLINK.exists():
            self.skipTest("vlink missing; run: source ./activate")
        obj = ROOT / "ext" / "oktalyzer" / "original" / "sources" / "okplay2.o"
        exe, labels, entries = self.disasm.load(obj)
        names = dict(labels)
        hs = self.disasm.hunks(exe)
        # `bsr StopAll` at $6: the displacement counts from its own word.
        disp = int.from_bytes(hs[0][1][8:10], "big", signed=True)
        self.assertEqual(8 + disp, names["StopAll"])
        self.assertEqual(hs[1][0], 0x10A4)  # hunks back to back, as IRA loads them
        self.assertIn(names["OK_Play"], entries)  # a code symbol
        self.assertNotIn(names["PBuff"], entries)  # in a BSS hunk

    # bra.w $8; bra.w $a; rts; rts: raw code with a jump table
    RAW = bytes.fromhex("60000006 60000004 4e75 4e75")

    def test_reads_a_jump_table(self):
        self.assertEqual(self.disasm.jump_table(self.RAW), [0x8, 0xA])
        jmp = bytes.fromhex("4efa0006 4efa0004 4e75 4e75")  # jmp (d16,pc)
        self.assertEqual(self.disasm.jump_table(jmp), [0x8, 0xA])

    def test_reads_entry_stubs(self):
        # movem.l d0/a0,-(sp); bsr.w; movem.l (sp)+,d0/a0; rts, then
        # move.l a3,-(sp); bsr.w; move.l (sp)+,a3; rts, then other code
        raw = bytes.fromhex("48e78080 61000010 4cdf0101 4e75")
        raw += bytes.fromhex("2f0b 61000006 265f 4e75 08f90001")
        self.assertEqual(self.disasm.stubs(raw), [0x0, 0xE])
        self.assertEqual(self.disasm.stubs(raw[:0xE]), [])  # one stub

    def test_wraps_raw_code_at_address_0(self):
        if not self.disasm.VASM.exists():
            self.skipTest("vasm missing; run: source ./activate")
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            raw.write_bytes(self.RAW)
            exe, labels, entries = self.disasm.load(raw)
        ((base, body, relocs),) = self.disasm.hunks(exe)
        self.assertEqual((base, body.rstrip(b"\0"), relocs), (0, self.RAW, {}))
        self.assertEqual(labels, [("Jump0", 0x8), ("Jump1", 0xA)])
        self.assertEqual(entries, [0, 0x8, 0xA])

    def test_reads_a_pointer_table(self):
        if not self.disasm.VASM.exists():
            self.skipTest("vasm missing; run: source ./activate")
        raw = bytes.fromhex("4e75 4e75 00000000 00000002")  # two pointers at $4
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "raw"
            path.write_bytes(raw)
            exe = self.disasm.load(path)[0]
        self.assertEqual(self.disasm.pointers(exe, 0x4, 0xC), [0x0, 0x2])

    def test_every_player_has_a_code_tag(self):
        for binary in sorted(self.disasm.PLAYERS.iterdir()):
            if binary.is_file():
                with self.subTest(player=binary.name):
                    names = {n for n, _ in self.disasm.tags(binary)}
                    self.assertTrue(names - self.disasm.DATA_TAGS)


class Timing(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import timing

        self.timing = timing

    def data(self, name="soundmon_22"):
        import yaml

        return yaml.safe_load((ROOT / f"data/timing/{name}.yaml").read_text())

    def test_takes_ranges_and_marks_their_ends(self):
        text = self.timing.excerpt(self.data())
        self.assertIn("\nReadRow:\n", text)
        self.assertIn("\nStartSynthNote:\n illegal\n", text)
        self.assertNotIn("bsr\t\tReadRow", text)
        self.assertNotIn("bpxx", text)
        self.assertNotIn("Section", text)

    def test_reads_addresses(self):
        symbols = {"DmaWait": 0x1000A}
        self.assertEqual(self.timing.address("DmaWait+4", symbols), 0x1000E)
        self.assertEqual(self.timing.address("DmaWait - 2", symbols), 0x10008)
        self.assertEqual(self.timing.address("0x40038", symbols), 0x40038)

    def test_writes_record_fields(self):
        memory = self.timing.records(self.data())
        symbols = {"Voices": 0x10100, "Song": 0x10200}
        self.assertEqual(
            self.timing.write("voice[1].volume 64", symbols, memory),
            (0x10100 + 36 + 2, 1, 64),
        )
        self.assertEqual(
            self.timing.write("instrument[1].length 1000", symbols, memory),
            (0x40038, 2, 1000),
        )
        self.assertEqual(
            self.timing.write("Song l 0x40000", symbols, memory), (0x10200, 4, 0x40000)
        )

    def test_spec_constants_match_the_measurements(self):
        import numbered

        for path in sorted((ROOT / "data/timing").glob("*.yaml")):
            data = self.data(path.stem)
            consts = numbered.constants(ROOT / "specs" / f"{path.stem}.py")
            for constant, (case, load) in data["measure"].get("spec", {}).items():
                with self.subTest(file=path.name, constant=constant):
                    want = data["cases"][case]["expect"][load][constant]
                    self.assertIn(constant, consts.get(want, []))

    def test_matches_the_recorded_times(self):
        if not self.timing.DRIVER.exists():
            self.skipTest("amiga-timing is not built; run: source ./activate")
        code, _, out = run("timing.py", "check", "soundmon_22")
        self.assertEqual(code, 0, out)


class Reviews(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import annot
        import reviews

        self.reviews = reviews
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = root = Path(tmp.name)
        files = {
            "players/Fred.md": "---\nplayer: Fred\n---\n# Fred\n",
            "specs/fred.py": "",
            "docs/control-dimensions.md": "",
            "docs/card-template.md": "",
            "docs/paula-techniques.md": "",
            "data/glossary.yaml": "",
            "AGENTS.md": "",
            "data/annot/Fred.yaml": "",
        }
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        for module, name, value in (
            (reviews, "ROOT", root),
            (reviews, "REVIEWS", root / "data/reviews"),
            (reviews, "CARDS", root / "players"),
            (annot, "ANNOT", root / "data/annot"),
        ):
            self.addCleanup(setattr, module, name, getattr(module, name))
            setattr(module, name, value)
        (root / "none.yaml").write_text("[]\n")
        with contextlib.redirect_stdout(io.StringIO()):
            for review in ("coverage", "writing"):
                reviews.record("Fred", review, root / "none.yaml")

    def statuses(self):
        reviews = self.reviews
        data = reviews.load("Fred")
        card = self.root / "players/Fred.md"
        return {r: reviews.status("Fred", r, card, data.get(r)) for r in reviews.FIELDS}

    def test_recorded_reviews_are_ok(self):
        self.assertEqual(self.statuses(), {"coverage": "ok", "writing": "ok"})

    def test_a_spec_change_makes_both_stale(self):
        (self.root / "specs/fred.py").write_text("x = 1\n")
        stale = "stale: specs/fred.py"
        self.assertEqual(self.statuses(), {"coverage": stale, "writing": stale})

    def test_a_checklist_change_makes_only_coverage_stale(self):
        (self.root / "docs/control-dimensions.md").write_text("new\n")
        got = self.statuses()
        self.assertEqual(got["coverage"], "stale: docs/control-dimensions.md")
        self.assertEqual(got["writing"], "ok")

    def test_a_new_listing_config_makes_coverage_stale(self):
        (self.root / "data/disasm").mkdir()
        (self.root / "data/disasm/Fred.cnf").write_text("")
        self.assertEqual(self.statuses()["coverage"], "stale: data/disasm/Fred.cnf")

    def test_a_review_not_run_is_missing(self):
        (self.root / "data/reviews/Fred.yaml").write_text("coverage: null\n")
        self.assertEqual(self.statuses()["writing"], "missing")

    def test_rejects_findings_without_their_fields(self):
        data = self.reviews.load("Fred")
        data["writing"]["open"] = [{"section": "Key ideas", "quote": "x"}]
        data["coverage"]["open"] = [
            {"dimension": "gate", "finding": "", "evidence": ":NoteOn"}
        ]
        problems = self.reviews.validate("Fred", data)
        self.assertEqual(len(problems), 2, problems)


class Print(unittest.TestCase):
    CARD = """---
player: Fred
---

# Fred

One sentence that is long enough to wrap past the eighty columns of a page, twice over.

## Context

| Fact   | Value  |
| ------ | ------ |
| Player | `Fred` |

## Key ideas

- A bullet with a code span, `NoteOn`, a [link to a page](x.md), and words enough to wrap onto a second line.
  - A nested bullet.

| Aspect   | Answer                                                                   | Source      |
| -------- | ------------------------------------------------------------------------ | ----------- |
| Notation | A cell long enough that the table must shrink it to fit the page's eighty-eight columns. | `:ReadStream` |
"""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import print as printer

        self.printer = printer
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.card = Path(tmp.name) / "Fred.md"
        self.card.write_text(self.CARD)
        self.lines = [line for line, _ in printer.render(self.card)]

    def test_lines_fit_the_columns(self):
        width = self.printer.visible
        self.assertTrue(
            all(width(line) <= self.printer.COLUMNS for line in self.lines), self.lines
        )

    def test_leaves_out_front_matter_and_context(self):
        text = "\n".join(self.lines)
        self.assertNotIn("player:", text)
        self.assertNotIn("Context", text)
        self.assertEqual(self.lines[0], "Fred")

    def test_bullets_hang_and_nest(self):
        start = next(i for i, line in enumerate(self.lines) if line.startswith("- A"))
        self.assertRegex(self.lines[start + 1], r"^  [a-z]")
        self.assertIn("  - A nested bullet.", self.lines)

    def test_a_link_gets_an_arrow_and_stays_on_one_line(self):
        marked = [line for line in self.lines if self.printer.OPEN in line]
        self.assertEqual(len(marked), 1, self.lines)
        self.assertIn("link to a page\u2197", self.printer.plain(marked[0]))

    def test_code_spans_lose_their_backticks(self):
        self.assertIn("NoteOn", "\n".join(self.lines))
        self.assertNotIn("`", "\n".join(self.lines))

    def test_a_wide_table_wraps_its_cells(self):
        rows = [line for line in self.lines if line.startswith(("Aspect", "Notation"))]
        self.assertEqual(len(rows), 2)
        row = self.printer.plain(self.lines[self.lines.index(rows[1])])
        self.assertIn("  ReadStream", row)
        self.assertNotIn(":ReadStream", row)

    def test_pages_count_whole_pages(self):
        lines = self.printer.LINES
        self.assertEqual(self.printer.pages([("", False)] * lines * 2), 2)
        self.assertEqual(self.printer.pages([("", False)] * (lines * 2 + 1)), 3)

    def test_pdf_starts_each_card_on_a_new_page(self):
        if not (self.printer.FONTS / "JetBrainsMono-Regular.ttf").is_file():
            self.skipTest("the font is missing; run: source ./activate")
        out = self.card.with_suffix(".pdf")
        self.assertEqual(self.printer.write_pdf([self.card, self.card], out), 2)

    def test_font_matches_the_page_model(self):
        font = self.printer.FONTS / "JetBrainsMono-Regular.ttf"
        if not font.is_file():
            self.skipTest("the font is missing; run: source ./activate")
        from fpdf import FPDF

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.add_font("mono", "", str(font))
        pdf.set_font("mono", size=self.printer.FONT_SIZE)
        advance = pdf.get_string_width("x")
        width = advance * self.printer.COLUMNS
        self.assertLessEqual(width, self.printer.PAGE_WIDTH)
        self.assertGreater(width + advance, self.printer.PAGE_WIDTH)


if __name__ == "__main__":
    unittest.main()
