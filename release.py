#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CrushExam TeleAgent skill packager (v1.9 standard layout).

Produces a ZIP with SKILL.md at the root (no wrapping directory),
matching the TeleAgent skill standard layout:
    SKILL.md / scripts / references / assets / tests

The repo keeps extra dev-only items (samples/, validation/, agents/,
release.py, root README.md for the GitHub landing page); none of
them enter the ZIP.

Usage:
    python release.py              # -> crushexam-teleagent-v<version>.zip in cwd
    python release.py --check      # verify structure + size only
    python release.py --out X.zip  # custom output path
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

ROOT = os.path.dirname(os.path.abspath(__file__))

# Files/dirs to include in the release ZIP (v1.9 standard layout)
INCLUDE_FILES = [
    "SKILL.md",
]
INCLUDE_DIRS = [
    "scripts",      # coach.py entry, coach/ package, validators, MANIFEST.sha256
    "references",   # support docs (README/CHANGELOG/LICENSE live here since v1.9)
    "assets",       # grading-policy.json + workbench.html (offline one-question UI)
    "tests",        # standard test package (has __init__.py, self-contained)
]

# Excluded patterns (relative paths starting with these are skipped)
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "samples", ".git",
                "figures", "validation", "CrushExam_TeleAgent"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".tmp", ".log", ".egg-info", ".zip"}

# Where the checksum manifest lives in the v1.9 layout
MANIFEST_REL = "scripts/MANIFEST.sha256"


def read_version():
    """Read metadata.version from SKILL.md (e.g. "1.9.0")."""
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        for line in fh:
            m = re.search(r'version:\s*"([^"]+)"', line)
            if m:
                return m.group(1)
            if not line.strip():
                break
    return "unknown"


def should_exclude(rel_path):
    parts = rel_path.replace("\\", "/").split("/")
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
    _, ext = os.path.splitext(rel_path)
    if ext in EXCLUDE_EXTS:
        return True
    return False


def collect_files():
    """Collect all files to include in the ZIP."""
    files = []
    # Single files
    for f in INCLUDE_FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            files.append((p, f))
        else:
            print("WARNING: missing %s" % f, file=sys.stderr)
    # Directories (recurse, exclude pycache etc.)
    for d in INCLUDE_DIRS:
        dir_path = os.path.join(ROOT, d)
        if not os.path.isdir(dir_path):
            print("WARNING: missing dir %s" % d, file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(dir_path):
            # Prune excluded dirs in-place
            dirnames[:] = [dn for dn in dirnames if dn not in EXCLUDE_DIRS]
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                if should_exclude(rel):
                    continue
                _, ext = os.path.splitext(fn)
                if ext in EXCLUDE_EXTS:
                    continue
                files.append((full, rel))
    return files


def build_zip(out_path):
    files = collect_files()
    # Verify SKILL.md is at root
    has_skill = any(rel == "SKILL.md" for _, rel in files)
    if not has_skill:
        print("ERROR: SKILL.md not found — cannot build ZIP", file=sys.stderr)
        return 1
    # Auto-refresh scripts/MANIFEST.sha256 so it always matches the packaged
    # content (previous hash entries go stale whenever files change).
    manifest_path = os.path.join(ROOT, *MANIFEST_REL.split("/"))
    lines = []
    for full, rel in sorted(files, key=lambda x: x[1]):
        if rel == MANIFEST_REL:
            continue
        h = _sha256(full)
        lines.append("%s  %s" % (h, rel))
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    files = collect_files()  # re-collect: MANIFEST now exists
    files = [f for f in files if f[1] != MANIFEST_REL] + \
            [(manifest_path, MANIFEST_REL)]
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, rel in sorted(files, key=lambda x: x[1]):
            zf.write(full, rel)
            print("  + %s" % rel)
    size = os.path.getsize(out_path)
    size_mb = size / (1024 * 1024)
    print("\nZIP: %s (%d files, %.2f MB)" % (out_path, len(files), size_mb))
    if size_mb > 10:
        print("WARNING: ZIP is %.2f MB — exceeds 10 MB limit!" % size_mb, file=sys.stderr)
        return 1
    # Verify: list contents
    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()
    # Check SKILL.md is at root (no directory prefix)
    skill_ok = "SKILL.md" in names
    print("SKILL.md at root: %s" % ("OK" if skill_ok else "FAIL"))
    print("MANIFEST in ZIP: %s" % ("OK" if MANIFEST_REL in names else "FAIL"))
    return 0 if skill_ok and MANIFEST_REL in names else 1


def check_only():
    files = collect_files()
    has_skill = any(rel == "SKILL.md" for _, rel in files)
    total_size = sum(os.path.getsize(f) for f, _ in files)
    size_mb = total_size / (1024 * 1024)
    print("Files to include: %d" % len(files))
    print("Total uncompressed: %.2f MB" % size_mb)
    print("SKILL.md at root: %s" % ("OK" if has_skill else "FAIL"))
    if size_mb > 10:
        print("WARNING: uncompressed size %.2f MB — ZIP may exceed 10 MB" % size_mb)
    for _, rel in sorted(files, key=lambda x: x[1]):
        print("  %s" % rel)
    return 0 if has_skill else 1


def main(argv=None):
    p = argparse.ArgumentParser(description="CrushExam TeleAgent skill packager")
    p.add_argument("--out", default=None, help="output ZIP path (default: crushexam-teleagent-v<version>.zip)")
    p.add_argument("--check", action="store_true", help="check structure without building ZIP")
    args = p.parse_args(argv)
    if args.check:
        return check_only()
    out = args.out or "crushexam-teleagent-v%s.zip" % read_version()
    return build_zip(out)


if __name__ == "__main__":
    sys.exit(main())
