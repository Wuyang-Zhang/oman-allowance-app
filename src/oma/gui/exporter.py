from __future__ import annotations

import tempfile
import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Sequence

from ..export import Table, write_csv, write_excel_xlsx
from ..storage.db import RecordRow
from .i18n import Translator


def export_records(records: List[RecordRow], translator: Translator, fmt: str) -> str:
    header_keys = [
        ("run_id", "export.header.run_id"),
        ("settlement_month", "export.header.settlement_month"),
        ("student_id", "export.header.student_id"),
        ("allowance_type", "export.header.allowance_type"),
        ("period_start", "export.header.period_start"),
        ("period_end", "export.header.period_end"),
        ("amount_usd", "export.header.amount_usd"),
        ("fx_rate", "export.header.fx_rate"),
        ("amount_cny", "export.header.amount_cny"),
        ("rule_id", "export.header.rule_id"),
        ("description", "export.header.description"),
        ("metadata_json", "export.header.metadata"),
    ]
    headers = [translator.t(key) for _, key in header_keys]
    rows = []
    for record in records:
        row_values = {
            "run_id": record.run_id,
            "settlement_month": record.settlement_month,
            "student_id": record.student_id,
            "allowance_type": record.allowance_type,
            "period_start": record.period_start,
            "period_end": record.period_end,
            "amount_usd": record.amount_usd,
            "fx_rate": record.fx_rate,
            "amount_cny": record.amount_cny,
            "rule_id": record.rule_id,
            "description": record.description,
            "metadata_json": record.metadata_json,
        }
        rows.append({translator.t(key): row_values[field] for field, key in header_keys})

    suffix = ".xlsx" if fmt == "xlsx" else ".csv"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()

    if fmt == "xlsx":
        tables = [Table("Settlement", rows, headers)]
        write_excel_xlsx(temp.name, tables)
    else:
        write_csv(temp.name, rows, headers)
    return temp.name


