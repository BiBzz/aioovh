# Contributing

## Issues and pull requests

Report bugs, ask questions and propose changes on
[GitHub](https://github.com/BiBzz/aioovh): [issues](https://github.com/BiBzz/aioovh/issues) and pull requests against `development`
are welcome there, and your commits do not need to be signed.

The code is reviewed and merged on
[GitLab](https://gitlab.com/businessagile/libraries/aioovh), which mirrors
itself to GitHub. A pull request is picked up into a GitLab merge request that
links back to it, keeps you as the author of your commits, and runs the full
CI. Once merged, the mirror brings the commits to GitHub, which marks the pull
request as merged; if they had to be rebased, the pull request is closed with
a link to the commit. Do not expect the GitHub merge button to work: only the
mirror writes to `development`.

## Setting up

The project is managed with [uv](https://docs.astral.sh/uv/), 0.13 or later:

```bash
uv sync
```

It uses the interpreter in `.python-version`, the oldest version the library
supports.

## The checks

These are the gates CI runs on every merge request on GitLab, and GitHub
Actions on every pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python scripts/generate.py && git diff --exit-code -- src docs
uv run mypy
uv run pytest -q
```

The tests run on Python 3.12, 3.13 and 3.14 in CI.

## Generated code

Everything under `src/aioovh/_operations/` and the area packages
(`src/aioovh/billing/`...) is generated, as are `docs/objects.md` and
`docs/coverage.md`; each generated file starts with a line saying so. Change
the generators (`scripts/operations.py`, `scripts/objects.py`), the mapping
(`mapping.yaml`) or the hand-written runtime (`src/aioovh/_*.py`), never the
output, then regenerate:

```bash
uv run python scripts/generate.py
```

The generator stops on a root missing from `mapping.yaml` or on a name clash.
Read the diff of `docs/objects.md`: it is the public surface.

To pick up what OVHcloud changed in its APIs:

```bash
uv run python scripts/fetch_specs.py
uv run python scripts/generate.py
```

The first command downloads every schema listed by the version 1.0 and v2
roots. Commit the schemas and the generated code together, in a merge request
of their own: its diff is the list of API changes.

## Commits

Work branches off `development`, the default branch, and lands through a
merge request. Everything in the repository is written in English, and commit
messages follow the Angular convention: `feat(client): ...`,
`fix(generator): ...`, `docs: ...`. Maintainers sign their commits and tags.

## The changelog

Anything a user of the library would notice goes under `## [Unreleased]` in
[CHANGELOG.md](CHANGELOG.md), in the merge request that changes the behaviour.
The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Releasing

1. In a merge request, bump `version` in `pyproject.toml`, run `uv lock`, and
   turn the `## [Unreleased]` section into the release:

   ```bash
   python3 scripts/roll_changelog.py 0.2.0
   ```

2. Once it is merged, from an up to date `development`:

   ```bash
   scripts/release.sh
   ```

   It checks the tree matches `origin`, the commit is signed and the
   changelog has the section, replays the checks, signs the `v0.2.0` tag with
   the changelog entry as its message, and pushes it after asking.

3. The GitLab mirror carries the tag to GitHub, where the `Release` workflow
   checks the tag matches the version, replays the checks, then waits for a
   reviewer to approve the `pypi` environment. Approving it is the point of no
   return: a version on PyPI can be yanked, but its files can never be uploaded
   again. The workflow builds the wheel and the sdist and uploads them with
   PyPI trusted publishing, so no token is stored anywhere.

### What PyPI trusts

The trusted publisher declared on PyPI for `aioovh` is the GitHub repository
`BiBzz/aioovh`, workflow `release.yml`, environment `pypi`. Renaming the
repository, the workflow or the environment breaks the upload until the
publisher is updated on PyPI. Tags matching `v*` are protected on GitLab, and
on GitHub only the mirror may create them.
