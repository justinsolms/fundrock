import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport
from fundrock.nav_report_parser import GroupParser, HeaderParser, ReportParser


class HeaderParserTest(unittest.TestCase):
    def test_reads_metadata_values_from_column_d_and_date_from_c3(self):
        dataframe = pd.DataFrame(
            [
                [None, None, None, None],
                [None, None, "NAV Breakdown Report", None],
                [None, None, "as at 03/08/2026", None],
                [None, None, None, None],
                [None, None, None, None],
                [None, None, "Portfolio Code:", 65713],
                [None, None, "Portfolio Name:", "BALANCED FUND"],
                [None, None, "Base Currency:", "ZAR"],
            ]
        )

        parsed_header = HeaderParser().parse(dataframe)

        self.assertEqual(
            parsed_header,
            {
                "report_date": datetime.date(2026, 8, 3),
                "portfolio_code": "65713",
                "portfolio_name": "BALANCED FUND",
                "base_currency": "ZAR",
            },
        )


class GroupParserTest(unittest.TestCase):
    def test_parses_holdings_instrument_subgroups_and_regular_groups(self):
        dataframe_rows: list[list[object | None]] = [
                [None, None, "CASH", None] + [None] * 16,
                [None, None, "CASH-001", "Cash holding"] + [None] * 16,
                [None, None, "CASH TOTAL", None] + [None] * 16,
                [None, None, "HOLDINGS AT MARKET VALUE", None] + [None] * 16,
                [None, None, "EQUITIES", None] + [None] * 16,
                [None, None, "EQ-001", "Equity holding"] + [None] * 16,
                [None, None, "FUNDS", None] + [None] * 16,
                [None, None, "FND-001", "Fund holding"] + [None] * 16,
                [None, None, "ALTERNATIVES", None] + [None] * 16,
                [None, None, "ALT-001", "Alternative holding"] + [None] * 16,
                [None, None, "HOLDINGS AT MARKET VALUE TOTAL", None] + [None] * 16,
                [None, None, "ACCRUED INCOME", None] + [None] * 16,
                [None, None, "INC-001", "Income item"] + [None] * 16,
                [None, None, "ACCRUED INCOME TOTAL", None] + [None] * 16,
        ]
        dataframe = pd.DataFrame(dataframe_rows)

        parsed_groups = GroupParser.extract_and_parse_all(dataframe)

        self.assertEqual(
            [
                (
                    group["group_label"],
                    group["instrument_type"],
                    [row["security_code"] for row in group["rows_data"]],
                )
                for group in parsed_groups
            ],
            [
                ("CASH", None, ["CASH-001"]),
                ("HOLDINGS AT MARKET VALUE", "EQUITIES", ["EQ-001"]),
                ("HOLDINGS AT MARKET VALUE", "FUNDS", ["FND-001"]),
                ("HOLDINGS AT MARKET VALUE", "ALTERNATIVES", ["ALT-001"]),
                ("ACCRUED INCOME", None, ["INC-001"]),
            ],
        )


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
                file_path = "NAV_65713_2026-09-29.xls"
                ReportParser.process_excel_file(file_path, connection_string)
                ReportParser.process_excel_file(file_path, connection_string)

            with Session(engine) as session:
                reports = session.scalars(select(NAVReport)).all()

            engine.dispose()

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].portfolio_name, "Updated name")

    def test_rejects_report_date_that_differs_from_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            connection_string = f"sqlite:///{Path(directory) / 'nav.db'}"
            report = NAVReport(
                portfolio_code="65713",
                report_date=datetime.date(2026, 8, 3),
            )
            with (
                patch("fundrock.nav_report_parser.pd.read_excel"),
                patch.object(ReportParser, "parse", return_value=report),
            ):
                with self.assertRaisesRegex(ValueError, "Report date mismatch"):
                    ReportParser.process_excel_file(
                        "NAV_65713_2026-08-04.xls",
                        connection_string,
                    )


if __name__ == "__main__":
    unittest.main()
