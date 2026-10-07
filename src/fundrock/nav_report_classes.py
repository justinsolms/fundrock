import datetime
import decimal
from typing import List, Optional

from sqlalchemy import String, Date, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class NAVReport(Base):
    """Aggregate root container for one portfolio's report on a given date."""
    __tablename__ = 'nav_reports'
    __table_args__ = (
        UniqueConstraint('portfolio_code', 'report_date', name='uq_nav_report_portfolio_date'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Header strings
    portfolio_code: Mapped[str] = mapped_column(String(50), index=True)
    report_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    portfolio_name: Mapped[Optional[str]] = mapped_column(String(255))
    base_currency: Mapped[Optional[str]] = mapped_column(String(10))
    
    # Relationships
    groups: Mapped[List["Group"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    summary_items: Mapped[List["SummaryItem"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    exchange_rates: Mapped[List["ExchangeRateItem"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class Group(Base):
    """Captures a report group, its detail rows, and reported total values."""
    __tablename__ = 'nav_groups'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('nav_reports.id'))
    parent_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('nav_groups.id')
    )
    
    # Relationships
    report: Mapped["NAVReport"] = relationship(back_populates="groups")
    rows: Mapped[List["Row"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    parent_group: Mapped[Optional["Group"]] = relationship(
        back_populates="child_groups",
        remote_side="Group.id",
    )
    child_groups: Mapped[List["Group"]] = relationship(
        back_populates="parent_group",
        cascade="all, delete-orphan",
    )

    # String data
    group_label: Mapped[str] = mapped_column(String(100))
    instrument_type: Mapped[Optional[str]] = mapped_column(String(100))

    # Values read from the group's TOTAL row
    total_current_book_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(precision=24, scale=2)
    )
    total_prior_market_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(precision=24, scale=2)
    )
    total_current_market_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(precision=24, scale=2)
    )
    total_market_value_base_change: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(precision=24, scale=2)
    )
    total_percent_of_market_value: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(precision=12, scale=4)
    )


class Row(Base):
    """Represents individual security rows within a group."""
    __tablename__ = 'nav_rows'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey('nav_groups.id'))
    
    # Relationships
    group: Mapped["Group"] = relationship(back_populates="rows")
    
    # String data
    security_code: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    issue_currency: Mapped[Optional[str]] = mapped_column(String(10))
    
    # Numeric data
    shares_par_prior: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    shares_par_current: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    base_price_prior: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    holdings_price_prior: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    base_price_current: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    holdings_price_current: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    price_percent_change_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    current_book_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    prior_market_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    current_market_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    market_value_base_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    earned_income_for_the_period: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    market_value_percent_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    adjusted_market_value_percent_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    percent_of_market_value: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)


class SummaryItem(Base):
    """Captures individual line items in the NAV summary block."""
    __tablename__ = 'nav_summary_items'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('nav_reports.id'))
    
    # Relationships
    report: Mapped["NAVReport"] = relationship(back_populates="summary_items")
    
    # String data
    description: Mapped[str] = mapped_column(String(255))
    
    # Numeric data
    prior_market_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    current_market_value_base: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    market_value_base_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    market_value_percent_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)


class ExchangeRateItem(Base):
    """Captures individual currency pairs from the exchange rates block."""
    __tablename__ = 'exchange_rate_items'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('nav_reports.id'))
    
    # Relationships
    report: Mapped["NAVReport"] = relationship(back_populates="exchange_rates")
    
    # String data
    currency_pair: Mapped[str] = mapped_column(String(50))
    
    # Numeric data
    prior_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    current_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    rate_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    percent_change: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)