"""Batch management for dated NAV report files."""

import datetime
import logging
import re
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from fundrock.nav_report_classes import Base
from fundrock.nav_report_parser import ReportParser
from fundrock.path_utils import get_data_path, get_var_path

logger = logging.getLogger(__name__)

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
            database_path = Path(get_var_path("nav_database.db"))
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
