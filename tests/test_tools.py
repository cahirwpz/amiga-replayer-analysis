"""Self-tests for the Markdown checkers in tools/.

Run: python3 -m unittest discover -s tests
"""

import importlib.util
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


class GoodCard(unittest.TestCase):
    def test_all_checkers_accept_a_good_card(self):
        for card in ("MugicianII.md", "MED.md"):
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
            "types: Empty needs a list of words",
        ):
            self.assertIn(text, out)

    def test_rejects_duplicate_keys(self):
        out = "\n".join(self.annot.process(self.dir / "duplicate.yaml", write=False))
        self.assertIn("duplicate key 2", out)

    def test_accepts_the_repo_files(self):
        self.assertEqual(self.annot.main(["--check"]), 0)


class Cards(unittest.TestCase):
    def test_reports_each_rule(self):
        code, rules, out = run("cards.py", FIXTURES / "cards_bad.md")
        self.assertEqual(code, 1)
        expected = {"front-matter", "player", "section", "streams", "base"}
        expected |= {"generators", "outputs", "interactions", "sequencer"}
        self.assertEqual(expected, rules, out)
        for text in (
            "`control` must map",
            "`themes` must be",
            "omit `track`",
            "missing `## State`",
            "order should be",
            "control `teleport`",
            "rate `sometimes`",
            "file name should be",
            "name `Sequence` not in the glossary",
            "unknown `evidence`",
            "role `conductor`",
            "scope `galaxy`",
            "rate `often`",
            "set by `Ghost`",
            "note-on `maybe`",
            "output `Colour`",
            "writer `Track` must be",
            "writer `Nobody` is not on the card",
            "mode `twist`",
            "`nowhere` is not on the card",
            "aspects must be",
            "time `grid`",
            "routing `magic`",
            "`Nowhere` is no other card",
        ):
            self.assertIn(text, out)

    def test_reports_each_template_2_rule(self):
        code, rules, out = run("cards.py", FIXTURES / "cards_bad_v2.md")
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

    def test_every_player_has_a_code_tag(self):
        for binary in sorted(self.disasm.PLAYERS.iterdir()):
            if binary.is_file():
                with self.subTest(player=binary.name):
                    names = {n for n, _ in self.disasm.tags(binary)}
                    self.assertTrue(names - self.disasm.DATA_TAGS)


if __name__ == "__main__":
    unittest.main()
