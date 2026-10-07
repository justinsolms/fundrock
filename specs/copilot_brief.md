Here is a comprehensive handover brief designed specifically for VSCode Copilot. You can copy and paste this directly into your Copilot Chat or save it as a `copilot_brief.md` file in your root directory to set the context for your upcoming coding sessions.

---

# Project Handover Brief: Fundrock NAV Report Parser

## Project Overview

**Fundrock** is a Python ETL (Extract, Transform, Load) pipeline designed to parse daily Net Asset Value (NAV) financial reports from Excel files (e.g., `NAV_65713_2026-09-29.xls`) into a structured relational database.

The pipeline uses `pandas` for raw file ingestion, custom object-oriented parsers to navigate irregular spreadsheet layouts, and SQLAlchemy 2.0 ORM to model and persist the complex hierarchical financial data.

## Architecture & Data Flow

1. **Ingestion:** Read the raw `.xls` file using `pandas.read_excel(..., header=None)`. The `header=None` parameter is critical because the report contains multiple sections (metadata, body, tail) and lacks a uniform column schema.
2. **Dynamic Chunking:** The `ReportParser` acts as a factory/orchestrator. It dynamically scans the dataframe for anchor keywords (e.g., `"SECURITY CODE"`, `"TOTAL NET ASSETS"`) to isolate the header, the body containing security groups, and the tail containing summaries and exchange rates.
3. **Parsing:** Specialized parsers (`HeaderParser`, `GroupParser`, etc.) extract data from their respective dataframe chunks and return standard Python dictionaries (`kwargs`).
4. **ORM Instantiation:** The dictionary outputs are passed directly into the default constructors of SQLAlchemy models.
5. **Persistence:** The root object (`NAVReport`) and its associated graph (`Groups`, `Rows`, `SummaryItems`, `ExchangeRateItems`) are committed to the database in a single atomic transaction.

## Module Map

**1. `src/fundrock/nav_report_classes.py` (Database Layer)**
Contains SQLAlchemy 2.0 declarative models using strict `Mapped` and `mapped_column` typing:

* `Base`: Declarative base class.
* `NAVReport`: The aggregate root container representing a single daily report.
* `Group`: Represents a portfolio asset category (e.g., 'CASH', 'EQUITIES'). Linked to `NAVReport`.
* `Row`: Represents an individual security holding. Linked to a `Group`. Uses `decimal.Decimal` / `Numeric` types to prevent floating-point errors.
* `SummaryItem` & `ExchangeRateItem`: Line items from the report tail. Linked to `NAVReport`.

**2. `src/fundrock/nav_report_parser.py` (ETL Layer)**
Contains the object-oriented parsing logic:

* `BaseParser`: Provides shared utilities like safe Pandas `NaN` to Python `None` or `Decimal` conversions.
* Block Parsers (`HeaderParser`, `GroupParser`, `NAVSummaryParser`, `ExchangeRatesParser`): Handle specific sections of the report.
* `ReportParser`: The master orchestrator containing `extract_body_dataframe()` and `process_excel_file()`.

**3. `src/fundrock/path_utils.py**`
Utility module for resolving file paths, ensuring the parsers can locate raw Excel files and the SQLite/database configurations.

**4. `tests/test_package.py**`
Placeholder for unit and integration testing.

## Important Context for Copilot

* **No SQLAlchemy Constructors Needed:** The parser classes intentionally return dictionaries so we rely entirely on SQLAlchemy's default constructors. Do not generate `__init__` methods for the ORM models.
* **Type Hinting:** Both `nav_report_classes.py` and `nav_report_parser.py` use strict Python type hints. Maintain this standard in all generated code.
* **Financial Math Precision:** Standard `float` types are banned for financial columns. Always use `decimal.Decimal` in Python and `Numeric` in SQLAlchemy.
* **Irregular Group Slicing:** The logic to find groups depends on checking if Column 3 (index 2) has a label while Column 4 (index 3) is empty, terminating when a row ends with "TOTAL".

## Immediate Next Steps / Implementation Queue

1. **Database Configuration:** Set up the database engine initialization (SQLite for local dev, PostgreSQL for production) and expose it via environment variables or a configuration file.
2. **Unit Testing (`test_package.py`):** Create Pytest fixtures that mock `pandas.DataFrame` slices to unit test the individual parsers (`RowParser`, `HeaderParser`) before writing integration tests for the full pipeline.
3. **CLI Entry Point:** Implement a command-line interface (e.g., using `argparse` or `click`) in `__init__.py` or a new `__main__.py` to allow the user to run `python -m fundrock /path/to/report.xls`.