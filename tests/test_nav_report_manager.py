import tempfile
import datetime
import unittest
from pathlib import Path
from unittest.mock import call, patch

from sqlalchemy import create_engine, inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport
from fundrock.nav_report_manager import NAVReportFileManager
from fundrock.nav_report_parser import ReportParser


def _fake_process(file_path, db_connection_string):
    name = Path(file_path).name
    engine = create_engine(db_connection_string)
    with Session(engine) as session:
        for old in session.scalars(select(NAVReport).where(NAVReport.source_file == name)):
            session.delete(old)
        session.flush()
        session.add(
            NAVReport(
                portfolio_code="65713",
                report_date=datetime.date.fromisoformat(name[10:20]),
                source_file=name,
                file_time_stamp=ReportParser.file_time_stamp(file_path),
            )
        )
        session.commit()
    engine.dispose()


class NAVReportFileManagerTest(unittest.TestCase):
    def _manager(self, directory):
        connection_string = f"sqlite:///{Path(directory) / 'sub' / 'nav.db'}"
        with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
            return NAVReportFileManager(connection_string)

    def test_update_adds_new_updates_modified_and_skips_unchanged(self):
        import os

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "NAV_65713_2026-08-03.xls"
            second = Path(directory) / "NAV_65713_2026-08-04.xls"
            first.write_text("a")
            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                manager = NAVReportFileManager(f"sqlite:///{Path(directory) / 'db' / 'nav.db'}")
            manager.set_up()
            with patch.object(ReportParser, "process_excel_file", side_effect=_fake_process):
                result = manager.update()
                self.assertEqual(result.added, [first])

                second.write_text("b")
                result = manager.update()
                self.assertEqual((result.added, result.unchanged), ([second], [first]))

                stat = first.stat()
                os.utime(first, (stat.st_atime, stat.st_mtime + 100))
                result = manager.update()
                self.assertEqual(
                    (result.updated, result.unchanged, result.added), ([first], [second], [])
                )

                result = manager.update()
                self.assertEqual(result.unchanged, [first, second])

    def test_update_reports_failed_file_and_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "NAV_65713_2026-08-03.xls"
            good = Path(directory) / "NAV_65713_2026-08-04.xls"
            bad.write_text("a")
            good.write_text("b")
            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                manager = NAVReportFileManager(f"sqlite:///{Path(directory) / 'db' / 'nav.db'}")
            manager.set_up()

            def process(file_path, db_connection_string):
                if Path(file_path) == bad:
                    raise ValueError("boom")
                _fake_process(file_path, db_connection_string)

            with patch.object(ReportParser, "process_excel_file", side_effect=process):
                with self.assertLogs("fundrock.nav_report_manager", "ERROR"):
                    result = manager.update()
        self.assertEqual((result.failed, result.added), ([bad], [good]))

    def test_update_refuses_when_database_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)
            with self.assertLogs("fundrock.nav_report_manager", "ERROR"):
                with self.assertRaises(FileNotFoundError):
                    manager.update()

    def test_set_up_creates_new_database_with_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)
            self.assertFalse(manager.database_exists())
            manager.set_up()
            self.assertTrue(manager.database_exists())
            engine = create_engine(manager.db_connection_string)
            try:
                self.assertIn("nav_reports", inspect(engine).get_table_names())
            finally:
                engine.dispose()

    def test_set_up_refuses_when_database_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)
            manager.set_up()
            with self.assertLogs("fundrock.nav_report_manager", "ERROR") as logs:
                with self.assertRaises(FileExistsError):
                    manager.set_up()
            self.assertIn("tear_down()", logs.output[0])

    def test_tear_down_removes_database_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(directory)
            manager.set_up()
            engine = create_engine(manager.db_connection_string)
            with Session(engine) as session:
                session.add(
                    NAVReport(portfolio_code="65713", report_date=datetime.date(2026, 9, 29))
                )
                session.commit()
            engine.dispose()
            manager.tear_down()
            self.assertFalse(manager.database_exists())
            manager.tear_down()
            manager.set_up()
            self.assertTrue(manager.database_exists())

    def test_set_up_rejects_in_memory_database(self):
        with patch("fundrock.nav_report_manager.get_data_path", return_value="/tmp"):
            manager = NAVReportFileManager("sqlite:///:memory:")
        with self.assertRaises(ValueError):
            manager.set_up()

    def test_default_database_is_created_under_var_directory(self):
        with (
            patch(
                "fundrock.nav_report_manager.get_database_path",
                return_value="/project/var/db/nav_database.db",
            ) as get_database_path,
            patch(
                "fundrock.nav_report_manager.get_data_path",
                return_value="/data/fundrock/nav_cache",
            ),
        ):
            manager = NAVReportFileManager()

        get_database_path.assert_called_once_with("nav_database.db")
        self.assertEqual(
            manager.db_connection_string,
            "sqlite:////project/var/db/nav_database.db",
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


class WriteNavSummaryCsvTest(unittest.TestCase):
    def test_writes_time_series_csv_per_portfolio(self):
        import pandas as pd
        from fundrock.nav_report_classes import SummaryItem

        with tempfile.TemporaryDirectory() as directory:
            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                manager = NAVReportFileManager(f"sqlite:///{Path(directory) / 'nav.db'}")
            manager.set_up()
            engine = create_engine(manager.db_connection_string)
            with Session(engine) as session:
                for day, a, b in [(2, 10, 1), (1, 8, 2)]:
                    session.add(NAVReport(
                        portfolio_code="P1",
                        report_date=datetime.date(2026, 1, day),
                        summary_items=[
                            SummaryItem(description="Cash", current_market_value_base=a),
                            SummaryItem(description="Equity", current_market_value_base=b),
                        ],
                    ))
                session.commit()
            engine.dispose()

            out = Path(directory) / "out"
            with patch("fundrock.nav_report_manager.get_output_path", return_value=str(out)):
                out.mkdir()
                paths = manager.write_nav_summary_csv()
                with self.assertRaises(ValueError):
                    manager.write_nav_summary_csv("nope")

            self.assertEqual([p.name for p in paths], ["NAVSummary-P1-2026-01-02.csv"])
            frame = pd.read_csv(paths[0], index_col=0, parse_dates=True)
            self.assertIsInstance(frame.index, pd.DatetimeIndex)
            self.assertEqual(list(frame.columns), ["Cash", "Equity"])
            self.assertEqual(frame["Cash"].tolist(), [8, 10])

            frames = manager.nav_summary_frames()
            self.assertEqual(list(frames), ["P1"])
            self.assertIsInstance(frames["P1"].index, pd.DatetimeIndex)
            self.assertEqual(frames["P1"]["Equity"].tolist(), [2, 1])
