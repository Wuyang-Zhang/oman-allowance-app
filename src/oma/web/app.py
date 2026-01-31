from __future__ import annotations

import csv
import io
import tempfile
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from ..calculations import CalculationContext
from ..config import AllowanceConfig
from ..export import Table, write_csv, write_excel_xlsx
from ..models import AllowanceRecord, AllowanceType, DegreeLevel, Status
from ..utils import month_end, proration_fraction, quantize_amount
from . import db


BASE_DIR = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str((BASE_DIR / "templates").resolve()))

DEFAULT_LANG = "zh_CN"
SUPPORTED_LANGS = {"zh_CN", "en_US"}
TRANSLATIONS: Dict[str, Dict[str, str]] = {}


app = FastAPI(title="Oman Students Allowance Calculator")


def _load_translations() -> None:
    for code in SUPPORTED_LANGS:
        path = BASE_DIR / "i18n" / f"{code}.json"
        with path.open("r", encoding="utf-8") as handle:
            TRANSLATIONS[code] = json.load(handle)


def _normalize_lang(lang: Optional[str]) -> str:
    if lang in SUPPORTED_LANGS:
        return lang
    return DEFAULT_LANG


def translate(lang: str, key: str, **kwargs: str) -> str:
    lang = _normalize_lang(lang)
    value = TRANSLATIONS.get(lang, {}).get(key)
    if value is None:
        value = TRANSLATIONS.get("en_US", {}).get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except Exception:
            return value
    return value


@pass_context
def t(context, key: str, **kwargs: str) -> str:
    request = context.get("request")
    lang = getattr(getattr(request, "state", None), "lang", DEFAULT_LANG)
    return translate(lang, key, **kwargs)


@pass_context
def degree_label(context, value: str) -> str:
    request = context.get("request")
    lang = getattr(getattr(request, "state", None), "lang", DEFAULT_LANG)
    return _degree_label(lang, value)


@pass_context
def status_label(context, value: str) -> str:
    request = context.get("request")
    lang = getattr(getattr(request, "state", None), "lang", DEFAULT_LANG)
    return _status_label(lang, value)


@pass_context
def allowance_label(context, value: str) -> str:
    request = context.get("request")
    lang = getattr(getattr(request, "state", None), "lang", DEFAULT_LANG)
    return _allowance_label(lang, value)


@pass_context
def run_label(context, value: str) -> str:
    request = context.get("request")
    lang = getattr(getattr(request, "state", None), "lang", DEFAULT_LANG)
    return _run_label(lang, value)


def _lang_from_request(request: Request) -> str:
    return _normalize_lang(request.cookies.get("lang"))


def _current_month_str() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _parse_settlement_month(value: str) -> date:
    try:
        parts = value.split("-")
        year = int(parts[0])
        month = int(parts[1])
        return date(year, month, 1)
    except Exception as exc:
        raise ValueError(f"Invalid settlement_month: {value}") from exc


def _degree_label(lang: str, value: str) -> str:
    mapping = {
        DegreeLevel.BACHELOR.value: "degree.bachelor",
        DegreeLevel.MASTER.value: "degree.master",
        DegreeLevel.PHD.value: "degree.phd",
    }
    return translate(lang, mapping.get(value, value))


def _status_label(lang: str, value: str) -> str:
    mapping = {
        Status.IN_STUDY.value: "status.in_study",
        Status.GRADUATED.value: "status.graduated",
        Status.WITHDRAWN.value: "status.withdrawn",
    }
    return translate(lang, mapping.get(value, value))


def _allowance_label(lang: str, value: str) -> str:
    mapping = {
        "Living": "allowance.living",
        "Study": "allowance.study",
        "ExcessBaggage": "allowance.baggage",
    }
    return translate(lang, mapping.get(value, value))


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _same_month(a: date, b: date) -> bool:
    return a.year == b.year and a.month == b.month


