from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from .config import AllowanceConfig
from .models import AllowanceRecord, AllowanceType, CalculationResult, MoneyAmount, Status, Student
from .utils import (
    date_range_to_years,
    iter_month_starts,
    month_end,
    proration_fraction,
    quantize_amount,
    year_month_first,
)


@dataclass(frozen=True)
class CalculationContext:
    config: AllowanceConfig

    def to_money(self, usd: Decimal, *, round_usd: bool = False) -> MoneyAmount:
        usd_q = quantize_amount(usd, self.config.usd_quantize, self.config.rounding_mode) if round_usd else usd
        cny = usd_q * self.config.fx_rate_usd_to_cny
        cny_q = quantize_amount(cny, self.config.cny_quantize, self.config.rounding_mode)
        return MoneyAmount(usd=usd_q, cny=cny_q)


def calculate_student_allowances(
    student: Student,
    config: AllowanceConfig,
    calculation_date: Optional[date] = None,
) -> CalculationResult:
    ctx = CalculationContext(config=config)
    records: List[AllowanceRecord] = []
    warnings: List[str] = []

    calc_date = calculation_date or date.today()
    records.extend(_calculate_living_allowance(student, ctx, calc_date))
    records.extend(_calculate_study_allowance(student, ctx, calc_date))
    records.extend(_calculate_baggage_allowance(student, ctx))

    totals_usd_by_type: Dict[AllowanceType, Decimal] = {}
    totals_cny_by_type: Dict[AllowanceType, Decimal] = {}
    for record in records:
        totals_usd_by_type[record.allowance_type] = totals_usd_by_type.get(record.allowance_type, Decimal("0")) + record.amount.usd
        totals_cny_by_type[record.allowance_type] = totals_cny_by_type.get(record.allowance_type, Decimal("0")) + record.amount.cny

    grand_total_usd = sum(totals_usd_by_type.values(), Decimal("0"))
    grand_total_cny = sum(totals_cny_by_type.values(), Decimal("0"))

    return CalculationResult(
        student_id=student.student_id,
        records=records,
        totals_usd_by_type=totals_usd_by_type,
        totals_cny_by_type=totals_cny_by_type,
        grand_total_usd=grand_total_usd,
        grand_total_cny=grand_total_cny,
        warnings=warnings,
    )


def _calculate_living_allowance(student: Student, ctx: CalculationContext, calc_date: date) -> List[AllowanceRecord]:
    monthly_usd = ctx.config.living_allowance_by_degree[student.degree_level]
    records: List[AllowanceRecord] = []
    entry_month_start = date(student.first_entry_date.year, student.first_entry_date.month, 1)
    exit_date = calc_date if student.status == Status.IN_STUDY else (student.graduation_date or calc_date)
    for month_start in iter_month_starts(entry_month_start, exit_date):
        period_start = month_start
        period_end = month_end(month_start)
        if month_start.year == student.first_entry_date.year and month_start.month == student.first_entry_date.month:
            fraction = proration_fraction(student.first_entry_date)
            usd = monthly_usd * fraction
            round_usd = ctx.config.rounding_policy == "two_step"
            money = ctx.to_money(usd, round_usd=round_usd)
            records.append(
                AllowanceRecord(
                    student_id=student.student_id,
                    allowance_type=AllowanceType.LIVING,
                    period_start=period_start,
                    period_end=period_end,
                    amount=money,
                    rule_id="LIVING_ENTRY_PRORATE",
                    description="Prorated living allowance for entry month",
                    metadata={
                        "monthly_usd": str(monthly_usd),
                        "fraction": str(fraction),
                        "entry_date": student.first_entry_date.isoformat(),
                        "rounding_policy": ctx.config.rounding_policy,
                    },
                )
            )
        else:
            money = ctx.to_money(monthly_usd, round_usd=False)
            records.append(
                AllowanceRecord(
                    student_id=student.student_id,
                    allowance_type=AllowanceType.LIVING,
                    period_start=period_start,
                    period_end=period_end,
                    amount=money,
                    rule_id="LIVING_FULL_MONTH",
                    description="Full monthly living allowance",
                    metadata={"monthly_usd": str(monthly_usd), "rounding_policy": ctx.config.rounding_policy},
                )
            )
    return records


def _calculate_study_allowance(student: Student, ctx: CalculationContext, calc_date: date) -> List[AllowanceRecord]:
    records: List[AllowanceRecord] = []
    exit_date = calc_date if student.status == Status.IN_STUDY else (student.graduation_date or calc_date)
    for year in date_range_to_years(student.first_entry_date, exit_date):
        target_first = year_month_first(year, ctx.config.study_allowance_month)
        qualifies_month = False
        entry_month_override = False
        if student.status == Status.IN_STUDY:
            qualifies_month = student.first_entry_date <= target_first <= exit_date
        elif student.status in (Status.GRADUATED, Status.WITHDRAWN) and student.graduation_date is not None:
            qualifies_month = student.first_entry_date <= target_first <= student.graduation_date
        if (
            ctx.config.issue_study_if_entry_month
            and student.first_entry_date.year == year
            and student.first_entry_date.month == ctx.config.study_allowance_month
            and student.first_entry_date <= exit_date
        ):
            entry_month_override = True
        special_case = (
            student.status in (Status.GRADUATED, Status.WITHDRAWN)
            and year == student.first_entry_date.year
            and exit_date < year_month_first(student.first_entry_date.year, ctx.config.study_allowance_month)
            and ctx.config.issue_study_if_exit_before_oct_entry_year
        )
        if qualifies_month or entry_month_override or special_case:
            if special_case:
                rule_id = "STUDY_ENTRY_YEAR_OVERRIDE"
                description = "Study allowance issued by entry-year override"
            elif entry_month_override and not qualifies_month:
                rule_id = "STUDY_ENTRY_MONTH"
                description = "Study allowance issued for entry month"
            else:
                rule_id = "STUDY_MONTH_IN_STUDY"
                description = "Study allowance issued for study month in-study"
            money = ctx.to_money(ctx.config.study_allowance_usd, round_usd=False)
            records.append(
                AllowanceRecord(
                    student_id=student.student_id,
                    allowance_type=AllowanceType.STUDY,
                    period_start=target_first,
                    period_end=target_first,
                    amount=money,
                    rule_id=rule_id,
                    description=description,
                    metadata={
                        "year": str(year),
                        "study_month": str(ctx.config.study_allowance_month),
                        "qualifies_month": str(qualifies_month),
                        "entry_month_override": str(entry_month_override),
                        "special_case": str(special_case),
                        "rounding_policy": ctx.config.rounding_policy,
                    },
                )
            )
    return records


def _calculate_baggage_allowance(student: Student, ctx: CalculationContext) -> List[AllowanceRecord]:
    if student.status != Status.GRADUATED:
        return []
    money = ctx.to_money(ctx.config.baggage_allowance_usd, round_usd=False)
    return [
        AllowanceRecord(
            student_id=student.student_id,
            allowance_type=AllowanceType.BAGGAGE,
            period_start=student.graduation_date,
            period_end=student.graduation_date,
            amount=money,
            rule_id="BAGGAGE_ON_GRADUATION",
            description="One-time excess baggage allowance after graduation",
            metadata={
                "graduation_date": student.graduation_date.isoformat(),
                "rounding_policy": ctx.config.rounding_policy,
            },
        )
    ]
