#!/usr/bin/env python3
"""
bump_version.py — Atomically update the version string across all aicli files.

Version appears in 6+ places. This script updates all of them in one shot
to prevent drift between __version__.py, pyproject.toml, CHANGELOG.md,
README.md, map_structure.sh, and mcp_server.py fallback.

Usage:
  python bump_version.py 1.6.0
  python bump_version.py 1.6.1 --dry-run   # preview changes without writing
  python bump_version.py --current          # print current version
  python bump_version.py --update-tests 763 # update test badge in README
"""

import re
import sys
from pathlib import Path

# ── Files and their version patterns ─────────────────────────────────────────

FILES = [
    # (path, search_pattern, replacement_template)
    (
        "aicli/__version__.py",
        r'__version__\s*=\s*"[^"]+"',
        '__version__ = "{version}"',
    ),
    (
        "pyproject.toml",
        r'^version\s*=\s*"[^"]+"',
        'version = "{version}"',
    ),
    (
        "aicli/handlers/mcp_server.py",
        r'(SERVER_VERSION_IMPORT\s*=\s*)"[0-9]+\.[0-9]+\.[0-9]+"',
        '\\1"{version}"',
    ),
    (
        "map_structure.sh",
        r'VERSION="[^"]+"',
        'VERSION="{version}"',
    ),
    (
        "README.md",
        r'version-[0-9]+\.[0-9]+\.[0-9]+-ff4488',
        'version-{version}-ff4488',
    ),
    (
        "README.md",
        r'\*\*Latest: v[0-9]+\.[0-9]+\.[0-9]+[^*]*\*\*',
        '**Latest: v{version}**',
    ),
]

# ── Test badge pattern (updated separately via update_test_badge) ──────────────
# README test badge: tests-669%20passing-22c55e
# Not updated by bump_version — use: python bump_version.py --update-tests N


def get_current_version() -> str:
    """Read current version from __version__.py."""
    path = Path("aicli/__version__.py")
    if not path.exists():
        print("ERROR: aicli/__version__.py not found. Run from project root.")
        sys.exit(1)
    text = path.read_text()
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        print("ERROR: Could not parse __version__ from aicli/__version__.py")
        sys.exit(1)
    return m.group(1)


def bump(new_version: str, dry_run: bool = False) -> None:
    """Update version in all tracked files."""
    current = get_current_version()
    if current == new_version:
        print(f"Already at version {new_version} — nothing to do.")
        return

    print(f"Bumping {current} → {new_version}{' (dry run)' if dry_run else ''}\n")

    changed = []
    for file_path, pattern, replacement_tmpl in FILES:
        path = Path(file_path)
        if not path.exists():
            print(f"  SKIP (not found): {file_path}")
            continue

        text = path.read_text()
        replacement = replacement_tmpl.replace("{version}", new_version)
        new_text, count = re.subn(pattern, replacement, text,
                                   flags=re.MULTILINE)
        if count == 0:
            print(f"  WARN  (no match): {file_path}  pattern={pattern!r}")
        elif new_text == text:
            print(f"  OK   (unchanged): {file_path}")
        else:
            print(f"  ✓  {count} change(s): {file_path}")
            if not dry_run:
                path.write_text(new_text)
            changed.append(file_path)

    # Also update CHANGELOG.md — add a new [version] header if not present
    cl_path = Path("CHANGELOG.md")
    if cl_path.exists():
        cl_text = cl_path.read_text()
        header = f"## [{new_version}]"
        if header not in cl_text:
            from datetime import date
            today = date.today().isoformat()
            new_entry = f"{header} — {today}\n\n### Added\n\n*(fill in release notes)*\n\n---\n\n"
            # Insert after the first line (# Changelog)
            lines = cl_text.split("\n", 2)
            new_cl = lines[0] + "\n\n" + new_entry + ("\n".join(lines[1:]) if len(lines) > 1 else "")
            print(f"  ✓  CHANGELOG.md: added [{new_version}] header (fill in notes)")
            if not dry_run:
                cl_path.write_text(new_cl)
            changed.append("CHANGELOG.md")
        else:
            print(f"  OK   (unchanged): CHANGELOG.md (header already present)")

    print()
    if dry_run:
        print(f"Dry run complete — {len(changed)} file(s) would change. Re-run without --dry-run to apply.")
    else:
        print(f"Done — {len(changed)} file(s) updated to v{new_version}")
        print(f"\nNext steps:")
        print(f"  git add -A && git commit -m 'chore: bump version to {new_version}'")
        print(f"  python -m build")
        print(f"  twine upload dist/aicli_maxmux-{new_version}*")
        print(f"  git tag v{new_version} && git push --tags")


def _update_test_badge(count: int, dry_run: bool = False) -> None:
    """Update the test count badge in README.md."""
    path = Path("README.md")
    if not path.exists():
        print("ERROR: README.md not found")
        return
    text = path.read_text()
    import re as _re
    new_text, n = _re.subn(
        r'tests-[0-9]+%20passing-22c55e',
        f'tests-{count}%20passing-22c55e',
        text,
    )
    if n == 0:
        print("  WARN: test badge pattern not found in README.md")
    elif new_text == text:
        print(f"  OK (unchanged): README.md test badge already shows {count}")
    else:
        print(f"  ✓ README.md: test badge → {count} passing")
        if not dry_run:
            path.write_text(new_text)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bump aicli version across all files.")
    parser.add_argument("version", nargs="?", help="New version string (e.g. 1.5.5)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--current", action="store_true", help="Print current version and exit")
    parser.add_argument("--update-tests", metavar="N", type=int,
                        help="Update test count badge in README to N passing")
    args = parser.parse_args()

    if args.current:
        print(get_current_version())
        return

    if getattr(args, 'update_tests', None) is not None:
        _update_test_badge(args.update_tests, dry_run=args.dry_run)
        return

    if not args.version:
        print("Usage: python bump_version.py <new_version> [--dry-run]")
        print(f"Current version: {get_current_version()}")
        sys.exit(1)

    # Validate semver
    if not re.match(r"^\d+\.\d+\.\d+$", args.version):
        print(f"ERROR: version must be x.y.z format, got: {args.version!r}")
        sys.exit(1)

    bump(args.version, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