def _monthly_records_for_student(
    student: db.WebStudent,
    settlement_month: date,
    config: AllowanceConfig,
    pay_baggage: bool,
    pay_withdrawal_living: bool,
    lang: str,
) -> Tuple[List[AllowanceRecord], List[str]]:
    ctx = CalculationContext(config=config)
    records: List[AllowanceRecord] = []
    warnings: List[str] = []

    entry_month = _month_start(student.first_entry_date)
    settlement_end = month_end(settlement_month)
    monthly_usd = config.living_allowance_by_degree[student.degree_level]

    def add_living(prorated: bool, metadata: Dict[str, str], rule_id: str, description: str) -> None:
        fraction = proration_fraction(student.first_entry_date) if prorated else Decimal("1")
        usd = monthly_usd * fraction
        if prorated:
            metadata = {**metadata, "fraction": str(fraction)}
        money = ctx.to_money(usd)
        records.append(
            AllowanceRecord(
                student_id=student.student_id,
                allowance_type=AllowanceType.LIVING,
                period_start=settlement_month,
                period_end=settlement_end,
                amount=money,
                rule_id=rule_id,
                description=description,
                metadata=metadata,
            )
        )

    # Living allowance
    if settlement_month >= entry_month:
        if student.status == Status.IN_STUDY:
            if _same_month(settlement_month, entry_month):
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
        elif student.status == Status.GRADUATED:
            if student.graduation_date and settlement_month <= _month_start(student.graduation_date):
                if _same_month(settlement_month, entry_month):
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
            withdrawal_month = _month_start(student.withdrawal_date)
            if settlement_month < withdrawal_month:
                if _same_month(settlement_month, entry_month):
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
                if _same_month(settlement_month, entry_month):
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
        special_case = False
        qualifies_oct = False
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
            money = ctx.to_money(config.study_allowance_usd)
            records.append(
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
                    },
                )
            )

    # Baggage allowance (one-time)
    if pay_baggage:
        if not student.graduation_date:
            warnings.append(translate(lang, "warnings.baggage_missing_graduation", student_id=student.student_id))
        else:
            if settlement_month < _month_start(student.graduation_date):
                warnings.append(translate(lang, "warnings.baggage_before_graduation", student_id=student.student_id))
                return records, warnings
            money = ctx.to_money(config.baggage_allowance_usd)
            records.append(
                AllowanceRecord(
                    student_id=student.student_id,
                    allowance_type=AllowanceType.BAGGAGE,
                    period_start=student.graduation_date,
                    period_end=student.graduation_date,
                    amount=money,
                    rule_id="BAGGAGE_ON_GRADUATION",
                    description="One-time excess baggage allowance after graduation",
                    metadata={"baggage_toggle": "true", "settlement_month": settlement_month.isoformat()},
                )
            )

    return records, warnings


def _run_label(lang: str, label: str) -> str:
    if label == "manual_all":
        return translate(lang, "run.label.manual_all")
    if label == "monthly_settlement":
        return translate(lang, "run.label.monthly_settlement")
    if label.startswith("manual_student:"):
        student_id = label.split("manual_student:", 1)[1]
        return translate(lang, "run.label.manual_student", student_id=student_id)
    return label


@app.on_event("startup")
def _startup() -> None:
    _load_translations()
    TEMPLATES.env.globals["t"] = t
    TEMPLATES.env.globals["degree_label"] = degree_label
    TEMPLATES.env.globals["status_label"] = status_label
    TEMPLATES.env.globals["allowance_label"] = allowance_label
    TEMPLATES.env.globals["run_label"] = run_label
    conn = db.get_connection()
    db.init_db(conn)
    conn.close()


@app.middleware("http")
async def _language_middleware(request: Request, call_next):
    request.state.lang = _lang_from_request(request)
    response = await call_next(request)
    return response


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, settlement_month: str = "") -> HTMLResponse:
    lang = _lang_from_request(request)
    month_value = settlement_month or _current_month_str()
    try:
        settlement_date = _parse_settlement_month(month_value)
    except ValueError:
        settlement_date = date.today().replace(day=1)
        month_value = _current_month_str()

    conn = db.get_connection()
    try:
        config_row = db.get_latest_config(conn)
        counts = db.student_counts(conn)
        latest_run = db.get_latest_run(conn)
        students = db.list_students(conn)
        special_baggage = []
        special_withdrawal = []
        for student in students:
            if student.status == Status.GRADUATED and student.graduation_date:
                if not db.is_baggage_paid(conn, student.student_id):
                    special_baggage.append(student)
            if student.status == Status.WITHDRAWN and student.withdrawal_date:
                if _same_month(_month_start(student.withdrawal_date), settlement_date):
                    special_withdrawal.append(student)
    finally:
        conn.close()

    return TEMPLATES.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "config": config_row,
            "counts": counts,
            "latest_run": latest_run,
            "lang": lang,
            "settlement_month": month_value,
            "special_baggage": special_baggage,
            "special_withdrawal": special_withdrawal,
        },
    )


