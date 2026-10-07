"""Parser for NAV reports."""

import datetime
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from fundrock.nav_report_classes import NAVReport, Group, Row, SummaryItem, ExchangeRateItem


_REPORT_FILENAME_DATE = re.compile(
    r"NAV_[^_]+_(?P<report_date>\d{4}-\d{2}-\d{2})\.xlsx?",
    re.IGNORECASE,
)


class BaseParser:
    """
    Base parser providing shared utility methods for data cleansing and type conversion.
    """
    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        """Safely converts a pandas value to a Decimal, returning None for NaNs or blanks."""
        if pd.isna(value) or value == "":
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _to_string(value: Any) -> Optional[str]:
        """Safely converts a pandas value to a string, returning None for NaNs."""
        if pd.isna(value):
            return None
        return str(value).strip()


class BaseBlockParser(BaseParser):
    """
    Base class for parsers that process a block of multiple rows.
    """
    def parse_block(self, rows: List[pd.Series]) -> List[Dict[str, Any]]:
        """To be implemented by subclasses to parse a list of dataframe rows."""
        raise NotImplementedError("Subclasses must implement parse_block()")


class HeaderParser(BaseParser):
    """Parses the top section of the report to extract metadata."""
    
    def parse(self, df_head: pd.DataFrame) -> Dict[str, Any]:
        """
        Expects the first ~10 rows of the dataframe.
        Returns kwargs for the NAVReport model.
        """
        report_kwargs: Dict[str, Any] = {}
        
        # Labels are in column C and their corresponding values in column D.
        for _, row in df_head.iterrows():
            for label_column in (1, 2):
                label = self._to_string(row[label_column])
                if not label:
                    continue

                label_upper = label.upper()
                if "AS AT" in label_upper:
                    date_str = label.lower().replace("as at", "").strip()
                    report_kwargs["report_date"] = datetime.datetime.strptime(
                        date_str, "%d/%m/%Y"
                    ).date()
                elif "PORTFOLIO CODE:" in label_upper:
                    report_kwargs["portfolio_code"] = self._to_string(
                        row[label_column + 1]
                    )
                elif "PORTFOLIO NAME:" in label_upper:
                    report_kwargs["portfolio_name"] = self._to_string(
                        row[label_column + 1]
                    )
                elif "BASE CURRENCY:" in label_upper:
                    report_kwargs["base_currency"] = self._to_string(
                        row[label_column + 1]
                    )
                
        return report_kwargs


class RowParser(BaseParser):
    """Parses a single pandas Series into a Row model kwargs dictionary."""
    
    def parse(self, row: pd.Series) -> Dict[str, Any]:
        """Maps pandas row indices to Row model columns."""
        return {
            "security_code": self._to_string(row[2]),
            "description": self._to_string(row[3]),
            "issue_currency": self._to_string(row[4]),
            "shares_par_prior": self._to_decimal(row[5]),
            "shares_par_current": self._to_decimal(row[6]),
            "base_price_prior": self._to_decimal(row[7]),
            "holdings_price_prior": self._to_decimal(row[8]),
            "base_price_current": self._to_decimal(row[9]),
            "holdings_price_current": self._to_decimal(row[10]),
            "price_percent_change_base": self._to_decimal(row[11]),
            "current_book_value_base": self._to_decimal(row[12]),
            "prior_market_value_base": self._to_decimal(row[13]),
            "current_market_value_base": self._to_decimal(row[14]),
            "market_value_base_change": self._to_decimal(row[15]),
            "earned_income_for_the_period": self._to_decimal(row[16]),
            "market_value_percent_change": self._to_decimal(row[17]),
            "adjusted_market_value_percent_change": self._to_decimal(row[18]),
            "percent_of_market_value": self._to_decimal(row[19]),
        }


