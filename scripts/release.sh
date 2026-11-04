#!/usr/bin/env bash
#
# Tag a release: the version and the changelog entry are merged through a merge
# request first, then this script signs the tag that lets CI publish to PyPI.
#
#   scripts/release.sh [--yes]
#
# It refuses to tag from another branch, a tree that differs from origin, a
# version already tagged, or a version without its changelog section.

set -euo pipefail

RELEASE_BRANCH="${RELEASE_BRANCH:-development}"
REMOTE=origin

die() { printf 'release: %s\n' "$1" >&2; exit 1; }
step() { printf '\n==> %s\n' "$1"; }

assume_yes=false
for arg in "$@"; do
    case "$arg" in
        -y | --yes) assume_yes=true ;;
        *) die "unknown argument ${arg}" ;;
    esac
done

cd "$(dirname "$0")/.."

step "Checking the working tree"
branch="$(git branch --show-current)"
[ "$branch" = "$RELEASE_BRANCH" ] || die "releases are tagged on ${RELEASE_BRANCH}, not ${branch}"
git diff-index --quiet HEAD -- || die "the tracked files have uncommitted changes"
version="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)"
[ -n "$version" ] || die "cannot read the version from pyproject.toml"
tag="v${version}"
! git rev-parse -q --verify "refs/tags/${tag}" >/dev/null || die "tag ${tag} already exists locally"
notes="$(python3 scripts/roll_changelog.py "$version" --released)"

step "Checking ${REMOTE}"
git fetch --quiet "$REMOTE" "$RELEASE_BRANCH"
[ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] ||
    die "${RELEASE_BRANCH} differs from ${REMOTE}/${RELEASE_BRANCH}, pull first"
[ -z "$(git ls-remote --tags "$REMOTE" "refs/tags/${tag}")" ] || die "tag ${tag} already exists on ${REMOTE}"
[ "$(git log -1 --format=%G?)" = "G" ] || die "the released commit is not signed with a trusted key"

step "Replaying the checks CI runs"
uv sync --frozen --quiet
uv run ruff check .
uv run ruff format --check .
uv run python scripts/generate.py >/dev/null
git diff --quiet -- src docs || die "the generated code differs from specs/, regenerate first"
uv run mypy
uv run pytest -q

step "Signing ${tag}"
# git tag defaults to --cleanup=strip, which would eat the ### headings
git tag --sign --cleanup=whitespace -m "Release ${version}

${notes}" "$tag"
git tag -v "$tag" >/dev/null 2>&1 || die "the tag signature does not verify"

if ! $assume_yes; then
    printf '\nPush %s to %s? [y/N] ' "$tag" "$REMOTE"
    read -r answer
    case "$answer" in
        [yY] | [yY][eE][sS]) ;;
        *) die "nothing pushed. To undo: git tag -d ${tag}" ;;
    esac
fi

git push "$REMOTE" "$tag"
printf '\n%s is pushed. Its pipeline waits on the manual publish job:\n  %s/-/pipelines?scope=tags\n' \
    "$tag" "$(git remote get-url "$REMOTE" | sed -E 's#^git@([^:]+):#https://\1/#; s#\.git$##')"
