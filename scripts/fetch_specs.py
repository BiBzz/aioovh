"""Download every OVHcloud API schema listed by the v1 and v2 API roots."""

import json
from pathlib import Path

import typer
from httpx2 import Client

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
API_URL = "https://eu.api.ovh.com"
ROOTS = {"v1": f"{API_URL}/1.0", "v2": f"{API_URL}/v2"}


def main() -> None:
    with Client(timeout=120.0, headers={"User-Agent": "aioovh-spec-fetcher"}) as client:
        for version, root in ROOTS.items():
            folder = SPECS / version
            index = client.get(f"{root}/").raise_for_status().json()
            for old in folder.glob("*.json"):
                old.unlink()
            (folder / "index.json").write_text(
                json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            for api in index["apis"]:
                path = api["path"]
                schema = client.get(f"{root}{path}.json").raise_for_status().json()
                name = path.strip("/").replace("/", ".")
                (folder / f"{name}.json").write_text(
                    json.dumps(schema, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                typer.echo(f"{version}{path}")


if __name__ == "__main__":
    typer.run(main)