def export_monthly_settlement_excel(
    *,
    run: "RunRow",
    config_row: "ConfigRow",
    students: Sequence["StudentRow"],
    records: List[RecordRow],
    translator: Translator,
) -> str:
    from ..storage.db import ConfigRow, RunRow, StudentRow

    student_map = {s.student_id: s for s in students}
    records_by_student: Dict[str, List[RecordRow]] = {}
    for record in records:
        records_by_student.setdefault(record.student_id, []).append(record)

    def header(key: str) -> str:
        return translator.t(key)

    summary_headers = [
        header("export.header.settlement_month"),
        header("export.header.run_id"),
        header("export.header.student_id"),
        header("export.header.name"),
        header("export.header.degree_level"),
        header("export.header.status"),
        header("export.header.entry_date"),
        header("export.header.graduation_date"),
        header("export.header.withdrawal_date"),
        header("export.header.living_cny"),
        header("export.header.study_cny"),
        header("export.header.baggage_cny"),
        header("export.header.total_cny"),
        header("export.header.fx_rate"),
        header("export.header.rounding_mode"),
        header("export.header.special_flags"),
    ]
    summary_rows: List[Dict[str, str]] = []
    for student_id, student_records in records_by_student.items():
        student = student_map.get(student_id)
        living_cny = sum((Decimal(r.amount_cny) for r in student_records if r.allowance_type == "Living"), Decimal("0"))
        study_cny = sum((Decimal(r.amount_cny) for r in student_records if r.allowance_type == "Study"), Decimal("0"))
        baggage_cny = sum((Decimal(r.amount_cny) for r in student_records if r.allowance_type == "ExcessBaggage"), Decimal("0"))
        total_cny = living_cny + study_cny + baggage_cny
        special_flags = _special_flags(student_records, translator)

        summary_rows.append(
            {
                header("export.header.settlement_month"): run.settlement_month,
                header("export.header.run_id"): str(run.run_id),
                header("export.header.student_id"): student_id,
                header("export.header.name"): student.name if student else "",
                header("export.header.degree_level"): student.degree_level.value if student else "",
                header("export.header.status"): student.status.value if student else "",
                header("export.header.entry_date"): student.first_entry_date.isoformat() if student else "",
                header("export.header.graduation_date"): student.graduation_date.isoformat() if student and student.graduation_date else "",
                header("export.header.withdrawal_date"): student.withdrawal_date.isoformat() if student and student.withdrawal_date else "",
                header("export.header.living_cny"): _fmt_decimal(living_cny),
                header("export.header.study_cny"): _fmt_decimal(study_cny),
                header("export.header.baggage_cny"): _fmt_decimal(baggage_cny),
                header("export.header.total_cny"): _fmt_decimal(total_cny),
                header("export.header.fx_rate"): run.fx_rate,
                header("export.header.rounding_mode"): config_row.rounding_policy,
                header("export.header.special_flags"): special_flags,
            }
        )

    detail_headers = [
        header("export.header.run_id"),
        header("export.header.settlement_month"),
        header("export.header.student_id"),
        header("export.header.name"),
        header("export.header.rule_id"),
        header("export.header.description"),
        header("export.header.usd_raw"),
        header("export.header.fx_rate"),
        header("export.header.amount_cny"),
        header("export.header.period_start"),
        header("export.header.period_end"),
        header("export.header.metadata"),
    ]
    detail_rows: List[Dict[str, str]] = []
    for record in records:
        student = student_map.get(record.student_id)
        usd_raw = _usd_raw_for_record(record, config_row, student)
        detail_rows.append(
            {
                header("export.header.run_id"): str(record.run_id),
                header("export.header.settlement_month"): record.settlement_month,
                header("export.header.student_id"): record.student_id,
                header("export.header.name"): student.name if student else "",
                header("export.header.rule_id"): record.rule_id,
                header("export.header.description"): record.description,
                header("export.header.usd_raw"): _fmt_decimal(usd_raw),
                header("export.header.fx_rate"): record.fx_rate,
                header("export.header.amount_cny"): record.amount_cny,
                header("export.header.period_start"): record.period_start,
                header("export.header.period_end"): record.period_end,
                header("export.header.metadata"): record.metadata_json,
            }
        )

    student_headers = [
        header("export.header.student_id"),
        header("export.header.name"),
        header("export.header.degree_level"),
        header("export.header.status"),
        header("export.header.entry_date"),
        header("export.header.graduation_date"),
        header("export.header.withdrawal_date"),
    ]
    student_rows = []
    for student_id in records_by_student.keys():
        student = student_map.get(student_id)
        if not student:
            continue
        student_rows.append(
            {
                header("export.header.student_id"): student.student_id,
                header("export.header.name"): student.name,
                header("export.header.degree_level"): student.degree_level.value,
                header("export.header.status"): student.status.value,
                header("export.header.entry_date"): student.first_entry_date.isoformat(),
                header("export.header.graduation_date"): student.graduation_date.isoformat() if student.graduation_date else "",
                header("export.header.withdrawal_date"): student.withdrawal_date.isoformat() if student.withdrawal_date else "",
            }
        )

    config_headers = [
        header("export.header.config_version"),
        header("export.header.exported_at"),
        header("export.header.living_bachelor"),
        header("export.header.living_master"),
        header("export.header.living_phd"),
        header("export.header.study_usd"),
        header("export.header.baggage_usd"),
        header("export.header.fx_rate"),
        header("export.header.policy"),
        header("export.header.withdrawn_default"),
        header("export.header.rounding_mode"),
        header("export.header.rounding_policy"),
    ]
    config_rows = [
        {
            header("export.header.config_version"): str(run.config_version),
            header("export.header.exported_at"): datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            header("export.header.living_bachelor"): config_row.living_allowance_bachelor,
            header("export.header.living_master"): config_row.living_allowance_master,
            header("export.header.living_phd"): config_row.living_allowance_phd,
            header("export.header.study_usd"): config_row.study_allowance_usd,
            header("export.header.baggage_usd"): config_row.baggage_allowance_usd,
            header("export.header.fx_rate"): config_row.fx_rate_usd_to_cny,
            header("export.header.policy"): str(config_row.issue_study_if_exit_before_oct_entry_year),
            header("export.header.withdrawn_default"): str(config_row.withdrawn_living_default),
            header("export.header.rounding_mode"): config_row.rounding_mode,
            header("export.header.rounding_policy"): config_row.rounding_policy,
        }
    ]

    tables = [
        Table("Summary_汇总", summary_rows, summary_headers, _default_widths(len(summary_headers))),
        Table("Details_明细", detail_rows, detail_headers, _default_widths(len(detail_headers))),
        Table("Students_学生信息", student_rows, student_headers, _default_widths(len(student_headers))),
        Table("Config_配置快照", config_rows, config_headers, _default_widths(len(config_headers))),
    ]

    suffix = ".xlsx"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()
    write_excel_xlsx(temp.name, tables)
    return temp.name


def _default_widths(count: int) -> List[float]:
    return [18.0 for _ in range(count)]


def _fmt_decimal(value: Decimal) -> str:
    return str(value)


def _special_flags(records: List[RecordRow], translator: Translator) -> str:
    flags = []
    for record in records:
        try:
            metadata = json.loads(record.metadata_json)
        except Exception:
            metadata = {}
        if record.allowance_type == "ExcessBaggage" or metadata.get("baggage_toggle") == "true":
            if translator.t("export.flag.baggage") not in flags:
                flags.append(translator.t("export.flag.baggage"))
        if metadata.get("withdrawal_toggle") == "true":
            if translator.t("export.flag.withdrawal") not in flags:
                flags.append(translator.t("export.flag.withdrawal"))
    return ", ".join(flags)


def _usd_raw_for_record(record: RecordRow, config_row: "ConfigRow", student: "StudentRow") -> Decimal:
    from ..storage.db import StudentRow, ConfigRow

    try:
        metadata = json.loads(record.metadata_json)
    except Exception:
        metadata = {}

    if record.allowance_type == "Living":
        if "monthly_usd" in metadata:
            monthly = Decimal(metadata["monthly_usd"])
        elif student is not None:
            if student.degree_level.value == "Bachelor":
                monthly = Decimal(config_row.living_allowance_bachelor)
            elif student.degree_level.value == "Master":
                monthly = Decimal(config_row.living_allowance_master)
            else:
                monthly = Decimal(config_row.living_allowance_phd)
        else:
            monthly = Decimal(record.amount_usd)
        if "fraction" in metadata:
            return monthly * Decimal(metadata["fraction"])
        return monthly
    if record.allowance_type == "Study":
        return Decimal(config_row.study_allowance_usd)
    if record.allowance_type == "ExcessBaggage":
        return Decimal(config_row.baggage_allowance_usd)
    return Decimal(record.amount_usd)
