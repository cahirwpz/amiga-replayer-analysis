"""Command lines for the tools in this directory.

  parser(doc)  an argparse parser whose help is the tool's docstring

A tool's usage lives in its module docstring, and only there. argparse
checks the arguments: `--help` prints the docstring as it is, and an error
prints the docstring's Usage lines, then the error, and exits 2.
Subcommands inherit the same help.
"""

# mypy: disallow-untyped-defs

import argparse


class DocParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (self.description or "").strip() + "\n"

    def format_usage(self) -> str:
        """The docstring's paragraph that starts with `Usage:`."""
        doc = self.description or ""
        start = doc.find("Usage:")
        if start < 0:
            return super().format_usage()
        end = doc.find("\n\n", start)
        return doc[start : end if end >= 0 else None].strip() + "\n"


def parser(doc: str | None) -> DocParser:
    return DocParser(description=doc)
