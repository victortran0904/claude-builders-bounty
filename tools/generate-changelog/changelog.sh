#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash changelog.sh [options]

Generate CHANGELOG.md from git commit history.

Options:
  --output PATH    Write changelog to PATH. Defaults to the repo root CHANGELOG.md.
  --since REF      Use commits after REF instead of the latest reachable git tag.
  --version NAME   Heading name for this changelog section. Defaults to Unreleased.
  --repo PATH      Git repository path. Defaults to the current directory.
  --help           Show this help message.
USAGE
}

die() {
  printf 'changelog.sh: %s\n' "$*" >&2
  exit 1
}

is_absolute_path() {
  case "$1" in
    /*) return 0 ;;
    *) return 1 ;;
  esac
}

strip_conventional_prefix() {
  subject=$1
  printf '%s\n' "$subject" | sed -E 's/^[A-Za-z]+(\([^)]+\))?!?:[[:space:]]*//'
}

categorize_subject() {
  subject=$1
  lower=$(printf '%s\n' "$subject" | tr '[:upper:]' '[:lower:]')

  case "$lower" in
    feat:*|feat\(*|feature:*|feature\(*|add:*|add\(*)
      printf 'Added'
      return
      ;;
    fix:*|fix\(*|bugfix:*|bugfix\(*|hotfix:*|hotfix\(*)
      printf 'Fixed'
      return
      ;;
    remove:*|remove\(*|removed:*|removed\(*|delete:*|delete\(*|drop:*|drop\(*)
      printf 'Removed'
      return
      ;;
    refactor:*|refactor\(*|perf:*|perf\(*|docs:*|docs\(*|test:*|test\(*|tests:*|tests\(*|build:*|build\(*|ci:*|ci\(*|style:*|style\(*|chore:*|chore\(*)
      printf 'Changed'
      return
      ;;
  esac

  case "$lower" in
    add\ *|adds\ *|added\ *|create\ *|creates\ *|created\ *|implement\ *|implements\ *|implemented\ *|introduce\ *|introduces\ *|introduced\ *|initial\ *)
      printf 'Added'
      ;;
    fix\ *|fixes\ *|fixed\ *|repair\ *|repairs\ *|repaired\ *|resolve\ *|resolves\ *|resolved\ *|correct\ *|corrects\ *|corrected\ *|patch\ *|patches\ *|patched\ *)
      printf 'Fixed'
      ;;
    remove\ *|removes\ *|removed\ *|delete\ *|deletes\ *|deleted\ *|drop\ *|drops\ *|dropped\ *|deprecate\ *|deprecates\ *|deprecated\ *)
      printf 'Removed'
      ;;
    update\ *|updates\ *|updated\ *|change\ *|changes\ *|changed\ *|improve\ *|improves\ *|improved\ *|rename\ *|renames\ *|renamed\ *|bump\ *|bumps\ *|bumped\ *|upgrade\ *|upgrades\ *|upgraded\ *|adjust\ *|adjusts\ *|adjusted\ *)
      printf 'Changed'
      ;;
    *)
      printf 'Changed'
      ;;
  esac
}

append_item() {
  category=$1
  item=$2
  case "$category" in
    Added) added="${added}${item}" ;;
    Fixed) fixed="${fixed}${item}" ;;
    Changed) changed="${changed}${item}" ;;
    Removed) removed="${removed}${item}" ;;
    *) changed="${changed}${item}" ;;
  esac
}

write_section() {
  title=$1
  entries=$2
  trailing_blank=${3:-yes}
  printf '### %s\n\n' "$title" >> "$tmp_file"
  if [ -n "$entries" ]; then
    printf '%s' "$entries" >> "$tmp_file"
  else
    printf '_No entries._\n' >> "$tmp_file"
  fi
  if [ "$trailing_blank" = yes ]; then
    printf '\n' >> "$tmp_file"
  fi
}

repo_arg=.
output_arg=
since_arg=
version=Unreleased
invocation_dir=$PWD

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      [ "$#" -ge 2 ] || die '--output requires a path'
      output_arg=$2
      shift 2
      ;;
    --since)
      [ "$#" -ge 2 ] || die '--since requires a git ref'
      since_arg=$2
      shift 2
      ;;
    --version)
      [ "$#" -ge 2 ] || die '--version requires a name'
      version=$2
      shift 2
      ;;
    --repo)
      [ "$#" -ge 2 ] || die '--repo requires a path'
      repo_arg=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[ -n "$version" ] || die '--version cannot be empty'

if ! git_root=$(git -C "$repo_arg" rev-parse --show-toplevel 2>/dev/null); then
  die "not a git repository: $repo_arg"
fi

if [ -n "$output_arg" ]; then
  if is_absolute_path "$output_arg"; then
    output_path=$output_arg
  else
    output_path=$invocation_dir/$output_arg
  fi
else
  output_path=$git_root/CHANGELOG.md
fi

if [ -n "$since_arg" ]; then
  if ! git -C "$git_root" rev-parse --verify --quiet "${since_arg}^{commit}" >/dev/null; then
    die "invalid --since ref: $since_arg"
  fi
  range="${since_arg}..HEAD"
  source_line="Commits since \`$since_arg\`."
else
  since_ref=$(git -C "$git_root" describe --tags --abbrev=0 2>/dev/null || true)
  if [ -n "$since_ref" ]; then
    range="${since_ref}..HEAD"
    source_line="Commits since \`$since_ref\`."
  else
    range=HEAD
    source_line='All commits; no reachable git tags were found.'
  fi
fi

added=
fixed=
changed=
removed=
commit_count=0
separator=$(printf '\037')

while IFS="$separator" read -r hash subject || [ -n "$hash" ]; do
  [ -n "$hash" ] || continue
  commit_count=$((commit_count + 1))
  category=$(categorize_subject "$subject")
  summary=$(strip_conventional_prefix "$subject")
  append_item "$category" "- ${summary} (${hash})"$'\n'
done < <(git -C "$git_root" log --no-merges --pretty=format:'%h%x1f%s' "$range")

output_dir=$(dirname "$output_path")
mkdir -p "$output_dir"
tmp_file=$(mktemp "${output_path}.tmp.XXXXXX") || die 'could not create temporary output file'
trap 'rm -f "$tmp_file"' EXIT HUP INT TERM

today=$(date +%Y-%m-%d)

{
  printf '# Changelog\n\n'
  printf '## %s - %s\n\n' "$version" "$today"
  printf '%s\n\n' "$source_line"
  printf '%s commits included.\n\n' "$commit_count"
} > "$tmp_file"

write_section Added "$added"
write_section Fixed "$fixed"
write_section Changed "$changed"
write_section Removed "$removed" no

mv "$tmp_file" "$output_path"
trap - EXIT HUP INT TERM
printf 'Wrote %s using %s commits.\n' "$output_path" "$commit_count"
