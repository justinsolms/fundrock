"""Batch management for dated NAV report files."""

import datetime
import re
from pathlib import Path

from sqlalchemy import create_engine

from fundrock.nav_report_classes import Base
from fundrock.nav_report_parser import ReportParser
from fundrock.path_utils import get_data_path, get_var_path


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

    def tear_down(self) -> None:
        """Drop all NAV database tables and their stored data."""
        engine = create_engine(self.db_connection_string)
        try:
            Base.metadata.drop_all(engine)
        finally:
            engine.dispose()

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
