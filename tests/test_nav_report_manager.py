import tempfile
import datetime
import unittest
from pathlib import Path
from unittest.mock import call, patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport
from fundrock.nav_report_manager import NAVReportFileManager


class NAVReportFileManagerTest(unittest.TestCase):
    def test_tear_down_drops_database_tables_and_report_data(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "nav.db"
            connection_string = f"sqlite:///{database_path}"
            engine = create_engine(connection_string)
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                session.add(
                    NAVReport(
                        portfolio_code="65713",
                        report_date=datetime.date(2026, 9, 29),
                    )
                )
                session.commit()
            engine.dispose()

            with (
                patch("fundrock.nav_report_manager.get_data_path", return_value=directory),
                patch("fundrock.nav_report_manager.get_var_path", return_value=str(database_path)),
            ):
                manager = NAVReportFileManager(connection_string)

            manager.tear_down()

            engine = create_engine(connection_string)
            try:
                self.assertEqual(inspect(engine).get_table_names(), [])
            finally:
                engine.dispose()

    def test_default_database_is_created_under_var_directory(self):
        with (
            patch(
                "fundrock.nav_report_manager.get_var_path",
                return_value="/project/var/nav_database.db",
            ) as get_var_path,
            patch(
                "fundrock.nav_report_manager.get_data_path",
                return_value="/data/fundrock/nav_cache",
            ),
        ):
            manager = NAVReportFileManager()

        get_var_path.assert_called_once_with("nav_database.db")
        self.assertEqual(
            manager.db_connection_string,
            "sqlite:////project/var/nav_database.db",
        )

    def test_finds_dated_excel_reports_in_chronological_order(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory)
            filenames = (
                "NAV_65713_2026-09-29.xls",
                "NAV_65713_2026-09-28.xlsx",
                "NAV_65714_2026-09-29.XLS",
                "NAV_65713_2026-09-29-not-final.xls",
                "notes.txt",
            )
            for filename in filenames:
                (data_path / filename).touch()

            with patch(
                "fundrock.nav_report_manager.get_data_path",
                return_value=directory,
            ) as get_data_path:
                manager = NAVReportFileManager()
                report_files = manager.find_report_files()

        self.assertEqual(
            [file_path.name for file_path in report_files],
            [
                "NAV_65713_2026-09-28.xlsx",
                "NAV_65713_2026-09-29.xls",
                "NAV_65714_2026-09-29.XLS",
            ],
        )
        get_data_path.assert_called_once_with("fundrock/nav_cache")

    def test_processes_every_matching_report(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory)
            (data_path / "NAV_65713_2026-09-29.xls").touch()
            (data_path / "NAV_65713_2026-09-28.xls").touch()

            with (
                patch("fundrock.nav_report_manager.get_data_path", return_value=directory),
                patch(
                    "fundrock.nav_report_manager.ReportParser.process_excel_file"
                ) as process_excel_file,
            ):
                manager = NAVReportFileManager("sqlite:///test_nav.db")
                processed_files = manager.process_all_reports()

        self.assertEqual(
            [file_path.name for file_path in processed_files],
            ["NAV_65713_2026-09-28.xls", "NAV_65713_2026-09-29.xls"],
        )
        self.assertEqual(
            process_excel_file.call_args_list,
            [
                call(
                    file_path=str(data_path / "NAV_65713_2026-09-28.xls"),
                    db_connection_string="sqlite:///test_nav.db",
                ),
                call(
                    file_path=str(data_path / "NAV_65713_2026-09-29.xls"),
                    db_connection_string="sqlite:///test_nav.db",
                ),
            ],
        )

    def test_rejects_invalid_calendar_date_in_report_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "NAV_65713_2026-02-30.xls").touch()
            with patch(
                "fundrock.nav_report_manager.get_data_path",
                return_value=directory,
            ):
                manager = NAVReportFileManager()

            with self.assertRaisesRegex(ValueError, "Invalid report date"):
                manager.find_report_files()

    def test_reports_missing_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_path = str(Path(directory) / "missing")
            with patch(
                "fundrock.nav_report_manager.get_data_path",
                return_value=missing_path,
            ):
                manager = NAVReportFileManager()

            with self.assertRaisesRegex(FileNotFoundError, "NAV report directory"):
                manager.find_report_files()


if __name__ == "__main__":
    unittest.main()
