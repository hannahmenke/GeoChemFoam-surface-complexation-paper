#!/usr/bin/env bash

set -euo pipefail

script_path="$(realpath -e -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -P -- "$(dirname -- "$script_path")" && pwd -P)"
manifest="$script_dir/arxiv_submission_files.tsv"
export_epoch="${SOURCE_DATE_EPOCH:-1788048000}"

if [[ $# -ne 1 || "$1" != *.zip ]]; then
    echo "Usage: $0 OUTPUT.zip" >&2
    exit 2
fi
if [[ ! "$export_epoch" =~ ^[0-9]+$ ]]; then
    echo "SOURCE_DATE_EPOCH must be a non-negative integer" >&2
    exit 2
fi

zip_path="$(realpath -m -- "$1")"
if [[ -e "$zip_path" || -L "$zip_path" ]]; then
    echo "Refusing to overwrite existing output: $zip_path" >&2
    exit 2
fi
mkdir -p -- "$(dirname -- "$zip_path")"
workspace="$(mktemp -d "$(dirname -- "$zip_path")/.arxiv-export.XXXXXX")"
export_dir="$workspace/source"
cleanup() { rm -rf -- "$workspace"; }
trap cleanup EXIT HUP INT TERM
mkdir -p -- "$export_dir"

declare -A destinations=()
while IFS=$'\t' read -r source destination extra; do
    [[ -z "$source" || "$source" == \#* ]] && continue
    [[ -n "${extra:-}" && "$extra" != "" ]] && { echo "Malformed manifest row: $source" >&2; exit 2; }
    [[ "$destination" != *.tex && "$destination" != *.bib && "$destination" != *.bst && "$destination" != *.cls && "$destination" != *.png ]] && {
        echo "Unsafe export name: $destination" >&2; exit 2;
    }
    [[ -n "${destinations[$destination]:-}" ]] && { echo "Duplicate export name: $destination" >&2; exit 2; }
    [[ "$source" != /* && "$source" != *..* ]] || { echo "Unsafe source: $source" >&2; exit 2; }
    src="$script_dir/$source"
    [[ -f "$src" && ! -L "$src" ]] || { echo "Missing or non-regular source: $source" >&2; exit 2; }
    cp -- "$src" "$export_dir/$destination"
    destinations[$destination]=1
done < "$manifest"

# The journal class contains an unused EPS reference in its ORCID helper.
# Neutralise that helper only in the isolated arXiv copy: this manuscript has
# no ORCID calls, and arXiv's dependency scanner must not request the unused
# logo file.
perl -0pi -e 's/\\gdef\\orcidlogo\{%\r(?:\n)?\\includegraphics\{Orcidlogo\.eps\}%\r(?:\n)?\}%/\\gdef\\orcidlogo{}%/s' \
    "$export_dir/sn-jnl.cls"
if rg -n 'Orcidlogo|\.eps' "$export_dir/sn-jnl.cls"; then
    echo "Unused ORCID/EPS dependency remained in exported class" >&2
    exit 2
fi

# Generate one self-contained manuscript source. Section inputs are expanded
# verbatim; the journal's Online Resource descriptor is replaced by the exact
# supplementary-information content and a single arXiv supplement heading.
awk -v source_root="$script_dir" '
function emit(file, line) {
    while ((getline line < file) > 0) print line
    close(file)
}
function emit_supplement(file, line, in_body) {
    in_body = 0
    while ((getline line < file) > 0) {
        if (line == "\\maketitle") {
            in_body = 1
            continue
        }
        if (line == "\\backmatter") {
            close(file)
            return
        }
        if (in_body) print line
    }
    close(file)
}
/^\\input\{sections\/[^}]+\}$/ {
    file = $0
    sub(/^\\input\{/, "", file)
    sub(/\}$/, "", file)
    emit(source_root "/" file ".tex")
    next
}
$0 == "\\section*{Supplementary Information}" {
    print "\\clearpage"
    print "\\section*{Supplementary Information}"
    # The standalone supplement is the canonical source of this body.
    emit_supplement(source_root "/supplementary.tex")
    skipping_online_resource = 1
    next
}
skipping_online_resource {
    if ($0 == "\\backmatter") {
        skipping_online_resource = 0
        print
    }
    next
}
{ print }
' "$export_dir/main.source.tex" > "$export_dir/main.tex"
rm -- "$export_dir/main.source.tex"
sed -i 's|figures/png/||g' "$export_dir/main.tex"

# Use unique, manuscript-order figure names in the flat arXiv source.  The
# repository names are intentionally preserved in the source tree; only the
# exported copies and their includegraphics references are renamed here.
sed -i \
    -e 's|{fig05_solver_workflow.png}|{figure01.png}|g' \
    -e 's|{fig01_1d_retardation.png}|{figure02.png}|g' \
    -e 's|{fig06_1d_breakthrough.png}|{figure03.png}|g' \
    -e 's|{fig09_sphere_surface_area_validation.png}|{figure04.png}|g' \
    -e 's|{fig10_hm12_surface_area_validation.png}|{figure05.png}|g' \
    -e 's|{fig11_3d_external_surface_area_validation.png}|{figure06.png}|g' \
    -e 's|{fig12_two_scale_lithium_nested_geometries.png}|{figure07.png}|g' \
    -e 's|{fig10_two_scale_pe1_fields.png}|{figure08.png}|g' \
    -e 's|{fig09_two_scale_error_vs_peclet.png}|{figure09.png}|g' \
    -e 's|{fig02_2d_fractures.png}|{figure10.png}|g' \
    -e 's|{fig03_3d_kelvin.png}|{figure11.png}|g' \
    -e 's|{fig07_kelvin_temporal.png}|{figure12.png}|g' \
    -e 's|{fig04_3d_estaillades.png}|{figure13.png}|g' \
    -e 's|{fig08_estaillades_temporal.png}|{figure14.png}|g' \
    "$export_dir/main.tex"

# Build the bibliography in the isolated export workspace.  The generated
# .bbl is then inlined through \input below, so the published arXiv package
# has no \bibliography command and does not require a BibTeX stage.
(
    cd "$export_dir"
    pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex \
        > main.bib-build.log
    bibtex main > main.bibtex.log
)
[[ -s "$export_dir/main.bbl" ]] || {
    echo "BibTeX did not generate main.bbl" >&2
    exit 2
}
# Remove the class's active \bibliographystyle write before the final
# pdflatex-only build.  It is needed for the local BibTeX generation above,
# but would leave a BibTeX marker in the arXiv build's .aux file.
perl -0pi -e 's/  \\bibliographystyle\{sn-basic\}%\r/  % bibliography is supplied as generated main.bbl\r/' \
    "$export_dir/sn-jnl.cls"
sed -i 's|\\bibliography{references}|\\input{main.bbl}|' "$export_dir/main.tex"
if rg -n '\\bibliography\{|\\bibdata\{' "$export_dir/main.tex"; then
    echo "Bibliography input remained in exported main.tex" >&2
    exit 2
fi
if rg -n '(^|[[:space:]{}])/(home|tmp|var|workspace)/' "$export_dir/main.bbl"; then
    echo "Absolute/local path remained in generated main.bbl" >&2
    exit 2
fi

# Verify that the final source is self-contained and compiles with pdflatex
# alone.  These passes intentionally run after the bibliography command has
# been replaced by the generated .bbl input.
(
    cd "$export_dir"
    pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex \
        > main.pdflatex-1.log
    pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex \
        > main.pdflatex-2.log
    pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex \
        > main.pdflatex-3.log
)
if rg -n 'Citation .* undefined|There were undefined references|undefined citations' \
    "$export_dir/main.pdflatex-3.log" "$export_dir/main.log"; then
    echo "Unresolved citation/reference remained after pdflatex-only build" >&2
    exit 2
fi

if [[ "$(rg -c '^\\documentclass' "$export_dir/main.tex")" -ne 1 ]]; then
    echo "Unexpected document class count in export" >&2
    exit 2
fi
if rg -n 'sections/|figures/png/|\\include\{' "$export_dir/main.tex"; then
    echo "Unresolved inputs or paths in export" >&2
    exit 2
fi
if rg --pcre2 -n '\\input\{(?!main\.bbl\})' "$export_dir/main.tex"; then
    echo "Unresolved input remained in export" >&2
    exit 2
fi
if [[ "$(rg -c '^\\section\*\{Supplementary Information\}$' "$export_dir/main.tex")" -ne 1 ]]; then
    echo "Expected exactly one Supplementary Information heading" >&2
    exit 2
fi
mapfile -t figure_refs < <(
    rg -o '\\includegraphics(?:\[[^]]*\])?\{figure[0-9]{2}\.png\}' "$export_dir/main.tex" \
        | sed -E 's/.*\{(figure[0-9]{2}\.png)\}/\1/' \
        | LC_ALL=C sort
)
if [[ "${#figure_refs[@]}" -ne 14 ]]; then
    echo "Expected exactly 14 figure references, found ${#figure_refs[@]}" >&2
    exit 2
fi
for figure_number in $(seq -w 1 14); do
    expected="figure${figure_number}.png"
    if [[ "${figure_refs[$((10#$figure_number - 1))]}" != "$expected" ]]; then
        echo "Figure references are not exactly figure01.png through figure14.png" >&2
        exit 2
    fi
done
if rg -n '\\includegraphics(?:\[[^]]*\])?\{fig[0-9]' "$export_dir/main.tex"; then
    echo "Repository figure name remains in exported includegraphics reference" >&2
    exit 2
fi
# Only the compiled manuscript source, generated bibliography, class, and
# manuscript-order raster figures are published.  Build inputs and logs stay
# in the temporary workspace and are never added to the archive.
package_files=(main.tex main.bbl sn-jnl.cls)
for figure_number in $(seq -w 1 14); do
    package_files+=("figure${figure_number}.png")
done
for package_file in "${package_files[@]}"; do
    [[ -f "$export_dir/$package_file" && ! -L "$export_dir/$package_file" ]] || {
        echo "Missing final package file: $package_file" >&2
        exit 2
    }
done
if [[ "${#package_files[@]}" -ne 17 ]]; then
    echo "Unexpected final package file count" >&2
    exit 2
fi

TZ=UTC touch -d "@$export_epoch" "${package_files[@]/#/$export_dir/}" "$export_dir"
(
    cd "$export_dir"
    TZ=UTC zip -X -q "$workspace/package.zip" "${package_files[@]}"
)
mv -T -- "$workspace/package.zip" "$zip_path"
printf '%s\n' "$zip_path"
