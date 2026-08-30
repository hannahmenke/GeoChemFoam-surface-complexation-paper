#!/usr/bin/env bash

set -euo pipefail

script_path="$(realpath -e -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -P -- "$(dirname -- "$script_path")" && pwd -P)"
manifest="$script_dir/submission_files.tsv"
export_epoch="${SOURCE_DATE_EPOCH:-1788048000}"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 OUTPUT_DIRECTORY_OR_ZIP" >&2
    exit 2
fi

output="$1"
workspace=""
zip_path=""
export_dir=""
final_dir=""
temporary_zip=""

cleanup() {
    if [[ -n "$workspace" && -d "$workspace" ]]; then
        rm -rf -- "$workspace"
    fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! "$export_epoch" =~ ^[0-9]+$ ]]; then
    echo "SOURCE_DATE_EPOCH must be a non-negative integer" >&2
    exit 2
fi

if [[ "$output" == *.zip ]]; then
    zip_path="$(realpath -m -- "$output")"
    if [[ -e "$zip_path" || -L "$zip_path" ]]; then
        echo "Refusing to overwrite existing output: $zip_path" >&2
        exit 2
    fi
    output_parent="$(dirname -- "$zip_path")"
    mkdir -p -- "$output_parent"
    output_parent="$(realpath -e -- "$output_parent")"
    output_name="$(basename -- "$zip_path")"
    workspace="$(mktemp -d -- "$output_parent/.${output_name}.tmp.XXXXXX")"
    export_dir="$workspace/submission"
    temporary_zip="$workspace/$output_name"
else
    final_dir="$(realpath -m -- "$output")"
    if [[ -e "$final_dir" || -L "$final_dir" ]]; then
        echo "Refusing to overwrite existing output: $final_dir" >&2
        exit 2
    fi
    output_parent="$(dirname -- "$final_dir")"
    mkdir -p -- "$output_parent"
    output_parent="$(realpath -e -- "$output_parent")"
    output_name="$(basename -- "$final_dir")"
    workspace="$(mktemp -d -- "$output_parent/.${output_name}.tmp.XXXXXX")"
    export_dir="$workspace"
fi

mkdir -p -- "$export_dir"
declare -A destinations=()

resolve_source() {
    local source="$1"
    local candidate="$script_dir"
    local component
    local canonical_source
    local -a components

    if [[ "$source" == /* ]]; then
        echo "Unsafe absolute source path in manifest: $source" >&2
        return 2
    fi

    IFS='/' read -r -a components <<< "$source"
    for component in "${components[@]}"; do
        if [[ -z "$component" || "$component" == "." || "$component" == ".." ]]; then
            echo "Unsafe source path component in manifest: $source" >&2
            return 2
        fi
        candidate="$candidate/$component"
        if [[ -L "$candidate" ]]; then
            echo "Symlink source path component is not allowed: $source" >&2
            return 2
        fi
    done

    if [[ ! -e "$candidate" ]]; then
        echo "Missing submission source: $source" >&2
        return 2
    fi
    canonical_source="$(realpath -e -- "$candidate")" || {
        echo "Cannot resolve submission source: $source" >&2
        return 2
    }
    if [[ "$canonical_source" != "$script_dir/"* || ! -f "$canonical_source" ]]; then
        echo "Submission source is not a regular file beneath the package directory: $source" >&2
        return 2
    fi

    printf '%s\n' "$canonical_source"
}

while IFS=$'\t' read -r source destination extra; do
    [[ -z "$source" || "$source" == \#* ]] && continue
    if [[ -n "${extra:-}" || -z "$destination" ]]; then
        echo "Invalid manifest row for source: $source" >&2
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
    canonical_source="$(resolve_source "$source")"
    destinations[$destination]=1
    cp -- "$canonical_source" "$export_dir/$destination"
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

TZ=UTC touch -d "@$export_epoch" "$export_dir"/* "$export_dir"

if [[ -n "$zip_path" ]]; then
    mapfile -t export_files < <(find "$export_dir" -maxdepth 1 -type f -printf '%f\n' | LC_ALL=C sort)
    (
        cd "$export_dir"
        TZ=UTC zip -X -q "$temporary_zip" "${export_files[@]}"
    )
    if [[ -e "$zip_path" || -L "$zip_path" ]]; then
        echo "Refusing to overwrite existing output: $zip_path" >&2
        exit 2
    fi
    mv -T -n -- "$temporary_zip" "$zip_path"
    if [[ -e "$temporary_zip" ]]; then
        echo "Refusing to overwrite existing output: $zip_path" >&2
        exit 2
    fi
    printf '%s\n' "$zip_path"
else
    if [[ -e "$final_dir" || -L "$final_dir" ]]; then
        echo "Refusing to overwrite existing output: $final_dir" >&2
        exit 2
    fi
    mv -T -n -- "$workspace" "$final_dir"
    if [[ -d "$workspace" ]]; then
        echo "Refusing to overwrite existing output: $final_dir" >&2
        exit 2
    fi
    workspace=""
    printf '%s\n' "$final_dir"
fi