@app.post("/settlement/run")
def run_settlement_all(
    request: Request,
    settlement_month: str = Form(...),
    baggage_pay: List[str] = Form([]),
    withdrawal_living_pay: List[str] = Form([]),
) -> RedirectResponse:
    lang = _lang_from_request(request)
    settlement_date = _parse_settlement_month(settlement_month)
    conn = db.get_connection()
    warnings: List[str] = []
    try:
        config_row = db.get_latest_config(conn)
        config = db.config_row_to_model(config_row)
        students = db.list_students(conn)
        run = db.create_run(conn, config_row.version, settlement_month, config.fx_rate_usd_to_cny, label="monthly_settlement")
        for student in students:
            pay_baggage = student.student_id in baggage_pay
            pay_withdrawal_living = student.student_id in withdrawal_living_pay
            if pay_baggage and db.is_baggage_paid(conn, student.student_id):
                warnings.append(translate(lang, "warnings.baggage_already_paid", student_id=student.student_id))
                pay_baggage = False
            if pay_withdrawal_living:
                if not (student.withdrawal_date and _same_month(_month_start(student.withdrawal_date), settlement_date)):
                    warnings.append(translate(lang, "warnings.withdrawal_toggle_invalid", student_id=student.student_id))
                    pay_withdrawal_living = False

            records, record_warnings = _monthly_records_for_student(
                student=student,
                settlement_month=settlement_date,
                config=config,
                pay_baggage=pay_baggage,
                pay_withdrawal_living=pay_withdrawal_living,
                lang=lang,
            )
            warnings.extend(record_warnings)
            if records:
                db.save_records(conn, run.run_id, settlement_month, records, config.fx_rate_usd_to_cny)
                if any(r.allowance_type == AllowanceType.BAGGAGE for r in records):
                    db.record_baggage_paid(conn, student.student_id, run.run_id, settlement_month)
    finally:
        conn.close()
    if warnings:
        return RedirectResponse(url="/reports?run_id={}&warnings=1".format(run.run_id), status_code=303)
    return RedirectResponse(url=f"/reports?run_id={run.run_id}", status_code=303)


@app.post("/export-settlement")
def export_settlement(request: Request, format: str = Form("csv"), settlement_month: str = Form("")) -> FileResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        if settlement_month:
            run = db.get_latest_run_for_month(conn, settlement_month)
        else:
            run = db.get_latest_run(conn)
        if not run:
            raise HTTPException(status_code=400, detail=translate(lang, "errors.no_run"))
        records = db.fetch_records_for_run(conn, run.run_id)
        path = _export_records(
            records, format=format, name_prefix=f"settlement_{run.settlement_month or 'all'}", lang=lang
        )
    finally:
        conn.close()
    return FileResponse(path, filename=_filename_from_path(path))


@app.get("/students", response_class=HTMLResponse)
def students(request: Request, q: str = "", degree: str = "", status: str = "") -> HTMLResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        students_list = db.list_students(conn, query=q, degree=degree, status=status)
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse(
        "students.html",
        {
            "request": request,
            "students": students_list,
            "query": q,
            "degree": degree,
            "status": status,
            "degree_levels": [{"value": d.value, "label": _degree_label(lang, d.value)} for d in DegreeLevel],
            "statuses": [{"value": s.value, "label": _status_label(lang, s.value)} for s in Status],
            "lang": lang,
        },
    )


@app.get("/students/new", response_class=HTMLResponse)
def student_new(request: Request) -> HTMLResponse:
    lang = _lang_from_request(request)
    return TEMPLATES.TemplateResponse(
        "student_detail.html",
        {
            "request": request,
            "student": None,
            "errors": [],
            "warnings": [],
            "degree_levels": [{"value": d.value, "label": _degree_label(lang, d.value)} for d in DegreeLevel],
            "statuses": [{"value": s.value, "label": _status_label(lang, s.value)} for s in Status],
            "lang": lang,
        },
    )


