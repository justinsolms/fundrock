"""Present data items from the NAV reports stored in the database."""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import NAVReport, SummaryItem
from fundrock.nav_report_manager import NAVReportFileManager
from fundrock.path_utils import get_output_path

logger = logging.getLogger(__name__)


class NAVDataProvider:
    """Provide data from the stored :class:`NAVReport` instances of one portfolio."""

    def __init__(self, portfolio_code: str, db_connection_string: str | None = None) -> None:
        self.portfolio_code = portfolio_code
        self._manager = NAVReportFileManager(db_connection_string)
        self.db_connection_string = self._manager.db_connection_string

    def nav_summary_frames(self) -> pd.DataFrame:
        """Return the portfolio's NAV Summary time series.

        The frame is indexed by a ``DatetimeIndex`` of ``report_date`` with one
        column per summary ``description`` holding ``current_market_value_base``.
        An unknown portfolio code raises ``ValueError``.
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
        """Write the portfolio's NAV Summary time series to a CSV file.

        Uses :meth:`nav_summary_frames`. The file is named
        ``NAVSummary-<portfolio_code>-<latest report_date>.csv`` and written
        under ``get_output_path(sub_path)``. Returns the written path.
        """
        frame = self.nav_summary_frames()
        latest = frame.index.max().date().isoformat()
        file_path = Path(get_output_path(sub_path)) / f"NAVSummary-{self.portfolio_code}-{latest}.csv"
        frame.to_csv(file_path)
        return file_path
