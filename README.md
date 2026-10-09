# fundrock

A new Python package using a `src/` layout.

## Development

Install the package in editable mode and run the test suite:

```bash
python -m pip install -e .
python -m unittest discover -s tests
```

The package source is in `src/fundrock/`.

NAV reports are stored as a dated series. Each portfolio can have one report per
date, while different portfolios can have reports for the same date.

To process every dated NAV Excel report under `$DATA_PATH/fundrock/nav_cache`:

```python
from fundrock.nav_report_manager import NAVReportFileManager

manager = NAVReportFileManager()
manager.process_all_reports()
```

The manager discovers files named like `NAV_65713_2026-09-29.xls` (also
supporting `.xlsx`) and processes them in report-date order. Reprocessing a
portfolio/date replaces its stored snapshot rather than creating a duplicate.
By default, the SQLite database is created at `var/db/nav_database.db`; a custom
database connection string can be passed to `NAVReportFileManager` when needed.
Header values are read from the cells beside their labels (for example, values
in column D beside labels in column C). The report date is read from cell C3
and checked against the date in the filename before the report is stored.
Rows under `HOLDINGS AT MARKET VALUE` are grouped by their report subheading:
`group_label` stores the outer heading and `instrument_type` stores values such
as `EQUITIES` or `FUNDS`; the outer heading is a rowless parent group holding
the reported section total.

Each group stores the five values from its `TOTAL` row. The parser checks the
four monetary totals exactly and checks `percent_of_market_value` after
normalizing detail percentages to fractions with a display-rounding tolerance.
Columns with no detail values are skipped. Mismatches are logged at `CRITICAL`
with the report, group, field, expected value, and actual total; they do not
prevent the report from being saved.
Summary items are read from the rows after `BASE CURRENCY` and before
`Calculated NAV Value Difference`; these headings are not stored as items.

To read stored data for one portfolio, use `NAVDataProvider`:

```python
from fundrock.nav_data_provider import NAVDataProvider

provider = NAVDataProvider("65713")
frame = provider.nav_summary_frames()   # DataFrame indexed by report_date, one column per summary description
path = provider.write_nav_summary_csv() # NAVSummary-65713-<latest date>.csv under the output path
```

The database lifecycle is explicit. `set_up()` creates a brand-new database with
all tables. If the database already exists it logs an `ERROR` and raises
`FileExistsError`, stating that it must first be torn down with `tear_down()`.
`tear_down()` deletes the database file so that it no longer exists (safe to call
when it is already absent). Only file-based SQLite databases are supported.

```python
manager.tear_down()   # database no longer exists
manager.set_up()      # fresh empty database
manager.process_all_reports()
```

## Logging

Call `fundrock.logging_setup.configure_logging()` once at start-up. It applies
`src/fundrock/config/log_config.yaml`: the `fundrock` logger writes to the
console and to a midnight-rotating file `var/log/fundrock.log`
(`fundrock.dblogging.FileHandler`).

## Updating from new or changed files

`manager.update()` brings an existing database up to date with the cache folder
(it requires `set_up()` to have been run; otherwise it logs an `ERROR` and raises
`FileNotFoundError`). Each report stores its `source_file` name and the file's
modification time (`file_time_stamp`, UTC). Files not yet in the database are
added; files modified since they were stored replace their report; the rest are
skipped. A failing file is logged at `ERROR` and returned in `failed` (retried on
the next update). It returns an `UpdateResult` with `added`, `updated`,
`unchanged` and `failed` file lists. Reports whose files were removed are kept.

## Command line

Installing the package provides the `fundrock` command (also `python -m fundrock`):

```
fundrock --help | -h        show help
fundrock --version | -v     print the version
fundrock set-up             create a new, empty database (refuses if one exists)
fundrock tear-down          delete the database; asks you to type "please proceed" (or use --yes)
fundrock update             add new / modified NAV report files to the database
fundrock export-summary     write a portfolio's NAV Summary time series to NAVSummary-<code>-<date>.csv (--portfolio required, --sub-path optional)
```
