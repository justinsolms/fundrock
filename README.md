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
By default, the SQLite database is created at `var/nav_database.db`; a custom
database connection string can be passed to `NAVReportFileManager` when needed.
