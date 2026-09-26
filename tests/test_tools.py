"""Self-tests for the Markdown checkers in tools/.

Run: python3 -m unittest discover -s tests
"""

import subprocess
import sys
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
        good = FIXTURES / "good" / "MugicianII.md"
        for tool in ("cogload.py", "links.py", "cards.py"):
            with self.subTest(tool=tool):
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
        }
        self.assertTrue(expected <= rules, out)


class Links(unittest.TestCase):
    def test_reports_each_rule(self):
        code, rules, out = run("links.py", FIXTURES / "links_bad.md")
        self.assertEqual(code, 1)
        self.assertEqual({"link", "cite", "related"}, rules, out)
        self.assertIn("99999 beyond", out)
        self.assertIn("src/nope.asm not found", out)
        self.assertIn('#L3 does not start with "MugicianII"', out)
        self.assertIn("sample.cnf has no label NoSuchLabel", out)
        self.assertIn("none.cnf does not exist", out)

    def test_accepts_label_citations(self):
        code, _, out = run("links.py", FIXTURES / "good" / "labels.md")
        self.assertEqual(code, 0, out)


class Cards(unittest.TestCase):
    def test_reports_each_rule(self):
        code, rules, out = run("cards.py", FIXTURES / "cards_bad.md")
        self.assertEqual(code, 1)
        self.assertEqual({"front-matter", "player", "section", "streams"}, rules, out)
        for text in (
            "`control: bytecode`",
            "`themes` must be",
            "omit `track`",
            "missing `## State`",
            "order should be",
            "control `teleport`",
            "rate `sometimes`",
            "file name should be",
        ):
            self.assertIn(text, out)


class Disasm(unittest.TestCase):
    """Tag-list parsing only; IRA itself is not run here."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import disasm

        self.disasm = disasm

    def test_finds_tags_by_address(self):
        found = dict(self.disasm.tags(self.disasm.PLAYERS / "DeltaMusic2.0"))
        self.assertEqual(found["DTP_PlayerName"], 0xB2)
        self.assertEqual(found["DTP_Interrupt"], 0x1B8)

    def test_every_player_has_a_code_tag(self):
        for binary in sorted(self.disasm.PLAYERS.iterdir()):
            if binary.is_file():
                with self.subTest(player=binary.name):
                    names = {n for n, _ in self.disasm.tags(binary)}
                    self.assertTrue(names - self.disasm.DATA_TAGS)


if __name__ == "__main__":
    unittest.main()
