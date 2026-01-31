from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional


class DegreeLevel(str, Enum):
    BACHELOR = "Bachelor"
    MASTER = "Master"
    PHD = "PhD"


class Status(str, Enum):
    IN_STUDY = "In-study"
    GRADUATED = "Graduated"
    WITHDRAWN = "Withdrawn"


class AllowanceType(str, Enum):
    LIVING = "Living"
    STUDY = "Study"
    BAGGAGE = "ExcessBaggage"


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str
    degree_level: DegreeLevel
    first_entry_date: date
    graduation_date: Optional[date]
    status: Status

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required")
        if not self.name:
            raise ValueError("name is required")
        if self.status == Status.GRADUATED and self.graduation_date is None:
            raise ValueError("graduation_date is required for Graduated status")
        if self.graduation_date is not None and self.graduation_date < self.first_entry_date:
            raise ValueError("graduation_date must be on or after first_entry_date")

    @property
    def exit_date(self) -> date:
        if self.graduation_date is None:
            raise ValueError("graduation_date is required to determine exit_date")
        return self.graduation_date


@dataclass(frozen=True)
class MoneyAmount:
    usd: Decimal
    cny: Decimal


@dataclass(frozen=True)
class AllowanceRecord:
    student_id: str
    allowance_type: AllowanceType
    period_start: date
    period_end: date
    amount: MoneyAmount
    rule_id: str
    description: str
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CalculationResult:
    student_id: str
    records: List[AllowanceRecord]
    totals_usd_by_type: Dict[AllowanceType, Decimal]
    totals_cny_by_type: Dict[AllowanceType, Decimal]
    grand_total_usd: Decimal
    grand_total_cny: Decimal
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AggregateRow:
    key: str
    totals_usd_by_type: Dict[AllowanceType, Decimal]
    totals_cny_by_type: Dict[AllowanceType, Decimal]
    grand_total_usd: Decimal
    grand_total_cny: Decimal


@dataclass(frozen=True)
class ReportTables:
    per_student_records: List[Dict[str, str]]
    summary_by_student: List[Dict[str, str]]
    summary_by_year: List[Dict[str, str]]
    summary_by_type: List[Dict[str, str]]
