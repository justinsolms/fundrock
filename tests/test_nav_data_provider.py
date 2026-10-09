import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fundrock.nav_data_provider import NAVDataProvider
from fundrock.nav_report_classes import NAVReport, SummaryItem
from fundrock.nav_report_manager import NAVReportFileManager


class NAVDataProviderTest(unittest.TestCase):
    def test_summary_frame_and_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            connection_string = f"sqlite:///{Path(directory) / 'nav.db'}"
            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                NAVReportFileManager(connection_string).set_up()
            engine = create_engine(connection_string)
            with Session(engine) as session:
                for code in ("P1", "P2"):
                    for day, a, b in [(2, 10, 1), (1, 8, 2)]:
                        session.add(NAVReport(
                            portfolio_code=code,
                            report_date=datetime.date(2026, 1, day),
                            summary_items=[
                                SummaryItem(description="Cash", current_market_value_base=a),
                                SummaryItem(description="Equity", current_market_value_base=b),
                            ],
                        ))
                session.commit()
            engine.dispose()

            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                provider = NAVDataProvider("P1", connection_string)
            frame = provider.nav_summary_frames()
            self.assertIsInstance(frame.index, pd.DatetimeIndex)
            self.assertEqual(list(frame.columns), ["Cash", "Equity"])
            self.assertEqual(frame["Equity"].tolist(), [2, 1])

            out = Path(directory) / "out"
            out.mkdir()
            with patch("fundrock.nav_data_provider.get_output_path", return_value=str(out)):
                path = provider.write_nav_summary_csv()
            self.assertEqual(path.name, "NAVSummaryHistory-P1-2026-01-02.csv")
            written = pd.read_csv(path, index_col=0, parse_dates=True)
            self.assertEqual(written["Cash"].tolist(), [8, 10])

            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                unknown = NAVDataProvider("nope", connection_string)
            with self.assertRaises(ValueError):
                unknown.nav_summary_frames()

    def _provider(self, directory, code="P1", dates=()):
        connection_string = f"sqlite:///{Path(directory) / 'nav.db'}"
        with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
            NAVReportFileManager(connection_string).set_up()
        engine = create_engine(connection_string)
        with Session(engine) as session:
            for day in dates:
                session.add(NAVReport(portfolio_code="P1", report_date=day))
            session.commit()
        engine.dispose()
        with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
            return NAVDataProvider(code, connection_string)

    def test_previous_business_day(self):
        previous = NAVDataProvider.previous_business_day
        # Monday -> Friday
        self.assertEqual(previous(datetime.date(2026, 10, 12)), datetime.date(2026, 10, 9))
        # Tuesday -> Monday
        self.assertEqual(previous(datetime.date(2026, 10, 13)), datetime.date(2026, 10, 12))
        # Day after New Year's Day (Fri 2026-01-02) -> Wed 2025-12-31
        self.assertEqual(previous(datetime.date(2026, 1, 2)), datetime.date(2025, 12, 31))
        # Day after Christmas Day 25 Dec and Day of Goodwill 26 Dec (Mon 2026-12-28) -> Thu 24 Dec
        self.assertEqual(previous(datetime.date(2026, 12, 28)), datetime.date(2026, 12, 24))

    def test_last_date_and_up_to_date(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = self._provider(
                directory, dates=[datetime.date(2026, 10, 8), datetime.date(2026, 10, 9)]
            )
            self.assertEqual(provider.last_date(), datetime.date(2026, 10, 9))
            self.assertTrue(provider.is_up_to_date(datetime.date(2026, 10, 12)))
            self.assertFalse(provider.is_up_to_date(datetime.date(2026, 10, 13)))

    def test_empty_and_missing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = self._provider(directory, code="nope", dates=[datetime.date(2026, 10, 9)])
            self.assertIsNone(provider.last_date())
            self.assertFalse(provider.is_up_to_date(datetime.date(2026, 10, 12)))
        with tempfile.TemporaryDirectory() as directory:
            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                provider = NAVDataProvider("P1", f"sqlite:///{Path(directory) / 'none.db'}")
            with self.assertRaises(FileNotFoundError):
                provider.last_date()


if __name__ == "__main__":
    unittest.main()
