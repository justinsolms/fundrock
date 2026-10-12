"""Present data items from the NAV reports stored in the database."""

import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import NAVReport, SummaryItem
from fundrock.nav_report_manager import NAVReportFileManager
from fundrock.path_utils import get_output_path

logger = logging.getLogger(__name__)


class NAVDataProvider:
    """Provide data from one portfolio's stored :class:`NAVReport` instances.

    Business days and holidays come from :class:`NAVReportFileManager`.
    Database-wide completeness is available through
    :meth:`is_complete_and_up_to_date`.

    Parameters
    ----------
    portfolio_code : str
        Portfolio code used by portfolio-specific data methods.
    db_connection_string : str, optional
        SQLAlchemy database connection string. When omitted, the manager's
        default database is used.
    """

    def __init__(self, portfolio_code: str, db_connection_string: str | None = None) -> None:
        """Initialize the provider.

        Parameters
        ----------
        portfolio_code : str
            Portfolio code for portfolio-specific data methods.
        db_connection_string : str, optional
            SQLAlchemy database connection string. When omitted, the manager's
            default database is used.
        """
        self.portfolio_code = portfolio_code
        self._manager = NAVReportFileManager(db_connection_string)
        self.db_connection_string = self._manager.db_connection_string

    def nav_summary_frames(self) -> pd.DataFrame:
        """Return the portfolio's NAV Summary time series as a DataFrame.

        The DataFrame has one row per report date, sorted oldest to newest. Its
        ``DatetimeIndex`` is named ``report_date``. Each column is a distinct
        NAV Summary item ``description``; each cell is that item's
        ``current_market_value_base`` for the date, converted to a float.
        Descriptions are not otherwise normalized, so their spelling and
        punctuation are the column labels. If a description is absent from a
        report, that date/column cell is ``NaN``. Duplicate items with the same
        report date and description are reduced to the first stored item.

        Example
        -------
        .. code-block:: python

           frame = provider.nav_summary_frames()
           cash_by_date = frame["Cash"]
           latest_report = frame.loc[frame.index.max()]

        Returns
        -------
        pandas.DataFrame
            Wide-form NAV summary values indexed by ``report_date``, with one
            float-valued column per item description.

        Raises
        ------
        FileNotFoundError
            If the database does not exist.
        ValueError
            If the portfolio has no NAV summary data.
        """
        if not self._manager.database_exists():
            message = (
                "Database does not exist. Create it first with the set_up() method."
            )
            logger.error(message)
            raise FileNotFoundError(message)

        query = (
            select(
                NAVReport.report_date,
                SummaryItem.description,
                SummaryItem.current_market_value_base,
            )
            .join(SummaryItem, SummaryItem.report_id == NAVReport.id)
            .where(NAVReport.portfolio_code == self.portfolio_code)
            .order_by(NAVReport.report_date, SummaryItem.id)
        )

        engine = create_engine(self.db_connection_string)
        try:
            with Session(engine) as session:
                rows = session.execute(query).tuples().all()
        finally:
            engine.dispose()

        if not rows:
            raise ValueError(f"No NAV summary data for portfolio: {self.portfolio_code}")

        data = pd.DataFrame(rows, columns=["report_date", "description", "value"])
        data["value"] = data["value"].astype(float)
        frame = (
            data.drop_duplicates(["report_date", "description"])
            .pivot(index="report_date", columns="description", values="value")
            .sort_index()
        )
        frame.index = pd.DatetimeIndex(frame.index, name="report_date")
        frame.columns.name = None
        return frame

    def write_nav_summary_csv(self, sub_path: str | None = None) -> Path:
        """Write the portfolio's NAV Summary time series to CSV.

        The CSV contains the same rows and summary-item columns as
        :meth:`nav_summary_frames`. The named ``report_date`` index is included
        as the first CSV column; dates are serialized by pandas, and missing
        item values are empty CSV fields. The filename is
        ``NAVSummaryHistory-<portfolio_code>-<latest report_date>.csv``, where
        the latest date is formatted as ``YYYY-MM-DD``. By default the file is
        placed under ``~/Downloads``. ``sub_path`` adds a directory under that
        output directory; the directory is created if necessary.

        Example
        -------
        .. code-block:: python

           path = provider.write_nav_summary_csv(sub_path="fundrock")
           # For portfolio "65713", returns a path ending in
           # NAVSummaryHistory-65713-2026-10-09.csv

        Parameters
        ----------
        sub_path : str, optional
            Output subdirectory relative to ``~/Downloads``. It must be a
            directory path, not a filename (a path with a file suffix raises
            ``ValueError``).

        Returns
        -------
        pathlib.Path
            Path to the written CSV file, including its filename.

        Raises
        ------
        FileNotFoundError
            If the database does not exist.
        ValueError
            If the portfolio has no NAV summary data.
        """
        frame = self.nav_summary_frames()
        latest = frame.index.max().date().isoformat()
        file_path = Path(get_output_path(sub_path)) / f"NAVSummaryHistory-{self.portfolio_code}-{latest}.csv"
        frame.to_csv(file_path)
        return file_path

    def last_date(self) -> date | None:
        """Return the latest ``report_date`` stored for the portfolio.

        Returns
        -------
        datetime.date or None
            Latest report date, or ``None`` if the portfolio has no reports.

        Raises
        ------
        FileNotFoundError
            If the database does not exist.
        """
        if not self._manager.database_exists():
            message = (
                "Database does not exist. Create it first with the set_up() method."
            )
            logger.error(message)
            raise FileNotFoundError(message)

        query = select(func.max(NAVReport.report_date)).where(
            NAVReport.portfolio_code == self.portfolio_code
        )
        engine = create_engine(self.db_connection_string)
        try:
            with Session(engine) as session:
                result = session.execute(query).scalar()
        finally:
            engine.dispose()

        if result is None:
            return None
        return result.date() if isinstance(result, datetime) else result

    def is_complete_and_up_to_date(self, today: date | None = None) -> bool:
        """Return whether the database is complete and up to date.

        Checks all portfolios in the database, not only this provider's
        ``portfolio_code``.

        Parameters
        ----------
        today : datetime.date, optional
            Date used to determine the previous business day. Defaults to the
            current date.

        Returns
        -------
        bool
            ``True`` if every stored portfolio is current and has no missing
            business days; otherwise ``False``.

        Raises
        ------
        FileNotFoundError
            If the database does not exist.
        """
        return self._manager.is_complete_and_up_to_date(today)
