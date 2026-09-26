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


if __name__ == "__main__":
    unittest.main()
