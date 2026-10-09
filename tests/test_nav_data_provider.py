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
            self.assertEqual(path.name, "NAVSummary-P1-2026-01-02.csv")
            written = pd.read_csv(path, index_col=0, parse_dates=True)
            self.assertEqual(written["Cash"].tolist(), [8, 10])

            with patch("fundrock.nav_report_manager.get_data_path", return_value=directory):
                unknown = NAVDataProvider("nope", connection_string)
            with self.assertRaises(ValueError):
                unknown.nav_summary_frames()


if __name__ == "__main__":
    unittest.main()
