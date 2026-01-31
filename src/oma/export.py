from __future__ import annotations

import csv
import os
import zipfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class Table:
    name: str
    rows: List[Dict[str, str]]
    headers: List[str]
    column_widths: List[float] | None = None
    freeze_header: bool = True


def write_csv(path: str, rows: Iterable[Dict[str, str]], headers: Sequence[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in headers})


def write_excel_xlsx(path: str, tables: Sequence[Table]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        sheets_xml, shared_strings = _build_sheets_and_shared_strings(tables)
        zf.writestr("[Content_Types].xml", _content_types_xml(len(tables)))
        zf.writestr("_rels/.rels", _root_rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml(tables))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(tables)))
        zf.writestr("xl/sharedStrings.xml", _shared_strings_xml(shared_strings))
        for idx, sheet_xml in enumerate(sheets_xml, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml)


def _build_sheets_and_shared_strings(tables: Sequence[Table]) -> Tuple[List[str], List[str]]:
    shared_strings: List[str] = []
    string_index: Dict[str, int] = {}
    sheets_xml: List[str] = []

    for table in tables:
        rows_xml = []
        row_index = 1
        headers = table.headers
        rows = [dict(zip(headers, headers))] + list(table.rows)
        cols_xml = ""
        if table.column_widths:
            cols_parts = []
            for idx, width in enumerate(table.column_widths, start=1):
                cols_parts.append(f"<col min=\"{idx}\" max=\"{idx}\" width=\"{width}\" customWidth=\"1\"/>")
            cols_xml = f"<cols>{''.join(cols_parts)}</cols>"
        sheet_views = ""
        if table.freeze_header:
            sheet_views = (
                "<sheetViews><sheetView workbookViewId=\"0\">"
                "<pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/>"
                "</sheetView></sheetViews>"
            )
        for row in rows:
            cells_xml = []
            col_index = 1
            for header in headers:
                value = str(row.get(header, ""))
                cell_ref = _cell_ref(col_index, row_index)
                if _looks_numeric(value):
                    cells_xml.append(f"<c r=\"{cell_ref}\" t=\"n\"><v>{value}</v></c>")
                else:
                    idx = _shared_string_index(value, shared_strings, string_index)
                    cells_xml.append(f"<c r=\"{cell_ref}\" t=\"s\"><v>{idx}</v></c>")
                col_index += 1
            rows_xml.append(f"<row r=\"{row_index}\">{''.join(cells_xml)}</row>")
            row_index += 1
        sheet_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            f"{sheet_views}{cols_xml}<sheetData>{''.join(rows_xml)}</sheetData>"
            "</worksheet>"
        )
        sheets_xml.append(sheet_xml)

    return sheets_xml, shared_strings


def _shared_string_index(value: str, shared: List[str], lookup: Dict[str, int]) -> int:
    if value in lookup:
        return lookup[value]
    idx = len(shared)
    shared.append(value)
    lookup[value] = idx
    return idx


def _cell_ref(col: int, row: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
        return value.strip() != ""
    except ValueError:
        return False


def _content_types_xml(sheet_count: int) -> str:
    overrides = "".join(
        f"<Override PartName=\"/xl/worksheets/sheet{idx}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        for idx in range(1, sheet_count + 1)
    )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/sharedStrings.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml\"/>"
        f"{overrides}"
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
        "</Relationships>"
    )


def _workbook_xml(tables: Sequence[Table]) -> str:
    sheets = "".join(
        f"<sheet name=\"{_escape_xml(table.name)}\" sheetId=\"{idx}\" r:id=\"rId{idx}\"/>"
        for idx, table in enumerate(tables, start=1)
    )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = "".join(
        f"<Relationship Id=\"rId{idx}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet{idx}.xml\"/>"
        for idx in range(1, sheet_count + 1)
    )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        f"{rels}"
        "</Relationships>"
    )


def _shared_strings_xml(strings: Sequence[str]) -> str:
    items = "".join(f"<si><t>{_escape_xml(value)}</t></si>" for value in strings)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        f"count=\"{len(strings)}\" uniqueCount=\"{len(strings)}\">"
        f"{items}"
        "</sst>"
    )


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
        .replace("'", "&apos;")
    )
