from __future__ import annotations

import tempfile
from typing import List

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
