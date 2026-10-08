import datetime
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, Group, NAVReport, SummaryItem
from fundrock.nav_report_parser import (
    GroupParser,
    HeaderParser,
    NAVSummaryParser,
    ReportParser,
)


def _excel_row(
    label: str | None = None,
    description: str | None = None,
    values: dict[int, object] | None = None,
) -> list[object | None]:
    row: list[object | None] = [None] * 20
    if label is not None:
        row[2] = label
    if description is not None:
        row[3] = description
    if values is not None:
        for column, value in values.items():
            row[column] = value
    return row


def _report_dataframe(
    body_rows: list[list[object | None]],
    total_net_assets_values: dict[int, object] | None = None,
    summary_rows: list[list[object | None]] | None = None,
) -> pd.DataFrame:
    rows = [_excel_row() for _ in range(10)]
    rows[2][2] = "as at 07/08/2026"
    rows[5][2] = "Portfolio Code:"
    rows[5][3] = 65713
    rows[6][2] = "Portfolio Name:"
    rows[6][3] = "BALANCED FUND"
    rows[7][2] = "Base Currency:"
    rows[7][3] = "ZAR"
    rows[9][2] = "Security Code"
    rows.extend(body_rows)
    rows.append(_excel_row("TOTAL NET ASSETS", values=total_net_assets_values))
    rows.append(_excel_row("NAV Summary"))
    rows.append(_excel_row("BASE CURRENCY"))
    rows.extend(summary_rows or [])
    rows.append(_excel_row("Calculated NAV Value Difference"))
    return pd.DataFrame(rows)


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


class NAVSummaryParserTest(unittest.TestCase):
    def test_parses_variable_summary_lines_in_input_order_and_stops_at_end_marker(self):
        rows = [
            _excel_row("TOTAL NET ASSETS", values={13: 100}),
            _excel_row("NAV Summary"),
            _excel_row("BASE CURRENCY"),
            _excel_row(
                "NET INCOME",
                values={13: -10, 14: -12, 15: -2, 17: -0.1},
            ),
            _excel_row(
                "TOTAL CLASS SHARES IN ISSUE",
                values={13: 20, 14: 22, 15: 2},
            ),
            _excel_row(
                "TOTAL NET ASSETS FOR CLASS - ISBFA",
                values={13: 100, 14: 110, 15: 10},
            ),
            _excel_row("Calculated NAV Value Difference", values={13: 0}),
            _excel_row("EXCHANGE RATES"),
            _excel_row("ZAR:USD", values={13: 0.06, 14: 0.07, 15: 0.01, 17: 0.1}),
        ]

        parsed_items = NAVSummaryParser().parse_block(
            [pd.Series(row) for row in rows]
        )

        self.assertEqual(
            parsed_items,
            [
                {
                    "description": "NET INCOME",
                    "prior_market_value_base": Decimal("-10"),
                    "current_market_value_base": Decimal("-12"),
                    "market_value_base_change": Decimal("-2"),
                    "market_value_percent_change": Decimal("-0.1"),
                },
                {
                    "description": "TOTAL CLASS SHARES IN ISSUE",
                    "prior_market_value_base": Decimal("20"),
                    "current_market_value_base": Decimal("22"),
                    "market_value_base_change": Decimal("2"),
                    "market_value_percent_change": None,
                },
                {
                    "description": "TOTAL NET ASSETS FOR CLASS",
                    "prior_market_value_base": Decimal("100"),
                    "current_market_value_base": Decimal("110"),
                    "market_value_base_change": Decimal("10"),
                    "market_value_percent_change": None,
                },
            ],
        )

    def test_requires_ordered_summary_boundaries(self):
        with self.assertRaisesRegex(ValueError, "ordered 'NAV Summary'"):
            NAVSummaryParser().parse_block(
                [pd.Series(_excel_row("NET INCOME"))]
            )

    def test_report_parser_creates_summary_item_instances_for_variable_rows(self):
        dataframe = _report_dataframe(
            [_excel_row("CASH"), _excel_row("CASH TOTAL")],
            summary_rows=[
                _excel_row(
                    "NET INCOME",
                    values={13: -10, 14: -12, 15: -2, 17: -0.1},
                ),
                _excel_row(
                    "CAPITAL VALUE",
                    values={13: 20, 14: 22, 15: 2, 17: 0.1},
                ),
            ],
        )

        report = ReportParser.parse(dataframe)

        self.assertEqual(
            [item.description for item in report.summary_items],
            ["NET INCOME", "CAPITAL VALUE"],
        )
        self.assertTrue(all(type(item) is SummaryItem for item in report.summary_items))
        self.assertEqual(report.summary_items[0].prior_market_value_base, Decimal("-10"))
        self.assertEqual(report.summary_items[0].current_market_value_base, Decimal("-12"))
        self.assertEqual(report.summary_items[0].market_value_base_change, Decimal("-2"))
        self.assertEqual(
            report.summary_items[0].market_value_percent_change,
            Decimal("-0.1"),
        )


