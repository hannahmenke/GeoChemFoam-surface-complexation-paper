#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

python generate_two_scale_lithium_sorption_validation.py
