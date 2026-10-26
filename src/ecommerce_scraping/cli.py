"""Command line entry point; grown in a later step."""

from typing import Annotated

import typer

from ecommerce_scraping import __version__

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    """Polite Scrapy ingestion pipeline for e-commerce product data."""
