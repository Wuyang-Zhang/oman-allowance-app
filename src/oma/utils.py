from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, getcontext
from typing import Iterable, Tuple


getcontext().prec = 28


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def month_end(d: date) -> date:
    last_day = monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def iter_month_starts(start: date, end: date) -> Iterable[date]:
    cur = date(start.year, start.month, 1)
    while cur <= end:
        yield cur
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)


def days_in_month(d: date) -> int:
    return monthrange(d.year, d.month)[1]


def proration_fraction(entry_date: date) -> Decimal:
    total_days = days_in_month(entry_date)
    days = total_days - entry_date.day + 1
    return Decimal(days) / Decimal(total_days)


def quantize_amount(amount: Decimal, quantum: Decimal, rounding: str) -> Decimal:
    return amount.quantize(quantum, rounding=rounding)


def year_october_first(year: int) -> date:
    return date(year, 10, 1)


def date_range_to_years(start: date, end: date) -> Tuple[int, ...]:
    return tuple(range(start.year, end.year + 1))
