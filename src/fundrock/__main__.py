"""Command line interface for fundrock."""

import click

from fundrock.logging_setup import configure_logging
from fundrock.nav_data_provider import NAVDataProvider
from fundrock.nav_report_manager import NAVReportFileManager

_PROCEED_PHRASE = "please proceed"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(
    None, "-v", "--version", package_name="fundrock", prog_name="fundrock"
)
def main() -> None:
    """Manage the fundrock NAV report database."""
    configure_logging()


@main.command("set-up")
def set_up() -> None:
    """Create a brand-new, empty database."""
    manager = NAVReportFileManager()
    try:
        manager.set_up()
    except FileExistsError as error:
        raise click.ClickException(str(error))
    click.echo(f"Database created: {manager.db_connection_string}")


@main.command("tear-down")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def tear_down(yes: bool) -> None:
    """Permanently delete the database."""
    manager = NAVReportFileManager()
    if not yes:
        click.secho(
            f"WARNING: this permanently deletes the database ({manager.db_connection_string}) "
            "and all its data.",
            fg="yellow",
        )
        answer = click.prompt(f'Type "{_PROCEED_PHRASE}" to continue', default="", show_default=False)
        if answer.strip().lower() != _PROCEED_PHRASE:
            raise click.ClickException("Aborted; the database was not deleted.")
    manager.tear_down()
    click.echo("Database deleted.")


@main.command("update")
def update() -> None:
    """Add new and modified NAV report files to the database."""
    manager = NAVReportFileManager()
    try:
        result = manager.update()
    except FileNotFoundError as error:
        raise click.ClickException(str(error))
    click.echo(
        f"Added {len(result.added)}, updated {len(result.updated)}, "
        f"unchanged {len(result.unchanged)}, failed {len(result.failed)}."
    )
    if result.failed:
        for path in result.failed:
            click.echo(f"  failed: {path}", err=True)
        raise SystemExit(1)


@main.command("export-summary")
@click.option("--portfolio", "portfolio_code", required=True, help="Portfolio code.")
@click.option("--sub-path", default=None, help="Output sub-directory (no filename).")
def export_summary(portfolio_code: str, sub_path: str | None) -> None:
    """Export a portfolio's NAV Summary time series to a CSV file."""
    provider = NAVDataProvider(portfolio_code)
    try:
        path = provider.write_nav_summary_csv(sub_path)
    except (FileNotFoundError, ValueError) as error:
        raise click.ClickException(str(error))
    click.echo(f"Wrote {path}")


if __name__ == "__main__":
    main()
