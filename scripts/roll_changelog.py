"""Turn the Unreleased section of CHANGELOG.md into a released one."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
UNRELEASED = "## [Unreleased]"
LINK = re.compile(
    r"^\[Unreleased\]: (?P<base>\S+)/-/compare/(?P<previous>v\S+)\.\.\.development$",
    re.MULTILINE,
)


def fail(message: str) -> NoReturn:
    print(f"roll_changelog: {message}", file=sys.stderr)
    raise SystemExit(1)


def released_body(text: str, version: str) -> str:
    heading = re.search(rf"^## \[{re.escape(version)}\] - \S+$", text, re.MULTILINE)
    if heading is None:
        fail(f"CHANGELOG.md has no released section for {version}")
    after = text[heading.end() :]
    return re.split(r"^(?:## |\[)", after, maxsplit=1, flags=re.MULTILINE)[0].strip()


def main(argv: list[str]) -> None:
    if not argv or argv[0].startswith("-"):
        fail("usage: roll_changelog.py <version> [--check | --body | --released]")
    version = argv[0]
    check_only = "--check" in argv[1:]
    body_only = "--body" in argv[1:]

    text = CHANGELOG.read_text(encoding="utf-8")
    if "--released" in argv[1:]:
        print(released_body(text, version))
        return
    if UNRELEASED not in text:
        fail(f"CHANGELOG.md has no '{UNRELEASED}' heading")
    if f"## [{version}]" in text:
        fail(f"CHANGELOG.md already has a section for {version}")

    after_heading = text.split(UNRELEASED, 1)[1]
    body = re.split(r"^## ", after_heading, maxsplit=1, flags=re.MULTILINE)[0]
    if not body.strip():
        fail(
            f"nothing under '{UNRELEASED}' in CHANGELOG.md: "
            f"write what {version} changes for its users first"
        )

    if body_only:
        print(body.strip("\n"))
        return

    link = LINK.search(text)
    if link is None:
        fail(
            "CHANGELOG.md has no "
            "'[Unreleased]: <base>/-/compare/vX.Y.Z...development' line"
        )
    if check_only:
        return

    text = text.replace(
        UNRELEASED,
        f"{UNRELEASED}\n\n## [{version}] - {date.today().isoformat()}",
        1,
    )
    base = link.group("base")
    previous = link.group("previous")
    text = text.replace(
        link.group(0),
        f"[Unreleased]: {base}/-/compare/v{version}...development\n"
        f"[{version}]: {base}/-/compare/{previous}...v{version}",
        1,
    )
    CHANGELOG.write_text(text, encoding="utf-8")
    print(f"CHANGELOG.md: {previous[1:]} to {version}")


if __name__ == "__main__":
    main(sys.argv[1:])
