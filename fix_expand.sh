#!/usr/bin/env bash
# Run from ~/Music/aicli to add .[all] extras install to expand.sh
set -e

EXPAND="./expand.sh"

if [ ! -f "$EXPAND" ]; then
    echo "ERROR: expand.sh not found. Run from ~/Music/aicli"
    exit 1
fi

if grep -qF '.[all]' "$EXPAND"; then
    echo "expand.sh already has .[all] install — nothing to do."
    exit 0
fi

echo "Current pip install lines in expand.sh:"
grep -n "pip install" "$EXPAND" || echo "  (none found)"
echo ""

# Try to find the right insertion point using Python
python3 - "$EXPAND" << 'PYEOF'
import sys, re

path = sys.argv[1]
text = open(path).read()
lines = text.splitlines(keepends=True)

# Find ANY pip install -e line (handles various quoting/spacing styles)
patterns = [
    r'^\s*pip install -e \.',          # pip install -e .
    r'^\s*pip install -e "\."',        # pip install -e "."
    r"^\s*pip install -e '\.'",        # pip install -e '.'
    r'^\s*\$VENV_PIP install -e \.',   # $VENV_PIP install -e .
    r'^\s*\$PIP install -e \.',        # $PIP install -e .
    r'^\s*\$\{.*\} install -e \.',     # ${PYTHON}/pip install -e .
    r'^\s*"?\$PYTHON"? -m pip install -e \.', # python -m pip install -e .
    r'^\s*python.*pip install -e \.',  # python3 -m pip install -e .
]

insert_after = -1
for i, line in enumerate(lines):
    for pat in patterns:
        if re.match(pat, line):
            # Skip if this line already installs .[all] or .[dev] etc
            if '.[' not in line:
                insert_after = i
                break
    if insert_after >= 0:
        break

if insert_after < 0:
    print("WARNING: Could not find a pip install -e . line.")
    print("Please manually add this line to expand.sh after your main pip install:")
    print('    pip install -e ".[all]" --quiet')
    print("")
    print("All lines containing 'pip' or 'install':")
    for i, l in enumerate(lines):
        if 'pip' in l.lower() or 'install' in l.lower():
            print(f"  line {i+1}: {l.rstrip()}")
    sys.exit(1)

# Build the insertion line matching the indentation of the found line
indent = re.match(r'^(\s*)', lines[insert_after]).group(1)
insert_line = f'{indent}pip install -e ".[all]" --quiet  # optional extras: RAG, proxy, TUI\n'

new_lines = lines[:insert_after+1] + [insert_line] + lines[insert_after+1:]
open(path, 'w').write(''.join(new_lines))
print(f"✓ Inserted after line {insert_after+1}: {lines[insert_after].rstrip()}")
print(f"  Added: {insert_line.rstrip()}")
PYEOF