@app.post("/students/new")
def student_create(
    request: Request,
    student_id: str = Form(...),
    name: str = Form(...),
    degree_level: str = Form(...),
    first_entry_date: str = Form(...),
    graduation_date: str = Form(""),
    withdrawal_date: str = Form(""),
    status: str = Form(...),
) -> HTMLResponse:
    lang = _lang_from_request(request)
    errors, warnings, student = _build_student_from_form(
        lang,
        student_id, name, degree_level, first_entry_date, graduation_date, withdrawal_date, status
    )
    if errors:
        return TEMPLATES.TemplateResponse(
            "student_detail.html",
            {
                "request": request,
                "student": student,
                "errors": errors,
                "warnings": warnings,
                "degree_levels": [{"value": d.value, "label": _degree_label(lang, d.value)} for d in DegreeLevel],
                "statuses": [{"value": s.value, "label": _status_label(lang, s.value)} for s in Status],
                "lang": lang,
            },
        )
    conn = db.get_connection()
    try:
        db.upsert_student(conn, student)
    finally:
        conn.close()
    return RedirectResponse(url=f"/students/{student.student_id}", status_code=303)


@app.get("/students/{student_id}", response_class=HTMLResponse)
def student_detail(request: Request, student_id: str) -> HTMLResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        student = db.get_student(conn, student_id)
        if not student:
            raise HTTPException(status_code=404, detail=translate(lang, "errors.student_not_found"))
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse(
        "student_detail.html",
        {
            "request": request,
            "student": student,
            "errors": [],
            "warnings": [],
            "degree_levels": [{"value": d.value, "label": _degree_label(lang, d.value)} for d in DegreeLevel],
            "statuses": [{"value": s.value, "label": _status_label(lang, s.value)} for s in Status],
            "lang": lang,
        },
    )


@app.post("/students/{student_id}")
def student_update(
    request: Request,
    student_id: str,
    name: str = Form(...),
    degree_level: str = Form(...),
    first_entry_date: str = Form(...),
    graduation_date: str = Form(""),
    withdrawal_date: str = Form(""),
    status: str = Form(...),
) -> HTMLResponse:
    lang = _lang_from_request(request)
    errors, warnings, student = _build_student_from_form(
        lang,
        student_id, name, degree_level, first_entry_date, graduation_date, withdrawal_date, status
    )
    if errors:
        return TEMPLATES.TemplateResponse(
            "student_detail.html",
            {
                "request": request,
                "student": student,
                "errors": errors,
                "warnings": warnings,
                "degree_levels": [{"value": d.value, "label": _degree_label(lang, d.value)} for d in DegreeLevel],
                "statuses": [{"value": s.value, "label": _status_label(lang, s.value)} for s in Status],
                "lang": lang,
            },
        )
    conn = db.get_connection()
    try:
        db.upsert_student(conn, student)
    finally:
        conn.close()
    return RedirectResponse(url=f"/students/{student.student_id}", status_code=303)


@app.post("/students/{student_id}/calculate")
def student_calculate(student_id: str) -> RedirectResponse:
    settlement_month = _current_month_str()
    settlement_date = _parse_settlement_month(settlement_month)
    conn = db.get_connection()
    try:
        student = db.get_student(conn, student_id)
        if not student:
            raise HTTPException(status_code=404, detail=translate(DEFAULT_LANG, "errors.student_not_found"))
        config_row = db.get_latest_config(conn)
        config = db.config_row_to_model(config_row)
        run = db.create_run(conn, config_row.version, settlement_month, config.fx_rate_usd_to_cny, label=f"manual_student:{student_id}")
        records, _warnings = _monthly_records_for_student(
            student=student,
            settlement_month=settlement_date,
            config=config,
            pay_baggage=False,
            pay_withdrawal_living=False,
            lang=DEFAULT_LANG,
        )
        if records:
            db.save_records(conn, run.run_id, settlement_month, records, config.fx_rate_usd_to_cny)
    finally:
        conn.close()
    return RedirectResponse(url=f"/reports?run_id={run.run_id}&student_id={student_id}", status_code=303)


@app.get("/students/{student_id}/export")
def student_export(request: Request, student_id: str, format: str = "csv") -> FileResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        records = db.fetch_records_for_student(conn, student_id)
        if not records:
            raise HTTPException(status_code=400, detail=translate(lang, "errors.no_records"))
        path = _export_records(records, format=format, name_prefix=f"settlement_{student_id}", lang=lang)
    finally:
        conn.close()
    return FileResponse(path, filename=_filename_from_path(path))


