import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport
from fundrock.nav_report_parser import ReportParser


class ReportParserPersistenceTest(unittest.TestCase):
    def test_reprocessing_a_report_replaces_the_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "nav.db"
            connection_string = f"sqlite:///{database_path}"
            engine = create_engine(connection_string)
            Base.metadata.create_all(engine)

            def parsed_report(portfolio_name: str) -> NAVReport:
                return NAVReport(
                    portfolio_code="65713",
                    portfolio_name=portfolio_name,
                    base_currency="USD",
                    report_date=datetime.date(2026, 9, 29),
                )

            with (
                patch("fundrock.nav_report_parser.pd.read_excel"),
                patch.object(
                    ReportParser,
                    "parse",
                    side_effect=(parsed_report("Old name"), parsed_report("Updated name")),
                ),
            ):
                ReportParser.process_excel_file("report.xls", connection_string)
                ReportParser.process_excel_file("report.xls", connection_string)

            with Session(engine) as session:
                reports = session.scalars(select(NAVReport)).all()

            engine.dispose()

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].portfolio_name, "Updated name")


if __name__ == "__main__":
    unittest.main()
