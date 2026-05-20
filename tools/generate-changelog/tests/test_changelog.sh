#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SCRIPT="$SCRIPT_DIR/changelog.sh"
TMP_ROOT=$(mktemp -d)

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT HUP INT TERM

fail() {
  printf 'test_changelog.sh: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  file=$1
  expected=$2
  if ! grep -Fq -- "$expected" "$file"; then
    printf 'Expected to find:\n%s\n\nin %s\n\nActual file:\n' "$expected" "$file" >&2
    sed -n '1,220p' "$file" >&2
    exit 1
  fi
}

commit_file() {
  repo=$1
  file=$2
  message=$3
  printf '%s\n' "$message" >> "$repo/$file"
  git -C "$repo" add "$file"
  git -C "$repo" commit -m "$message" >/dev/null
}

make_repo() {
  repo=$1
  mkdir -p "$repo"
  git -C "$repo" init -q
  git -C "$repo" config user.email changelog@example.invalid
  git -C "$repo" config user.name 'Changelog Test'
}

repo_no_tags="$TMP_ROOT/no-tags"
make_repo "$repo_no_tags"
commit_file "$repo_no_tags" app.txt 'feat: add dashboard'
commit_file "$repo_no_tags" app.txt 'fix: repair login redirect'
commit_file "$repo_no_tags" app.txt 'docs: update README'
commit_file "$repo_no_tags" app.txt 'remove legacy endpoint'

output_no_tags="$TMP_ROOT/no-tags-changelog.md"
bash "$SCRIPT" --repo "$repo_no_tags" --output "$output_no_tags" --version v0.1.0 >/dev/null
assert_contains "$output_no_tags" '## v0.1.0 - '
assert_contains "$output_no_tags" 'All commits; no reachable git tags were found.'
assert_contains "$output_no_tags" '- add dashboard'
assert_contains "$output_no_tags" '- repair login redirect'
assert_contains "$output_no_tags" '- update README'
assert_contains "$output_no_tags" '- remove legacy endpoint'

repo_with_tag="$TMP_ROOT/with-tag"
make_repo "$repo_with_tag"
commit_file "$repo_with_tag" app.txt 'feat: before tag'
git -C "$repo_with_tag" tag v1.0.0
commit_file "$repo_with_tag" app.txt 'feat: add billing'
commit_file "$repo_with_tag" app.txt 'fix: resolve invoice crash'

output_with_tag="$TMP_ROOT/with-tag-changelog.md"
bash "$SCRIPT" --repo "$repo_with_tag" --output "$output_with_tag" --version v1.1.0 >/dev/null
assert_contains "$output_with_tag" 'Commits since `v1.0.0`.'
assert_contains "$output_with_tag" '- add billing'
assert_contains "$output_with_tag" '- resolve invoice crash'
if grep -Fq -- 'before tag' "$output_with_tag"; then
  fail 'tagged commit leaked into generated changelog'
fi

since_ref=$(git -C "$repo_with_tag" rev-parse HEAD~1)
output_since="$TMP_ROOT/since-changelog.md"
bash "$SCRIPT" --repo "$repo_with_tag" --since "$since_ref" --output "$output_since" --version custom >/dev/null
assert_contains "$output_since" '## custom - '
assert_contains "$output_since" '- resolve invoice crash'
if grep -Fq -- 'add billing' "$output_since"; then
  fail '--since did not restrict the commit range'
fi

printf 'All changelog tests passed.\n'