@app.post("/students/import")
def students_import(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    content = file.file.read().decode("utf-8")
    lang = _lang_from_request(request)
    errors, students_list = _parse_students_csv(content, lang)
    if errors:
        return TEMPLATES.TemplateResponse(
            "students_import.html",
            {"request": request, "errors": errors, "filename": file.filename, "lang": lang},
        )
    conn = db.get_connection()
    try:
        for student in students_list:
            db.upsert_student(conn, student)
    finally:
        conn.close()
    return RedirectResponse(url="/students", status_code=303)


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request) -> HTMLResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        config_row = db.get_latest_config(conn)
    finally:
        conn.close()
    return TEMPLATES.TemplateResponse(
        "config.html",
        {
            "request": request,
            "config": config_row,
            "lang": lang,
        },
    )


@app.post("/config")
def config_save(
    living_bachelor: str = Form(...),
    living_master: str = Form(...),
    living_phd: str = Form(...),
    study_allowance: str = Form(...),
    baggage_allowance: str = Form(...),
    fx_rate: str = Form(...),
    issue_study_if_exit_before_oct_entry_year: Optional[str] = Form(None),
    withdrawn_living_default: Optional[str] = Form(None),
) -> RedirectResponse:
    config = AllowanceConfig(
        living_allowance_by_degree={
            DegreeLevel.BACHELOR: Decimal(living_bachelor),
            DegreeLevel.MASTER: Decimal(living_master),
            DegreeLevel.PHD: Decimal(living_phd),
        },
        study_allowance_usd=Decimal(study_allowance),
        baggage_allowance_usd=Decimal(baggage_allowance),
        issue_study_if_exit_before_oct_entry_year=bool(issue_study_if_exit_before_oct_entry_year),
        fx_rate_usd_to_cny=Decimal(fx_rate),
        usd_quantize=Decimal("0.01"),
        cny_quantize=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
    )
    conn = db.get_connection()
    try:
        db.save_config(conn, config, withdrawn_living_default=bool(withdrawn_living_default))
    finally:
        conn.close()
    return RedirectResponse(url="/config", status_code=303)


@app.get("/reports", response_class=HTMLResponse)
def reports(
    request: Request,
    student_id: str = "",
    year: str = "",
    run_id: str = "",
    settlement_month: str = "",
) -> HTMLResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        target_run = None
        if run_id == "latest":
            target_run = db.get_latest_run(conn)
        elif run_id:
            target_run = db.get_run(conn, int(run_id))
        elif settlement_month:
            target_run = db.get_latest_run_for_month(conn, settlement_month)

        if student_id:
            records = db.fetch_records_for_student(conn, student_id, target_run.run_id if target_run else None)
        elif year:
            records = db.fetch_records_for_year(conn, int(year), target_run.run_id if target_run else None)
        elif target_run:
            records = db.fetch_records_for_run(conn, target_run.run_id)
        else:
            latest = db.get_latest_run(conn)
            records = db.fetch_records_for_run(conn, latest.run_id) if latest else []

        totals_cny = sum(Decimal(row["amount_cny"]) for row in records)
        per_student_totals: Dict[str, Decimal] = {}
        for row in records:
            per_student_totals[row["student_id"]] = per_student_totals.get(row["student_id"], Decimal("0")) + Decimal(
                row["amount_cny"]
            )
    finally:
        conn.close()

    return TEMPLATES.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "records": records,
            "student_id": student_id,
            "year": year,
            "run_id": run_id,
            "settlement_month": settlement_month or (target_run.settlement_month if target_run else ""),
            "totals_cny": str(quantize_amount(Decimal(totals_cny), Decimal("0.01"), "ROUND_HALF_UP"))
            if records
            else "0.00",
            "per_student_totals": per_student_totals,
            "warnings_flag": "warnings" in request.query_params,
            "lang": lang,
        },
    )


