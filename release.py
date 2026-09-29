#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CrushExam TeleAgent skill packager.

Produces a ZIP with SKILL.md at the root (no wrapping directory),
excluding __pycache__, tests, samples, and other dev-only files.

Usage:
    python release.py              # -> crushexam-teleagent.zip in cwd
    python release.py --check      # verify structure + size only
    python release.py --out X.zip  # custom output path
"""
import argparse
import hashlib
import os
import sys
import zipfile


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

ROOT = os.path.dirname(os.path.abspath(__file__))

# Files/dirs to include in the release ZIP
INCLUDE_FILES = [
    "SKILL.md",
    "coach.py",
    "LICENSE",
    "CHANGELOG.md",
    "MANIFEST.sha256",
]
INCLUDE_DIRS = [
    "coach",        # all .py files, excluding __pycache__
    "references",   # support docs referenced from SKILL.md
    "templates",    # workbench.html (offline one-question UI)
    "scripts",      # repeatable release-validation scripts
    "agents",       # host manifest
]

# Excluded patterns (relative paths starting with these are skipped)
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "tests", "samples", ".git",
                "figures", "validation", "CrushExam_TeleAgent"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".tmp", ".log", ".egg-info", ".zip"}


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
    # Auto-refresh MANIFEST.sha256 so it always matches the packaged content
    # (previous hash entries go stale whenever files change).
    manifest_rels = [rel for _, rel in files if rel != "MANIFEST.sha256"]
    manifest_path = os.path.join(ROOT, "MANIFEST.sha256")
    lines = []
    for full, rel in sorted(files, key=lambda x: x[1]):
        if rel == "MANIFEST.sha256":
            continue
        h = _sha256(full)
        lines.append("%s  %s" % (h, rel))
    with open(manifest_path, "w", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")
    files = collect_files()  # re-collect: MANIFEST now exists
    files = [f for f in files if f[1] != "MANIFEST.sha256"] + \
            [(manifest_path, "MANIFEST.sha256")]
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
    return 0 if skill_ok else 1


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
    p.add_argument("--out", default="crushexam-teleagent.zip", help="output ZIP path")
    p.add_argument("--check", action="store_true", help="check structure without building ZIP")
    args = p.parse_args(argv)
    if args.check:
        return check_only()
    return build_zip(args.out)


if __name__ == "__main__":
    sys.exit(main())
