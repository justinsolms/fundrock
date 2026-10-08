"""Batch management for dated NAV report files."""

import datetime
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport, SummaryItem
from fundrock.nav_report_parser import ReportParser
from fundrock.path_utils import get_data_path, get_database_path, get_output_path

logger = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    """Outcome of NAVReportFileManager.update()."""

    added: list[Path] = field(default_factory=list)
    updated: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)
    failed: list[Path] = field(default_factory=list)

_REPORT_FILENAME = re.compile(
    r"NAV_[^_]+_(?P<report_date>\d{4}-\d{2}-\d{2})\.xlsx?",
    re.IGNORECASE,
)


class NAVReportFileManager:
    """Find and process dated NAV Excel reports from the data directory."""

    def __init__(
        self,
        db_connection_string: str | None = None,
        data_sub_path: str = "fundrock/nav_cache",
    ) -> None:
        if db_connection_string is None:
            database_path = Path(get_database_path("nav_database.db"))
            db_connection_string = f"sqlite:///{database_path}"
        self.db_connection_string = db_connection_string
        self.data_path = Path(get_data_path(data_sub_path))

    def _database_file(self) -> Path:
        """Return the SQLite database file path for the connection string."""
        url = make_url(self.db_connection_string)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
            raise ValueError(
                "set_up()/tear_down() support only file-based SQLite databases: "
                f"{self.db_connection_string}"
            )
        return Path(url.database)

    def database_exists(self) -> bool:
        """Return True if the database file exists."""
        return self._database_file().exists()

    def set_up(self) -> None:
        """Create a brand-new database with all NAV tables.

        Refuses, logging an ERROR and raising FileExistsError, if the database
        already exists; it must first be removed with tear_down().
        """
        database_file = self._database_file()
        if database_file.exists():
            message = (
                f"Database already exists: {database_file}. "
                "It must first be torn down with the tear_down() method."
            )
            logger.error(message)
            raise FileExistsError(message)
        database_file.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(self.db_connection_string)
        try:
            Base.metadata.create_all(engine)
        finally:
            engine.dispose()

    def tear_down(self) -> None:
        """Delete the database so that it no longer exists (idempotent)."""
        self._database_file().unlink(missing_ok=True)

    def find_report_files(self) -> list[Path]:
        """Return matching report files ordered by report date and filename."""
        if not self.data_path.is_dir():
            raise FileNotFoundError(f"NAV report directory not found: {self.data_path}")

        report_files: list[tuple[datetime.date, Path]] = []
        for file_path in self.data_path.iterdir():
            if not file_path.is_file():
                continue
            match = _REPORT_FILENAME.fullmatch(file_path.name)
            if match is None:
                continue
            try:
                report_date = datetime.date.fromisoformat(match.group("report_date"))
            except ValueError as error:
                raise ValueError(
                    f"Invalid report date in NAV filename: {file_path.name}"
                ) from error
            report_files.append((report_date, file_path))

        report_files.sort(key=lambda item: (item[0], item[1].name))
        return [file_path for _, file_path in report_files]

    def process_all_reports(self) -> list[Path]:
        """Process every dated NAV report found in the configured data directory."""
        report_files = self.find_report_files()
        for file_path in report_files:
            ReportParser.process_excel_file(
                file_path=str(file_path),
                db_connection_string=self.db_connection_string,
            )
        return report_files

    def update(self) -> UpdateResult:
        """Add new report files and refresh those modified since they were stored.

        Files are matched to reports by file name. A file absent from the
        database is added; one whose modification time is newer than the stored
        ``file_time_stamp`` replaces its report; others are skipped. A failing
        file is logged at ERROR, reported in ``failed`` and retried next time.
        """
        if not self.database_exists():
            message = (
                f"Database does not exist: {self._database_file()}. "
                "Create it first with the set_up() method."
            )
            logger.error(message)
            raise FileNotFoundError(message)

        engine = create_engine(self.db_connection_string)
        try:
            with Session(engine) as session:
                stored = dict(
                    session.execute(
                        select(NAVReport.source_file, NAVReport.file_time_stamp)
                    ).tuples().all()
                )
        finally:
            engine.dispose()

        result = UpdateResult()
        for file_path in self.find_report_files():
            file_time_stamp = ReportParser.file_time_stamp(file_path)
            if file_path.name not in stored:
                bucket = result.added
            elif (
                file_time_stamp is not None
                and (stored[file_path.name] is None or file_time_stamp > stored[file_path.name])
            ):
                bucket = result.updated
            else:
                result.unchanged.append(file_path)
                continue
            try:
                ReportParser.process_excel_file(
                    file_path=str(file_path),
                    db_connection_string=self.db_connection_string,
                )
            except Exception:
                logger.exception("Failed to process NAV report file: %s", file_path)
                result.failed.append(file_path)
            else:
                bucket.append(file_path)

        logger.info(
            "NAV update: %d added, %d updated, %d unchanged, %d failed",
            len(result.added),
            len(result.updated),
            len(result.unchanged),
            len(result.failed),
        )
        return result

    def nav_summary_frames(self, portfolio_code: str | None = None) -> dict[str, pd.DataFrame]:
        """Return each portfolio's NAV Summary time series, keyed by portfolio code.

        Each frame is indexed by a ``DatetimeIndex`` of ``report_date`` with one
        column per summary ``description`` holding ``current_market_value_base``.
        All portfolios are returned unless ``portfolio_code`` is given, in which
        case an unknown code raises ``ValueError``.
        """
        if not self.database_exists():
            message = (
                f"Database does not exist: {self._database_file()}. "
                "Create it first with the set_up() method."
            )
            logger.error(message)
            raise FileNotFoundError(message)

        query = (
            select(
                NAVReport.portfolio_code,
                NAVReport.report_date,
                SummaryItem.description,
                SummaryItem.current_market_value_base,
            )
            .join(SummaryItem, SummaryItem.report_id == NAVReport.id)
            .order_by(NAVReport.report_date, SummaryItem.id)
        )
        if portfolio_code is not None:
            query = query.where(NAVReport.portfolio_code == portfolio_code)

        engine = create_engine(self.db_connection_string)
        try:
            with Session(engine) as session:
                rows = session.execute(query).tuples().all()
        finally:
            engine.dispose()

        if portfolio_code is not None and not rows:
            raise ValueError(f"No NAV summary data for portfolio: {portfolio_code}")

        data = pd.DataFrame(
            rows,
            columns=["portfolio_code", "report_date", "description", "value"],
        )
        data["value"] = data["value"].astype(float)

        frames: dict[str, pd.DataFrame] = {}
        for code, group in data.groupby("portfolio_code"):
            frame = (
                group.drop_duplicates(["report_date", "description"])
                .pivot(index="report_date", columns="description", values="value")
                .sort_index()
            )
            frame.index = pd.DatetimeIndex(frame.index, name="report_date")
            frame.columns.name = None
            frames[str(code)] = frame
        return frames

    def write_nav_summary_csv(
        self,
        portfolio_code: str | None = None,
        sub_path: str | None = None,
    ) -> list[Path]:
        """Write each portfolio's NAV Summary time series to a CSV file.

        Uses :meth:`nav_summary_frames`. Files are named
        ``NAVSummary-<portfolio_code>-<latest report_date>.csv`` and written
        under ``get_output_path(sub_path)``. Returns the written paths.
        """
        frames = self.nav_summary_frames(portfolio_code)
        output_path = Path(get_output_path(sub_path))

        written: list[Path] = []
        for code, frame in frames.items():
            latest = frame.index.max().date().isoformat()
            file_path = output_path / f"NAVSummary-{code}-{latest}.csv"
            frame.to_csv(file_path)
            written.append(file_path)
        return written