@app.get("/reports/export")
def reports_export(
    request: Request, student_id: str = "", year: str = "", settlement_month: str = "", format: str = "csv"
) -> FileResponse:
    lang = _lang_from_request(request)
    conn = db.get_connection()
    try:
        if student_id:
            records = db.fetch_records_for_student(conn, student_id)
            name_prefix = f"settlement_{student_id}"
        elif year:
            records = db.fetch_records_for_year(conn, int(year))
            name_prefix = f"settlement_{year}"
        elif settlement_month:
            run = db.get_latest_run_for_month(conn, settlement_month)
            if not run:
                raise HTTPException(status_code=400, detail=translate(lang, "errors.no_run"))
            records = db.fetch_records_for_run(conn, run.run_id)
            name_prefix = f"settlement_{settlement_month}"
        else:
            run = db.get_latest_run(conn)
            if not run:
                raise HTTPException(status_code=400, detail=translate(lang, "errors.no_run"))
            records = db.fetch_records_for_run(conn, run.run_id)
            name_prefix = "settlement_all"
        path = _export_records(records, format=format, name_prefix=name_prefix, lang=lang)
    finally:
        conn.close()
    return FileResponse(path, filename=_filename_from_path(path))


@app.get("/exports/template")
def export_template() -> FileResponse:
    headers = [
        "student_id",
        "name",
        "degree_level",
        "first_entry_date",
        "graduation_date",
        "withdrawal_date",
        "status",
    ]
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    temp.close()
    write_csv(temp.name, [], headers)
    return FileResponse(temp.name, filename="students_template.csv")


@app.get("/lang/{lang_code}")
def set_language(lang_code: str, request: Request) -> RedirectResponse:
    lang = _normalize_lang(lang_code)
    redirect_to = request.headers.get("referer") or "/"
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365)
    return response


def _build_student_from_form(
    lang: str,
    student_id: str,
    name: str,
    degree_level: str,
    first_entry_date: str,
    graduation_date: str,
    withdrawal_date: str,
    status: str,
) -> Tuple[List[str], List[str], Optional[db.WebStudent]]:
    errors: List[str] = []
    warnings: List[str] = []
    try:
        degree = DegreeLevel(degree_level)
    except ValueError:
        errors.append(translate(lang, "errors.invalid_degree"))
        degree = DegreeLevel.BACHELOR
    try:
        status_enum = Status(status)
    except ValueError:
        errors.append(translate(lang, "errors.invalid_status"))
        status_enum = Status.IN_STUDY
    try:
        entry_date = datetime.fromisoformat(first_entry_date).date()
    except ValueError:
        errors.append(translate(lang, "errors.invalid_entry"))
        entry_date = datetime.utcnow().date()
    grad_date = None
    grad_raw = graduation_date.strip()
    if status_enum == Status.IN_STUDY:
        if grad_raw:
            warnings.append(translate(lang, "warnings.graduation_ignored"))
        grad_date = None
    else:
        if grad_raw:
            try:
                grad_date = datetime.fromisoformat(grad_raw).date()
            except ValueError:
                errors.append(translate(lang, "errors.invalid_graduation"))
        if status_enum == Status.GRADUATED and grad_date is None:
            errors.append(translate(lang, "errors.graduation_required"))
    if grad_date and grad_date < entry_date:
        errors.append(translate(lang, "errors.graduation_before_entry"))

    withdrawal = None
    withdrawal_raw = withdrawal_date.strip()
    if status_enum == Status.WITHDRAWN:
        if withdrawal_raw:
            try:
                withdrawal = datetime.fromisoformat(withdrawal_raw).date()
            except ValueError:
                errors.append(translate(lang, "errors.invalid_withdrawal"))
        if withdrawal is None:
            errors.append(translate(lang, "errors.withdrawal_required"))
    else:
        if withdrawal_raw:
            warnings.append(translate(lang, "warnings.withdrawal_ignored"))
        withdrawal = None

    student = None
    try:
        student = db.WebStudent(
            student_id=student_id.strip(),
            name=name.strip(),
            degree_level=degree,
            first_entry_date=entry_date,
            graduation_date=grad_date,
            withdrawal_date=withdrawal,
            status=status_enum,
        )
    except ValueError as exc:
        error_map = {
            "student_id is required": "errors.student_id_required",
            "name is required": "errors.name_required",
            "graduation_date must be on or after first_entry_date": "errors.graduation_before_entry",
            "graduation_date is required for Graduated status": "errors.graduation_required",
        }
        key = error_map.get(str(exc))
        errors.append(translate(lang, key) if key else str(exc))
    return errors, warnings, student


