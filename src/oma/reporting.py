from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List

from .models import AllowanceRecord, AllowanceType, CalculationResult, ReportTables, Student


def build_report_tables(students: Iterable[Student], results: Iterable[CalculationResult]) -> ReportTables:
    student_lookup = {s.student_id: s for s in students}
    flat_records: List[Dict[str, str]] = []
    summary_by_student: Dict[str, Dict[AllowanceType, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    summary_by_student_cny: Dict[str, Dict[AllowanceType, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    summary_by_year: Dict[str, Dict[AllowanceType, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    summary_by_year_cny: Dict[str, Dict[AllowanceType, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    summary_by_type: Dict[AllowanceType, Dict[str, Decimal]] = defaultdict(lambda: {"usd": Decimal("0"), "cny": Decimal("0")})

    for result in results:
        for record in result.records:
            student = student_lookup.get(record.student_id)
            student_name = student.name if student else ""
            period_label = _format_period(record.period_start, record.period_end, record.allowance_type)
            year_key = str(record.period_start.year)

            flat_records.append(
                {
                    "student_id": record.student_id,
                    "student_name": student_name,
                    "allowance_type": record.allowance_type.value,
                    "period": period_label,
                    "period_start": record.period_start.isoformat(),
                    "period_end": record.period_end.isoformat(),
                    "amount_usd": str(record.amount.usd),
                    "amount_cny": str(record.amount.cny),
                    "rule_id": record.rule_id,
                    "description": record.description,
                    "metadata": "|".join(f"{k}={v}" for k, v in record.metadata.items()),
                }
            )

            summary_by_student[record.student_id][record.allowance_type] += record.amount.usd
            summary_by_student_cny[record.student_id][record.allowance_type] += record.amount.cny
            summary_by_year[year_key][record.allowance_type] += record.amount.usd
            summary_by_year_cny[year_key][record.allowance_type] += record.amount.cny
            summary_by_type[record.allowance_type]["usd"] += record.amount.usd
            summary_by_type[record.allowance_type]["cny"] += record.amount.cny

    summary_student_rows: List[Dict[str, str]] = []
    for student_id, totals in summary_by_student.items():
        totals_cny = summary_by_student_cny[student_id]
        row = {"student_id": student_id}
        for allowance_type in AllowanceType:
            row[f"{allowance_type.value.lower()}_usd"] = str(totals.get(allowance_type, Decimal("0")))
            row[f"{allowance_type.value.lower()}_cny"] = str(totals_cny.get(allowance_type, Decimal("0")))
        row["grand_total_usd"] = str(sum(totals.values(), Decimal("0")))
        row["grand_total_cny"] = str(sum(totals_cny.values(), Decimal("0")))
        summary_student_rows.append(row)

    summary_year_rows: List[Dict[str, str]] = []
    for year_key, totals in summary_by_year.items():
        totals_cny = summary_by_year_cny[year_key]
        row = {"year": year_key}
        for allowance_type in AllowanceType:
            row[f"{allowance_type.value.lower()}_usd"] = str(totals.get(allowance_type, Decimal("0")))
            row[f"{allowance_type.value.lower()}_cny"] = str(totals_cny.get(allowance_type, Decimal("0")))
        row["grand_total_usd"] = str(sum(totals.values(), Decimal("0")))
        row["grand_total_cny"] = str(sum(totals_cny.values(), Decimal("0")))
        summary_year_rows.append(row)

    summary_type_rows: List[Dict[str, str]] = []
    for allowance_type, totals in summary_by_type.items():
        summary_type_rows.append(
            {
                "allowance_type": allowance_type.value,
                "total_usd": str(totals["usd"]),
                "total_cny": str(totals["cny"]),
            }
        )

    return ReportTables(
        per_student_records=flat_records,
        summary_by_student=summary_student_rows,
        summary_by_year=summary_year_rows,
        summary_by_type=summary_type_rows,
    )


def _format_period(start: date, end: date, allowance_type: AllowanceType) -> str:
    if allowance_type == AllowanceType.LIVING:
        return start.strftime("%Y-%m")
    if allowance_type == AllowanceType.STUDY:
        return str(start.year)
    return start.isoformat()
