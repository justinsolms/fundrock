import datetime
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fundrock.nav_report_classes import Base, NAVReport


class NAVReportTimeSeriesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _report(self, portfolio_code: str, report_date: datetime.date) -> NAVReport:
        return NAVReport(
            portfolio_code=portfolio_code,
            report_date=report_date,
        )

    def test_stores_multiple_dates_for_a_portfolio(self):
        dates = (
            datetime.date(2026, 9, 28),
            datetime.date(2026, 9, 29),
        )
        with Session(self.engine) as session:
            session.add_all(self._report("65713", date) for date in dates)
            session.commit()

            reports = session.scalars(
                select(NAVReport).order_by(NAVReport.report_date)
            ).all()

        self.assertEqual([report.report_date for report in reports], list(dates))

    def test_allows_different_portfolios_on_the_same_date(self):
        report_date = datetime.date(2026, 9, 29)
        with Session(self.engine) as session:
            session.add_all(
                (
                    self._report("65713", report_date),
                    self._report("65714", report_date),
                )
            )
            session.commit()

            reports = session.scalars(select(NAVReport)).all()

        self.assertEqual({report.portfolio_code for report in reports}, {"65713", "65714"})

    def test_rejects_duplicate_portfolio_and_date(self):
        report_date = datetime.date(2026, 9, 29)
        with Session(self.engine) as session:
            session.add(self._report("65713", report_date))
            session.commit()
            session.add(self._report("65713", report_date))

            with self.assertRaises(IntegrityError):
                session.commit()


if __name__ == "__main__":
    unittest.main()