class GroupParserTest(unittest.TestCase):
    def test_parses_holdings_instrument_subgroups_and_regular_groups(self):
        dataframe = pd.DataFrame(
            [
                _excel_row("CASH"),
                _excel_row(
                    "CASH-001",
                    "Cash holding",
                    {12: 1, 13: 10, 14: 12, 15: 2, 19: 25},
                ),
                _excel_row(
                    "CASH TOTAL",
                    values={12: 1, 13: 10, 14: 12, 15: 2, 19: 0.25},
                ),
                _excel_row("HOLDINGS AT MARKET VALUE"),
                _excel_row("EQUITIES"),
                _excel_row(
                    "EQ-001",
                    "Equity holding",
                    {12: 2, 13: 100, 14: 90, 15: -10, 19: 30},
                ),
                _excel_row("FUNDS"),
                _excel_row(
                    "FND-001",
                    "Fund holding",
                    {12: 3, 13: 200, 14: 180, 15: -20, 19: 50},
                ),
                _excel_row("ALTERNATIVES"),
                _excel_row(
                    "ALT-001",
                    "Alternative holding",
                    {12: 0, 13: 0, 14: 0, 15: 0, 19: 0},
                ),
                _excel_row(
                    "HOLDINGS AT MARKET VALUE TOTAL",
                    values={12: 5, 13: 300, 14: 270, 15: -30, 19: 0.8},
                ),
                _excel_row("ACCRUED INCOME"),
                _excel_row(
                    "INC-001",
                    "Income item",
                    {12: 0, 13: 5, 14: 6, 15: 1, 19: 0},
                ),
                _excel_row(
                    "ACCRUED INCOME TOTAL",
                    values={12: 0, 13: 5, 14: 6, 15: 1, 19: 0},
                ),
            ]
        )

        parsed_groups = GroupParser.extract_and_parse_all(dataframe)

        cash, holdings_parent, accrued_income = parsed_groups
        self.assertEqual(cash["group_label"], "CASH")
        self.assertIsNone(cash["instrument_type"])
        self.assertEqual(cash["total_prior_market_value_base"], 10)
        self.assertEqual(cash["validation_mismatches"], [])

        self.assertEqual(holdings_parent["group_label"], "HOLDINGS AT MARKET VALUE")
        self.assertNotIn("rows_data", holdings_parent)
        self.assertEqual(holdings_parent["total_prior_market_value_base"], 300)
        self.assertEqual(holdings_parent["validation_mismatches"], [])
        self.assertEqual(
            [
                (
                    child["group_label"],
                    child["instrument_type"],
                    [row["security_code"] for row in child["rows_data"]],
                    child["validation_mismatches"],
                )
                for child in holdings_parent["child_groups"]
            ],
            [
                ("HOLDINGS AT MARKET VALUE", "EQUITIES", ["EQ-001"], []),
                ("HOLDINGS AT MARKET VALUE", "FUNDS", ["FND-001"], []),
                ("HOLDINGS AT MARKET VALUE", "ALTERNATIVES", ["ALT-001"], []),
            ],
        )
        self.assertEqual(accrued_income["group_label"], "ACCRUED INCOME")
        self.assertEqual(accrued_income["total_current_market_value_base"], 6)
        self.assertEqual(accrued_income["validation_mismatches"], [])

    def test_percentage_validation_normalizes_and_allows_display_rounding(self):
        row = _excel_row("SEC-001", "Security", {19: 0.49})
        total = _excel_row("TEST TOTAL", values={19: 0.0048})

        parsed_group = GroupParser().parse_group(
            "TEST", [pd.Series(row)], total_row=pd.Series(total)
        )

        self.assertEqual(parsed_group["validation_mismatches"], [])

    def test_percentage_validation_reports_difference_outside_rounding_tolerance(self):
        row = _excel_row("SEC-001", "Security", {19: 0.5})
        total = _excel_row("TEST TOTAL", values={19: 0.0048})

        parsed_group = GroupParser().parse_group(
            "TEST", [pd.Series(row)], total_row=pd.Series(total)
        )

        self.assertEqual(
            parsed_group["validation_mismatches"],
            [
                {
                    "field": "total_percent_of_market_value",
                    "expected": Decimal("0.005"),
                    "actual": Decimal("0.0048"),
                }
            ],
        )

    def test_skips_validation_when_detail_column_is_entirely_blank(self):
        parsed_group = GroupParser().parse_group(
            "TEST",
            [pd.Series(_excel_row("SEC-001", "Security"))],
            total_row=pd.Series(_excel_row("TEST TOTAL")),
        )

        self.assertEqual(parsed_group["validation_mismatches"], [])

    def test_reports_mismatch_when_total_value_is_missing(self):
        parsed_group = GroupParser().parse_group(
            "TEST",
            [pd.Series(_excel_row("SEC-001", "Security", {12: 5}))],
        )

        self.assertEqual(
            parsed_group["validation_mismatches"],
            [
                {
                    "field": "total_current_book_value_base",
                    "expected": 5,
                    "actual": None,
                }
            ],
        )

    def test_validates_report_total_against_group_totals(self):
        groups = [
            {
                "total_current_book_value_base": Decimal("100"),
                "total_prior_market_value_base": Decimal("10"),
                "total_current_market_value_base": Decimal("12"),
                "total_market_value_base_change": Decimal("2"),
                "total_percent_of_market_value": Decimal("0.25"),
            },
            {
                "total_current_book_value_base": Decimal("200"),
                "total_prior_market_value_base": Decimal("20"),
                "total_current_market_value_base": Decimal("24"),
                "total_market_value_base_change": Decimal("4"),
                "total_percent_of_market_value": Decimal("0.50"),
            },
        ]
        total_row = pd.Series(
            _excel_row(
                "TOTAL NET ASSETS",
                values={12: 0, 13: 30, 14: 36, 15: 6, 19: 0.75},
            )
        )

        self.assertEqual(
            GroupParser._validate_report_total(groups, total_row),
            [],
        )

        incorrect_percentage_row = pd.Series(
            _excel_row(
                "TOTAL NET ASSETS",
                values={12: 0, 13: 30, 14: 36, 15: 6, 19: 0.7},
            )
        )
        self.assertEqual(
            GroupParser._validate_report_total(groups, incorrect_percentage_row),
            [
                {
                    "field": "total_percent_of_market_value",
                    "expected": Decimal("0.75"),
                    "actual": Decimal("0.7"),
                }
            ],
        )

    def test_report_total_mismatch_is_logged(self):
        dataframe = _report_dataframe(
            [
                _excel_row("CASH"),
                _excel_row("CASH-001", "Cash", {13: 10, 14: 12, 15: 2, 19: 25}),
                _excel_row(
                    "CASH TOTAL",
                    values={13: 10, 14: 12, 15: 2, 19: 0.25},
                ),
            ],
            total_net_assets_values={13: 9, 14: 12, 15: 2, 19: 0.25},
        )

        with self.assertLogs("fundrock.nav_report_parser", level="CRITICAL") as logs:
            ReportParser.parse(dataframe, source_file="sample.xls")

        self.assertTrue(
            any(
                "file=sample.xls" in message
                and "group=TOTAL NET ASSETS" in message
                and "field=total_prior_market_value_base" in message
                and "expected=10" in message
                and "actual=9" in message
                for message in logs.output
            )
        )

    def test_report_parse_builds_holdings_parent_child_relationship(self):
        dataframe = _report_dataframe(
            [
                _excel_row("HOLDINGS AT MARKET VALUE"),
                _excel_row("EQUITIES"),
                _excel_row(
                    "EQ-001",
                    "Equity",
                    {12: 1, 13: 10, 14: 9, 15: -1, 19: 50},
                ),
                _excel_row(
                    "HOLDINGS AT MARKET VALUE TOTAL",
                    values={12: 1, 13: 10, 14: 9, 15: -1, 19: 0.5},
                ),
            ],
            total_net_assets_values={13: 10, 14: 9, 15: -1, 19: 0.5},
        )

        report = ReportParser.parse(dataframe)

        parent = next(
            group
            for group in report.groups
            if group.group_label == "HOLDINGS AT MARKET VALUE"
            and group.instrument_type is None
        )
        child = next(
            group
            for group in report.groups
            if group.instrument_type == "EQUITIES"
        )
        self.assertIsNone(parent.parent_group_id)
        self.assertEqual(parent.total_prior_market_value_base, 10)
        self.assertIs(child.parent_group, parent)
        self.assertEqual([row.security_code for row in child.rows], ["EQ-001"])