class GroupParser(BaseBlockParser):
    """Parses a defined group and delegates row parsing to RowParser."""
    
    # Explicitly typing the instance variable for strict type checkers
    row_parser: RowParser
    
    def __init__(self) -> None:
        self.row_parser = RowParser()

    @classmethod
    def extract_and_parse_all(cls, body_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Class method to scan the entire body dataframe, detect group boundaries,
        slice the rows, and parse each group.
        """
        parser_instance: 'GroupParser' = cls()
        all_groups_kwargs: List[Dict[str, Any]] = []
        
        # Explicit type hints for tracking variables
        current_group_label: Optional[str] = None
        current_group_rows: List[pd.Series] = []
        
        row: pd.Series
        for _, row in body_df.iterrows():
            col_2_val: Optional[str] = parser_instance._to_string(row[2])
            col_3_val: Optional[str] = parser_instance._to_string(row[3])
            
            # Skip completely empty rows
            if not col_2_val and not col_3_val:
                continue

            # Detect Group Start: Col 2 has a label, Col 3 (Security Code) is empty, and it's not a TOTAL row
            if col_2_val and not col_3_val and not col_2_val.upper().endswith("TOTAL"):
                current_group_label = col_2_val
                current_group_rows = [] # Reset for the new group
                continue
                
            # Detect Group End: Col 2 ends with TOTAL
            if col_2_val and col_2_val.upper().endswith("TOTAL") and current_group_label is not None:
                # We reached the end of the group, parse the collected slice
                parsed_group: Dict[str, Any] = parser_instance.parse_group(current_group_label, current_group_rows)
                all_groups_kwargs.append(parsed_group)
                
                # Reset tracking variables
                current_group_label = None
                current_group_rows = []
                continue
                
            # If we are inside a group, collect the data rows
            if current_group_label is not None:
                current_group_rows.append(row)
                
        return all_groups_kwargs

    def parse_group(self, group_label: str, rows: List[pd.Series]) -> Dict[str, Any]:
        """Parses the sliced rows for a specific group."""
        group_kwargs: Dict[str, Any] = {
            "group_label": group_label.strip(),
            "rows_data": [] 
        }
        
        row: pd.Series
        for row in rows:
            parsed_row: Dict[str, Any] = self.row_parser.parse(row)
            group_kwargs["rows_data"].append(parsed_row)
                
        return group_kwargs
    
    
class NAVSummaryParser(BaseBlockParser):
    """Parses the NAV Summary block into a list of SummaryItem kwargs."""
    
    def parse_block(self, rows: List[pd.Series]) -> List[Dict[str, Any]]:
        summary_items: List[Dict[str, Any]] = []
        
        for row in rows:
            description = self._to_string(row[2])
            if not description or "Calculated NAV Value" in description:
                continue
                
            summary_items.append({
                "description": description,
                # Mapping to the specific populated columns in the summary tail
                "prior_market_value_base": self._to_decimal(row[12]),
                "current_market_value_base": self._to_decimal(row[13]),
                "market_value_base_change": self._to_decimal(row[14]),
                "market_value_percent_change": self._to_decimal(row[16]),
            })
            
        return summary_items


class ExchangeRatesParser(BaseBlockParser):
    """Parses the Exchange Rates block into a list of ExchangeRateItem kwargs."""
    
    def parse_block(self, rows: List[pd.Series]) -> List[Dict[str, Any]]:
        exchange_rates: List[Dict[str, Any]] = []
        
        for row in rows:
            currency_pair = self._to_string(row[2])
            
            # Stop if we hit the legend or notes
            if not currency_pair or "Legend" in currency_pair or "Note:" in currency_pair:
                continue
                
            exchange_rates.append({
                "currency_pair": currency_pair,
                # Mapping to the specific populated columns in the exchange rate tail
                "prior_rate": self._to_decimal(row[12]),
                "current_rate": self._to_decimal(row[13]),
                "rate_change": self._to_decimal(row[14]),
                "percent_change": self._to_decimal(row[16]),
            })
            
        return exchange_rates


import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from typing import Optional, Dict, Any, List

from fundrock.nav_report_classes import Base

class ReportParser:
    """
    Master orchestrator class responsible for chunking the raw dataframe,
    delegating the data to the specialized parsers, and handling database ingestion.
    """

    @classmethod
    def extract_body_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Dynamically locates the start and end of the report body."""
        start_idx: Optional[int] = None
        end_idx: Optional[int] = None
        
        index: Any
        row: pd.Series
        for index, row in df.iterrows():
            col_2_val: str = str(row[2]).strip().upper() if pd.notna(row[2]) else ""
            
            if "SECURITY CODE" in col_2_val:
                start_idx = index + 1
                continue
                
            if "TOTAL NET ASSETS" in col_2_val:
                end_idx = index
                break
                
        if start_idx is None or end_idx is None:
            raise ValueError("Failed to locate 'Security Code' or 'TOTAL NET ASSETS' boundaries.")
            
        return df.iloc[start_idx:end_idx]

    @classmethod
    def parse(cls, df: pd.DataFrame) -> "NAVReport":
        """Orchestrates the full parsing process and returns a populated NAVReport ORM object."""
        header_kwargs: Dict[str, Any] = HeaderParser().parse(df.head(20))
        report = NAVReport(**header_kwargs)
        
        body_df: pd.DataFrame = cls.extract_body_dataframe(df)
        parsed_groups_list: List[Dict[str, Any]] = GroupParser.extract_and_parse_all(body_df)
        
        for g_kwargs in parsed_groups_list:
            rows_data: List[Dict[str, Any]] = g_kwargs.pop("rows_data")
            group = Group(**g_kwargs)
            group.rows = [Row(**r_kwargs) for r_kwargs in rows_data]
            report.groups.append(group)
            
        tail_start_idx: int = body_df.index[-1] + 1
        tail_df: pd.DataFrame = df.iloc[tail_start_idx:]
        tail_rows: List[pd.Series] = [row for _, row in tail_df.iterrows()]
        
        summary_kwargs_list: List[Dict[str, Any]] = NAVSummaryParser().parse_block(tail_rows)
        report.summary_items = [SummaryItem(**sk) for sk in summary_kwargs_list]
        
        exchange_kwargs_list: List[Dict[str, Any]] = ExchangeRatesParser().parse_block(tail_rows)
        report.exchange_rates = [ExchangeRateItem(**ek) for ek in exchange_kwargs_list]
        
        return report

    @classmethod
    def process_excel_file(cls, file_path: str, db_connection_string: str) -> None:
        """
        Reads a raw NAV Excel report, parses it into ORM objects, 
        and commits it to the database.
        """
        engine = create_engine(db_connection_string)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        print(f"Reading file: {file_path}")
        df = pd.read_excel(file_path, sheet_name=0, header=None)  # type: ignore[reportUnknownMemberType]

        print("Parsing report...")
        report = cls.parse(df)

        filename_match = _REPORT_FILENAME_DATE.fullmatch(Path(file_path).name)
        if filename_match is None:
            raise ValueError(
                f"NAV report filename must include a date in YYYY-MM-DD format: {file_path}"
            )
        filename_date = datetime.date.fromisoformat(
            filename_match.group("report_date")
        )
        if report.report_date != filename_date:
            raise ValueError(
                f"Report date mismatch for {file_path}: "
                f"cell C3 has {report.report_date}, filename has {filename_date}"
            )

        with Session() as session:
            existing_reports = session.scalars(
                select(NAVReport).where(
                    NAVReport.portfolio_code == report.portfolio_code,
                    NAVReport.report_date == report.report_date,
                )
            ).all()
            for existing_report in existing_reports:
                session.delete(existing_report)
            session.flush()
            session.add(report)
            session.commit()
            print(f"Successfully saved Report for {report.report_date} (ID: {report.id}) to database.")