from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Tuple

from ..calculations import CalculationContext
from ..config import AllowanceConfig
from ..models import AllowanceRecord, AllowanceType, Status
from ..utils import month_end, proration_fraction
from ..storage.db import StudentRow


@dataclass(frozen=True)
class SettlementResult:
    records: List[AllowanceRecord]
    warnings: List[str]


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def same_month(a: date, b: date) -> bool:
    return a.year == b.year and a.month == b.month


def parse_settlement_month(value: str) -> date:
    parts = value.split("-")
    if len(parts) != 2:
        raise ValueError("Invalid settlement month")
    return date(int(parts[0]), int(parts[1]), 1)


def compute_monthly_settlement(
    students: Iterable[StudentRow],
    settlement_month: date,
    config: AllowanceConfig,
    baggage_pay_ids: Iterable[str],
    withdrawal_living_ids: Iterable[str],
) -> SettlementResult:
    ctx = CalculationContext(config=config)
    records: List[AllowanceRecord] = []
    warnings: List[str] = []
    baggage_set = set(baggage_pay_ids)
    withdrawal_set = set(withdrawal_living_ids)

    for student in students:
        records.extend(
            _student_records(
                student=student,
                settlement_month=settlement_month,
                config=config,
                ctx=ctx,
                pay_baggage=student.student_id in baggage_set,
                pay_withdrawal_living=student.student_id in withdrawal_set,
                warnings=warnings,
            )
        )

    return SettlementResult(records=records, warnings=warnings)


def _student_records(
    *,
    student: StudentRow,
    settlement_month: date,
    config: AllowanceConfig,
    ctx: CalculationContext,
    pay_baggage: bool,
    pay_withdrawal_living: bool,
    warnings: List[str],
) -> List[AllowanceRecord]:
    items: List[AllowanceRecord] = []
    entry_month = month_start(student.first_entry_date)
    settlement_end = month_end(settlement_month)
    monthly_usd = config.living_allowance_by_degree[student.degree_level]

    def add_living(prorated: bool, metadata: Dict[str, str], rule_id: str, description: str) -> None:
        fraction = proration_fraction(student.first_entry_date) if prorated else Decimal("1")
        usd = monthly_usd * fraction
        if prorated:
            metadata = {**metadata, "fraction": str(fraction)}
        round_usd = prorated and config.rounding_policy == "two_step"
        money = ctx.to_money(usd, round_usd=round_usd)
        items.append(
            AllowanceRecord(
                student_id=student.student_id,
                allowance_type=AllowanceType.LIVING,
                period_start=settlement_month,
                period_end=settlement_end,
                amount=money,
                rule_id=rule_id,
                description=description,
                metadata={**metadata, "rounding_policy": config.rounding_policy},
            )
        )

    # Living allowance
    if settlement_month >= entry_month:
        if student.status == Status.IN_STUDY:
            if same_month(settlement_month, entry_month):
                add_living(
                    True,
                    {"monthly_usd": str(monthly_usd), "entry_date": student.first_entry_date.isoformat()},
                    "LIVING_ENTRY_PRORATE",
                    "Prorated living allowance for entry month",
                )
            else:
                add_living(
                    False,
                    {"monthly_usd": str(monthly_usd)},
                    "LIVING_FULL_MONTH",
                    "Full monthly living allowance",
                )
        elif student.status == Status.GRADUATED and student.graduation_date:
            grad_month = month_start(student.graduation_date)
            if settlement_month <= grad_month:
                if same_month(settlement_month, entry_month):
                    add_living(
                        True,
                        {"monthly_usd": str(monthly_usd), "entry_date": student.first_entry_date.isoformat()},
                        "LIVING_ENTRY_PRORATE",
                        "Prorated living allowance for entry month",
                    )
                else:
                    add_living(
                        False,
                        {"monthly_usd": str(monthly_usd)},
                        "LIVING_FULL_MONTH",
                        "Full monthly living allowance",
                    )
        elif student.status == Status.WITHDRAWN and student.withdrawal_date:
            withdrawal_month = month_start(student.withdrawal_date)
            if settlement_month < withdrawal_month:
                if same_month(settlement_month, entry_month):
                    add_living(
                        True,
                        {"monthly_usd": str(monthly_usd), "entry_date": student.first_entry_date.isoformat()},
                        "LIVING_ENTRY_PRORATE",
                        "Prorated living allowance for entry month",
                    )
                else:
                    add_living(
                        False,
                        {"monthly_usd": str(monthly_usd)},
                        "LIVING_FULL_MONTH",
                        "Full monthly living allowance",
                    )
            elif settlement_month == withdrawal_month and pay_withdrawal_living:
                metadata = {"monthly_usd": str(monthly_usd), "withdrawal_toggle": "true"}
                if same_month(settlement_month, entry_month):
                    metadata["entry_date"] = student.first_entry_date.isoformat()
                    add_living(
                        True,
                        metadata,
                        "LIVING_WITHDRAWAL_TOGGLE_PRORATE",
                        "Prorated living allowance for withdrawal month (toggle)",
                    )
                else:
                    add_living(
                        False,
                        metadata,
                        "LIVING_WITHDRAWAL_TOGGLE",
                        "Living allowance for withdrawal month (toggle)",
                    )

    # Study allowance (October only)
    if settlement_month.month == 10:
        oct_first = date(settlement_month.year, 10, 1)
        qualifies_oct = False
        special_case = False
        if student.status == Status.IN_STUDY:
            qualifies_oct = student.first_entry_date <= oct_first
        elif student.status == Status.GRADUATED and student.graduation_date:
            qualifies_oct = student.first_entry_date <= oct_first <= student.graduation_date
        elif student.status == Status.WITHDRAWN and student.withdrawal_date:
            special_case = (
                student.first_entry_date.year == settlement_month.year
                and student.withdrawal_date < oct_first
                and config.issue_study_if_exit_before_oct_entry_year
            )
        if qualifies_oct or special_case:
            rule_id = "STUDY_OCT_IN_STUDY" if qualifies_oct else "STUDY_ENTRY_YEAR_OVERRIDE"
            description = "Study allowance issued for October in-study" if qualifies_oct else "Study allowance issued by entry-year override"
            money = ctx.to_money(config.study_allowance_usd, round_usd=False)
            items.append(
                AllowanceRecord(
                    student_id=student.student_id,
                    allowance_type=AllowanceType.STUDY,
                    period_start=oct_first,
                    period_end=oct_first,
                    amount=money,
                    rule_id=rule_id,
                    description=description,
                    metadata={
                        "year": str(settlement_month.year),
                        "qualifies_oct": str(qualifies_oct),
                        "special_case": str(special_case),
                        "rounding_policy": config.rounding_policy,
                    },
                )
            )

    # Baggage allowance
    if pay_baggage:
        if not student.graduation_date:
            warnings.append(f"{student.student_id}: missing graduation_date")
        else:
            if settlement_month < month_start(student.graduation_date):
                warnings.append(f"{student.student_id}: before graduation month")
            else:
                money = ctx.to_money(config.baggage_allowance_usd, round_usd=False)
                items.append(
                    AllowanceRecord(
                        student_id=student.student_id,
                        allowance_type=AllowanceType.BAGGAGE,
                        period_start=student.graduation_date,
                        period_end=student.graduation_date,
                        amount=money,
                        rule_id="BAGGAGE_ON_GRADUATION",
                        description="One-time excess baggage allowance after graduation",
                        metadata={
                            "baggage_toggle": "true",
                            "settlement_month": settlement_month.isoformat(),
                            "rounding_policy": config.rounding_policy,
                        },
                    )
                )

    return items