class ReportParserPersistenceTest(unittest.TestCase):
    def test_group_total_values_keep_report_decimal_precision_in_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'nav.db'}")
            Base.metadata.create_all(engine)
            expected = Decimal("234821804.77")
            with Session(engine) as session:
                session.add(
                    NAVReport(
                        portfolio_code="65713",
                        report_date=datetime.date(2026, 8, 7),
                        groups=[
                            Group(
                                group_label="CASH",
                                total_prior_market_value_base=expected,
                            )
                        ],
                    )
                )
                session.commit()

            with Session(engine) as session:
                group = session.scalar(select(Group))
            engine.dispose()

        self.assertEqual(group.total_prior_market_value_base, expected)

    def test_logs_critical_total_mismatch_and_still_saves_report(self):
        with tempfile.TemporaryDirectory() as directory:
            connection_string = f"sqlite:///{Path(directory) / 'nav.db'}"
            dataframe = _report_dataframe(
                [
                    _excel_row("CASH"),
                    _excel_row("CASH-001", "Cash", {12: 2}),
                    _excel_row("CASH TOTAL", values={12: 1}),
                ]
            )
            with (
                patch("fundrock.nav_report_parser.pd.read_excel", return_value=dataframe),
                self.assertLogs("fundrock.nav_report_parser", level="CRITICAL") as logs,
            ):
                ReportParser.process_excel_file(
                    "NAV_65713_2026-08-07.xls",
                    connection_string,
                )

            engine = create_engine(connection_string)
            with Session(engine) as session:
                report = session.scalar(select(NAVReport))
                group = session.scalar(select(Group).where(Group.group_label == "CASH"))
            engine.dispose()

        self.assertIsNotNone(report)
        self.assertIsNotNone(group)
        self.assertEqual(group.total_current_book_value_base, 1)
        self.assertTrue(
            any(
                "CRITICAL" in message
                and "file=NAV_65713_2026-08-07.xls" in message
                and "group=CASH" in message
                and "expected=2" in message
                and "actual=1" in message
                for message in logs.output
            )
        )

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
