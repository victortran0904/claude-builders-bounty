# Generate a Changelog

Portable Bash changelog generator for git repositories. It writes a formatted
`CHANGELOG.md` from commit subjects, grouped into `Added`, `Fixed`, `Changed`,
and `Removed`.

## Setup

1. Keep `tools/generate-changelog/changelog.sh` in the repository you want to summarize.
2. Run `bash tools/generate-changelog/changelog.sh`.
3. Review and commit the generated `CHANGELOG.md`.

## Behavior

- Uses `git describe --tags --abbrev=0` to find the latest reachable tag, then
  reads commits after that tag.
- If no reachable tag exists, includes all commits in the repository.
- Ignores merge commits so release notes focus on authored changes.
- Classifies conventional commits first, then keyword prefixes:
  - `Added`: `feat:`, `add`, `create`, `implement`, `introduce`, `initial`
  - `Fixed`: `fix:`, `bugfix:`, `hotfix:`, `repair`, `resolve`, `correct`, `patch`
  - `Changed`: `docs:`, `chore:`, `refactor:`, `perf:`, `test:`, `build`, `ci`, uncategorized subjects
  - `Removed`: `remove`, `delete`, `drop`, `deprecate`

## Options

```bash
bash tools/generate-changelog/changelog.sh --help
bash tools/generate-changelog/changelog.sh --output RELEASE_NOTES.md
bash tools/generate-changelog/changelog.sh --since v1.0.0 --version v1.1.0
```

`SAMPLE_CHANGELOG.md` was generated from this repository's real git history.