def _parse_students_csv(content: str, lang: str) -> Tuple[List[str], List[db.WebStudent]]:
    errors: List[str] = []
    students: List[db.WebStudent] = []
    reader = csv.DictReader(io.StringIO(content))
    required = [
        "student_id",
        "name",
        "degree_level",
        "first_entry_date",
        "graduation_date",
        "withdrawal_date",
        "status",
    ]
    if not reader.fieldnames:
        return [translate(lang, "errors.csv_no_headers")], []
    missing = [name for name in required if name not in reader.fieldnames]
    if missing:
        return [translate(lang, "errors.csv_missing_columns", columns=", ".join(missing))], []

    for idx, row in enumerate(reader, start=2):
        try:
            student_id = row["student_id"].strip()
            name = row["name"].strip()
            degree_raw = row["degree_level"].strip()
            status_raw = row["status"].strip()
            try:
                degree = DegreeLevel(degree_raw)
            except ValueError:
                raise ValueError(translate(lang, "errors.invalid_degree"))
            try:
                status_enum = Status(status_raw)
            except ValueError:
                raise ValueError(translate(lang, "errors.invalid_status"))
            try:
                entry_date = datetime.fromisoformat(row["first_entry_date"].strip()).date()
            except ValueError:
                raise ValueError(translate(lang, "errors.invalid_entry"))
            grad_date = None
            grad_raw = row["graduation_date"].strip()
            if status_enum == Status.IN_STUDY:
                grad_date = None
            else:
                if grad_raw:
                    try:
                        grad_date = datetime.fromisoformat(grad_raw).date()
                    except ValueError:
                        raise ValueError(translate(lang, "errors.invalid_graduation"))
                if status_enum == Status.GRADUATED and grad_date is None:
                    raise ValueError(translate(lang, "errors.graduation_required"))
            withdrawal = None
            withdrawal_raw = row["withdrawal_date"].strip()
            if status_enum == Status.WITHDRAWN:
                if withdrawal_raw:
                    try:
                        withdrawal = datetime.fromisoformat(withdrawal_raw).date()
                    except ValueError:
                        raise ValueError(translate(lang, "errors.invalid_withdrawal"))
                if withdrawal is None:
                    raise ValueError(translate(lang, "errors.withdrawal_required"))
            if grad_date and grad_date < entry_date:
                raise ValueError(translate(lang, "errors.graduation_before_entry"))

            student = db.WebStudent(
                student_id=student_id,
                name=name,
                degree_level=degree,
                first_entry_date=entry_date,
                graduation_date=grad_date,
                withdrawal_date=withdrawal,
                status=status_enum,
            )
            students.append(student)
        except Exception as exc:
            error_map = {
                "student_id is required": "errors.student_id_required",
                "name is required": "errors.name_required",
                "graduation_date must be on or after first_entry_date": "errors.graduation_before_entry",
            }
            mapped = error_map.get(str(exc))
            message = translate(lang, mapped) if mapped else str(exc)
            errors.append(translate(lang, "errors.csv_row", row=str(idx), error=message))
    return errors, students


def _export_records(records: List, format: str, name_prefix: str, lang: str) -> str:
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
        ("metadata", "export.header.metadata"),
    ]
    headers = [translate(lang, key) for _, key in header_keys]
    rows = []
    for row in records:
        row_values = {
            "run_id": row["run_id"],
            "settlement_month": row["settlement_month"],
            "student_id": row["student_id"],
            "allowance_type": _allowance_label(lang, row["allowance_type"]),
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "amount_usd": row["amount_usd"],
            "fx_rate": row["fx_rate"],
            "amount_cny": row["amount_cny"],
            "rule_id": row["rule_id"],
            "description": row["description"],
            "metadata": row["metadata_json"],
        }
        localized = {translate(lang, key): row_values[field] for field, key in header_keys}
        rows.append(localized)

    suffix = ".xlsx" if format == "xlsx" else ".csv"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()

    if format == "xlsx":
        sheet_name = translate(lang, "export.sheet")
        tables = [Table(sheet_name, rows, headers)]
        write_excel_xlsx(temp.name, tables)
    else:
        write_csv(temp.name, rows, headers)
    return temp.name


def _filename_from_path(path: str) -> str:
    name = path.split("/")[-1]
    if name.startswith("tmp"):
        return f"settlement{path[path.rfind('.'):]}"
    return name
