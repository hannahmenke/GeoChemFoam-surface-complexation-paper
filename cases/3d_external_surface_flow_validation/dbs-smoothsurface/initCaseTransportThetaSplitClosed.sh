#!/bin/bash

set -e

###### USERS INPUT ############################################################

Theta_scale=0.5
Theta_shift=5e-5

#### END OF USER INPUT #######################################################

./initCaseTransportClosed.sh

export Theta_scale
export Theta_shift

python - <<'PY'
import os
import re
from pathlib import Path

theta_scale = float(os.environ["Theta_scale"])
theta_shift = float(os.environ["Theta_shift"])


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


def replace_nonuniform_internal_field(path, values):
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
        r'internalField\s+nonuniform\s+List<scalar>\s*\n\d+\s*\n\((.*?)\)\s*;',
        replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError(f"Could not replace nonuniform internalField in {path}")
    Path(path).write_text(text)


proc_dirs = sorted(Path('.').glob('processor*'))

if not proc_dirs:
    proc_dirs = [Path('.')]

for proc_dir in proc_dirs:
    eps_values = read_nonuniform_values(proc_dir / '0' / 'epsNum')
    theta_values = [theta_shift + theta_scale * value for value in eps_values]
    replace_nonuniform_internal_field(proc_dir / '0' / 'theta', theta_values)
PY

echo -e "Theta-split closed transport case initialised"
