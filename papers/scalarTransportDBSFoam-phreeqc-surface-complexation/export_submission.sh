#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
manifest="$script_dir/submission_files.tsv"
export_epoch="${SOURCE_DATE_EPOCH:-1788048000}"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 OUTPUT_DIRECTORY_OR_ZIP" >&2
    exit 2
fi

output="$1"
workspace=""
zip_path=""

if [[ "$output" == *.zip ]]; then
    zip_path="$(realpath -m -- "$output")"
    if [[ -e "$zip_path" ]]; then
        echo "Refusing to overwrite existing output: $zip_path" >&2
        exit 2
    fi
    mkdir -p -- "$(dirname -- "$zip_path")"
    workspace="$(mktemp -d /tmp/gcf-submission-export.XXXXXX)"
    trap 'rm -rf -- "$workspace"' EXIT
    export_dir="$workspace/submission"
else
    export_dir="$(realpath -m -- "$output")"
    if [[ -e "$export_dir" ]]; then
        echo "Refusing to overwrite existing output: $export_dir" >&2
        exit 2
    fi
fi

mkdir -p -- "$export_dir"
declare -A destinations=()

while IFS=$'\t' read -r source destination extra; do
    [[ -z "$source" || "$source" == \#* ]] && continue
    if [[ -n "${extra:-}" || -z "$destination" ]]; then
        echo "Invalid manifest row for source: $source" >&2
        exit 2
    fi
    if [[ "$source" == /* || "$source" == *..* ]]; then
        echo "Unsafe source path in manifest: $source" >&2
        exit 2
    fi
    if [[ "$destination" == */* || "$destination" == "." || "$destination" == ".." ]]; then
        echo "Export destination is not flat: $destination" >&2
        exit 2
    fi
    if [[ -n "${destinations[$destination]:-}" ]]; then
        echo "Duplicate export destination: $destination" >&2
        exit 2
    fi
    if [[ ! -f "$script_dir/$source" ]]; then
        echo "Missing submission source: $source" >&2
        exit 2
    fi
    destinations[$destination]=1
    cp -- "$script_dir/$source" "$export_dir/$destination"
done < "$manifest"

for tex_file in "$export_dir"/*.tex; do
    sed -i -e 's|sections/||g' -e 's|figures/png/||g' "$tex_file"
done

if rg -n '\{sections/|\{figures/png/' "$export_dir"/*.tex; then
    echo "Unflattened TeX path remains in export" >&2
    exit 2
fi

for required in main.tex references.bib sn-jnl.cls sn-basic.bst cover_letter.txt; do
    if [[ ! -f "$export_dir/$required" ]]; then
        echo "Required export file is missing: $required" >&2
        exit 2
    fi
done

(
    cd "$export_dir"
    find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%f\n' \
        | LC_ALL=C sort \
        | xargs sha256sum
) > "$export_dir/SHA256SUMS"

TZ=UTC touch -d "@$export_epoch" "$export_dir"/*

if [[ -n "$zip_path" ]]; then
    mapfile -t export_files < <(find "$export_dir" -maxdepth 1 -type f -printf '%f\n' | LC_ALL=C sort)
    (
        cd "$export_dir"
        TZ=UTC zip -X -q "$zip_path" "${export_files[@]}"
    )
    printf '%s\n' "$zip_path"
else
    printf '%s\n' "$export_dir"
fi
