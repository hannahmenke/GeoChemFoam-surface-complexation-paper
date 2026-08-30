#!/usr/bin/env bash

set -euo pipefail

script_path="$(realpath -e -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -P -- "$(dirname -- "$script_path")" && pwd -P)"
test_root="$(mktemp -d /tmp/gcf-export-tests.XXXXXX)"

cleanup() {
    rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

make_fixture() {
    local fixture="$1"
    mkdir -p -- "$fixture"
    cp -- "$script_dir/export_submission.sh" "$fixture/export_submission.sh"
    chmod +x "$fixture/export_submission.sh"
    printf '\\documentclass{sn-jnl}\n\\begin{document}Test\\end{document}\n' > "$fixture/main.tex"
    printf '\\documentclass{sn-jnl}\n\\begin{document}Supplement\\end{document}\n' > "$fixture/supplementary.tex"
    printf 'Supplementary text\n' > "$fixture/supplementary_information.tex"
    printf '@misc{test, title={Test}}\n' > "$fixture/references.bib"
    printf 'class fixture\n' > "$fixture/sn-jnl.cls"
    printf 'bst fixture\n' > "$fixture/sn-basic.bst"
    printf 'cover fixture\n' > "$fixture/cover_letter.txt"
    printf '%s\n' \
        $'main.tex\tmain.tex' \
        $'supplementary.tex\tsupplementary.tex' \
        $'supplementary_information.tex\tsupplementary_information.tex' \
        $'references.bib\treferences.bib' \
        $'sn-jnl.cls\tsn-jnl.cls' \
        $'sn-basic.bst\tsn-basic.bst' \
        $'cover_letter.txt\tcover_letter.txt' \
        > "$fixture/submission_files.tsv"
}

expect_failure() {
    local name="$1"
    local fixture="$test_root/$name"
    local output="$test_root/${name}-output"
    shift
    make_fixture "$fixture"
    "$@" "$fixture"
    if "$fixture/export_submission.sh" "$output" > "$test_root/${name}.stdout" 2> "$test_root/${name}.stderr"; then
        echo "Expected failure: $name" >&2
        exit 1
    fi
    if [[ -e "$output" || -L "$output" ]]; then
        echo "Failed export was published: $name" >&2
        exit 1
    fi
    if compgen -G "$test_root/.${name}-output.tmp.*" > /dev/null; then
        echo "Failed export left a transaction directory: $name" >&2
        exit 1
    fi
}

add_absolute_source() {
    printf '/etc/hosts\thosts.txt\n' >> "$1/submission_files.tsv"
}

add_parent_source() {
    printf '../outside.txt\toutside.txt\n' >> "$1/submission_files.tsv"
}

add_file_symlink() {
    ln -s /etc/hosts "$1/linked-file"
    printf 'linked-file\tlinked.txt\n' >> "$1/submission_files.tsv"
}

add_parent_symlink() {
    ln -s /etc "$1/linked-parent"
    printf 'linked-parent/hosts\thosts.txt\n' >> "$1/submission_files.tsv"
}

add_missing_source() {
    printf 'missing.txt\tmissing.txt\n' >> "$1/submission_files.tsv"
}

add_duplicate_destination() {
    printf 'cover_letter.txt\tmain.tex\n' >> "$1/submission_files.tsv"
}

add_nonflat_destination() {
    printf 'cover_letter.txt\tnested/cover_letter.txt\n' >> "$1/submission_files.tsv"
}

add_malformed_row() {
    printf 'cover_letter.txt\textra.txt\tunexpected\n' >> "$1/submission_files.tsv"
}

expect_failure absolute-source add_absolute_source
expect_failure parent-source add_parent_source
expect_failure file-symlink add_file_symlink
expect_failure parent-symlink add_parent_symlink
expect_failure missing-source add_missing_source
expect_failure duplicate-destination add_duplicate_destination
expect_failure nonflat-destination add_nonflat_destination
expect_failure malformed-row add_malformed_row

fixture="$test_root/success"
make_fixture "$fixture"
ln -s "$fixture/export_submission.sh" "$test_root/export-via-symlink.sh"
"$test_root/export-via-symlink.sh" "$test_root/directory-one" > /dev/null
"$fixture/export_submission.sh" "$test_root/directory-two" > /dev/null
diff -ru -- "$test_root/directory-one" "$test_root/directory-two"

"$fixture/export_submission.sh" "$test_root/archive-one.zip" > /dev/null
"$fixture/export_submission.sh" "$test_root/archive-two.zip" > /dev/null
cmp --silent "$test_root/archive-one.zip" "$test_root/archive-two.zip"

if "$fixture/export_submission.sh" "$test_root/directory-one" > /dev/null 2>&1; then
    echo "Existing directory was overwritten" >&2
    exit 1
fi
if "$fixture/export_submission.sh" "$test_root/archive-one.zip" > /dev/null 2>&1; then
    echo "Existing ZIP was overwritten" >&2
    exit 1
fi

printf 'Exporter adversarial and transactional tests passed.\n'
