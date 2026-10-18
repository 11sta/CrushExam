#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Masking self-check: preview what CrushExam's PII masking would do.

Reads one text file (or stdin) and prints the masked preview plus per-kind hit
counts. The exact same `coach.pii.mask_pii` runs automatically when materials
enter a workspace (input side) and again at the export boundary (cheatsheet,
capability view). This standalone entry point exists so the masking behaviour
can be verified without importing any course materials.

Usage:
    python scripts/mask_check.py <file>       # preview masking for one file
    type notes.txt | python scripts/mask_check.py -    # via stdin (Windows)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coach.pii import mask_pii  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="text file to preview, or - for stdin")
    args = parser.parse_args()

    if args.path == "-":
        text = sys.stdin.read()
    else:
        path = Path(args.path)
        if not path.is_file():
            print("not a file: %s" % path)
            return 2
        text = path.read_text(encoding="utf-8", errors="replace")

    masked, counts = mask_pii(text)
    print(masked)
    print()
    if counts:
        print("masked hits: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
    else:
        print("no high-confidence PII patterns found")
    print("Mitigation only, not full de-identification; see SKILL.md section 7.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
