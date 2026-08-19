#!/bin/bash

set -e

###### USERS INPUT ############################################################

# Construct nonuniform closed-system species fields from epsNum.
A_scale=1.0
A_shift=0.0
B_scale=0.25
B_shift=0.15

#### END OF USER INPUT #######################################################

./initCaseTransport.sh

export A_scale
export A_shift
export B_scale
export B_shift

python - <<'PY'
import os
from pathlib import Path
import re

A_SCALE = float(os.environ["A_scale"])
A_SHIFT = float(os.environ["A_shift"])
B_SCALE = float(os.environ["B_scale"])
B_SHIFT = float(os.environ["B_shift"])


def read_nonuniform_values(path):
    text = Path(path).read_text()
    match = re.search(
        r'internalField\s+nonuniform\s+List<scalar>\s*\n(\d+)\s*\n\((.*?)\)\s*;',
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Could not parse nonuniform internalField in {path}")

    count = int(match.group(1))
    values = [float(item) for item in match.group(2).split()]

    if len(values) != count:
        raise RuntimeError(f"Value count mismatch in {path}: {len(values)} != {count}")

    return values


def replace_uniform_internal_field(path, values):
    text = Path(path).read_text()
    payload = "\n".join(f"{value:.12g}" for value in values)
    replacement = (
        "internalField   nonuniform List<scalar>\n"
        f"{len(values)}\n"
        "(\n"
        f"{payload}\n"
        ");"
    )
    text, count = re.subn(
        r'internalField\s+uniform\s+[-+0-9.eE]+;',
        replacement,
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Could not replace uniform internalField in {path}")
    Path(path).write_text(text)


def set_inlet_zero_gradient(path):
    text = Path(path).read_text()
    old = (
        "    inlet\n"
        "    {\n"
        "        type            fixedValue;\n"
    )
    new = (
        "    inlet\n"
        "    {\n"
        "        type            zeroGradient;\n"
    )
    if old not in text:
        raise RuntimeError(f"Could not find inlet fixedValue block in {path}")
    Path(path).write_text(text.replace(old, new, 1))


def zero_vector_field(path):
    text = Path(path).read_text()
    text, count = re.subn(
        r'internalField\s+uniform\s+\([^;]+\);',
        'internalField   uniform (0 0 0);',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Could not zero internal U field in {path}")

    text = re.sub(
        r'value\s+uniform\s+\([^;]+\);',
        'value           uniform (0 0 0);',
        text,
    )
    Path(path).write_text(text)


proc_dirs = sorted(Path('.').glob('processor*'))

if not proc_dirs:
    proc_dirs = [Path('.')]

for proc_dir in proc_dirs:
    zero_vector_field(proc_dir / '0' / 'U')

    eps_values = read_nonuniform_values(proc_dir / '0' / 'epsNum')
    a_values = [A_SHIFT + A_SCALE * value for value in eps_values]
    b_values = [B_SHIFT + B_SCALE * value for value in eps_values]

    a_path = proc_dir / '0' / 'A'
    b_path = proc_dir / '0' / 'B'

    replace_uniform_internal_field(a_path, a_values)
    replace_uniform_internal_field(b_path, b_values)

    set_inlet_zero_gradient(a_path)
    set_inlet_zero_gradient(b_path)
PY

echo -e "Closed transport case initialised"
