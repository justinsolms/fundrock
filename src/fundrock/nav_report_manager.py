"""Batch management for dated NAV report files."""

import datetime
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

import holidays
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport
from fundrock.nav_report_parser import ReportParser
from fundrock.path_utils import get_data_path, get_database_path

logger = logging.getLogger(__name__)


class PortfolioStatus(TypedDict):
    first_date: datetime.date
    last_date: datetime.date
    up_to_date: bool
    missing_business_days: list[datetime.date]


class NAVStatus(TypedDict):
    report_count: int
    portfolio_count: int
    first_date: datetime.date | None
    last_date: datetime.date | None
    expected_last_date: datetime.date
    up_to_date: bool
    portfolios: dict[str, PortfolioStatus]
    missing_business_days: dict[str, list[datetime.date]]


@dataclass
class UpdateResult:
    """Outcome of NAVReportFileManager.update()."""

    added: list[Path] = field(default_factory=list[Path])
    updated: list[Path] = field(default_factory=list[Path])
    unchanged: list[Path] = field(default_factory=list[Path])
    failed: list[Path] = field(default_factory=list[Path])
    missing_business_days: dict[str, list[datetime.date]] = field(default_factory=dict[str, list[datetime.date]])

_REPORT_FILENAME = re.compile(
    r"NAV_[^_]+_(?P<report_date>\d{4}-\d{2}-\d{2})\.xlsx?",
    re.IGNORECASE,
)


class NAVReportFileManager:
    """Find and process dated NAV Excel reports from the data directory.

    ``COUNTRY_CODE`` selects the country used for public-holiday calculations.
    """

    COUNTRY_CODE = "ZA"

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

    @classmethod
    def _holidays(cls, first_year: int, last_year: int) -> holidays.HolidayBase:
        return holidays.country_holidays(cls.COUNTRY_CODE, years=range(first_year, last_year + 1))

    @classmethod
    def is_business_day(cls, day: datetime.date) -> bool:
        """Return whether ``day`` is neither a weekend nor a public holiday."""
        return day.weekday() < 5 and day not in cls._holidays(day.year, day.year)

    @classmethod
    def previous_business_day(cls, today: datetime.date | None = None) -> datetime.date:
        """Return the business day before ``today`` for ``COUNTRY_CODE``."""
        today = today or datetime.date.today()
        public_holidays = cls._holidays(today.year - 1, today.year)
        day = today - datetime.timedelta(days=1)
        while day.weekday() >= 5 or day in public_holidays:
            day -= datetime.timedelta(days=1)
        return day

    def report_dates(self) -> dict[str, list[datetime.date]]:
        """Return the sorted distinct stored report dates for each portfolio."""
        engine = create_engine(self.db_connection_string)
        try:
            with Session(engine) as session:
                rows = session.execute(
                    select(NAVReport.portfolio_code, NAVReport.report_date)
                    .distinct()
                    .order_by(NAVReport.portfolio_code, NAVReport.report_date)
                ).tuples().all()
        finally:
            engine.dispose()
        dates: dict[str, list[datetime.date]] = {}
        for code, value in rows:
            day = value.date() if isinstance(value, datetime.datetime) else value
            dates.setdefault(code, []).append(day)
        return dates

    def continuity_test(self, today: datetime.date | None = None) -> dict[str, list[datetime.date]]:
        """Return, per portfolio, the business days lacking a NAV report.

        Each portfolio is checked from its own earliest stored report date to
        the previous business day before ``today``, warning for each gap.
        Missing days at the end of a range mean that portfolio is not up to
        date. Portfolios with no gaps are omitted; an empty database has none.
        """
        if not self.database_exists():
            raise FileNotFoundError(f"Database does not exist: {self._database_file()}")
        end = self.previous_business_day(today)
        missing: dict[str, list[datetime.date]] = {}
        for code, dates in self.report_dates().items():
            stored = set(dates)
            public_holidays = self._holidays(dates[0].year, max(end.year, dates[-1].year))
            gaps: list[datetime.date] = []
            day = dates[0]
            while day <= end:
                if day.weekday() < 5 and day not in public_holidays and day not in stored:
                    gaps.append(day)
                day += datetime.timedelta(days=1)
            for day in gaps:
                logger.warning(
                    "NAV continuity: portfolio %s has no report for business day %s",
                    code,
                    day.isoformat(),
                )
            if gaps:
                missing[code] = gaps
        return missing

    def status(self, today: datetime.date | None = None) -> NAVStatus:
        """Return database metrics and the per-portfolio continuity result."""
        missing = self.continuity_test(today)
        engine = create_engine(self.db_connection_string)
        try:
            with Session(engine) as session:
                report_count = session.execute(select(func.count(NAVReport.id))).scalar() or 0
        finally:
            engine.dispose()
        dates = self.report_dates()
        expected = self.previous_business_day(today)
        portfolios: dict[str, PortfolioStatus] = {
            code: {
                "first_date": days[0],
                "last_date": days[-1],
                "up_to_date": days[-1] >= expected,
                "missing_business_days": missing.get(code, []),
            }
            for code, days in dates.items()
        }
        all_days = [day for days in dates.values() for day in days]
        return {
            "report_count": report_count,
            "portfolio_count": len(portfolios),
            "first_date": min(all_days) if all_days else None,
            "last_date": max(all_days) if all_days else None,
            "expected_last_date": expected,
            "up_to_date": bool(portfolios) and all(p["up_to_date"] for p in portfolios.values()),
            "portfolios": portfolios,
            "missing_business_days": missing,
        }

    def is_complete_and_up_to_date(self, today: datetime.date | None = None) -> bool:
        """Return whether every stored portfolio is current and has no gaps."""
        status = self.status(today)
        return status["up_to_date"] and not status["missing_business_days"]

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
            else:
                stored_time = stored[file_path.name]
                if file_time_stamp is not None and (stored_time is None or file_time_stamp > stored_time):
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

        result.missing_business_days = self.continuity_test()

        logger.info(
            "NAV update: %d added, %d updated, %d unchanged, %d failed",
            len(result.added),
            len(result.updated),
            len(result.unchanged),
            len(result.failed),
        )
        return result
