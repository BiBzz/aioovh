"""Generate aioovh from the OVHcloud schemas in specs/: operations, then objects."""

import subprocess

import objects
import operations
import typer


def main(
    format_code: bool = typer.Option(True, help="Run ruff on the output."),
) -> None:
    objects.clean()
    modules = operations.generate()
    namespaces = objects.generate(modules)
    typer.echo(f"{len(modules)} APIs, {len(namespaces)} namespaces")
    if format_code:
        targets = [
            str(operations.PACKAGE),
            *namespaces,
            str(objects.PACKAGE / "_namespaces.py"),
        ]
        subprocess.run(["ruff", "check", "--fix", "--quiet", *targets], check=False)
        subprocess.run(["ruff", "format", "--quiet", *targets], check=True)


if __name__ == "__main__":
    typer.run(main)
