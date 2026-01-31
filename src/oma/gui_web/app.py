from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..config import AllowanceConfig
from ..models import DegreeLevel, Status
from ..storage import db
from ..storage.backup import create_backup, restore_backup
from ..gui.exporter import export_monthly_settlement_excel, export_records
from ..schema import STUDENT_CSV_HEADERS
from ..gui.i18n import Translator
from ..gui.settings import load_settings, save_settings
from ..gui.settlement import compute_monthly_settlement, parse_settlement_month, same_month

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    normalized = value.replace("/", "-").replace(".", "-")
    return datetime.strptime(normalized, "%Y-%m-%d").date()


class Backend(QObject):
    def __init__(self, translator: Translator, conn) -> None:
        super().__init__()
        self.translator = translator
        self.conn = conn

    def _lang(self) -> str:
        return self.translator.lang

    @Slot(result=str)
    def get_state(self) -> str:
        settings = load_settings()
        settlement_month = settings.get("settlement_month") or date.today().strftime("%Y-%m")
        cfg = db.get_latest_config(self.conn)
        students = db.list_students(self.conn)
        counts = db.student_counts(self.conn)
        run = db.get_latest_run_for_month(self.conn, settlement_month)
        special = self._special_list(settlement_month)
        records = db.fetch_records_for_run(self.conn, run.run_id) if run else []
        per_student = self._per_student_totals(records, students)
        return json.dumps(
            {
                "config": asdict(cfg),
                "run": asdict(run) if run else None,
                "students": [self._student_to_dict(s) for s in students],
                "counts": counts,
                "settlement_month": settlement_month,
                "special": special,
                "language": self._lang(),
                "records": [r.__dict__ for r in records],
                "per_student": per_student,
                "runs": [asdict(r) for r in db.list_runs(self.conn)],
            },
            ensure_ascii=False,
        )

    @Slot(str, result=str)
    def set_language(self, lang: str) -> str:
        self.translator.set_language(lang)
        settings = load_settings()
        settings["language"] = lang
        save_settings(settings)
        return json.dumps({"ok": True})

    @Slot(str, result=str)
    def set_settlement_month(self, value: str) -> str:
        if value:
            settings = load_settings()
            settings["settlement_month"] = value
            save_settings(settings)
        return json.dumps({"ok": True})

    @Slot(result=str)
    def get_translations(self) -> str:
        return json.dumps(self.translator.translations.get(self._lang(), {}), ensure_ascii=False)

    @Slot(str, result=str)
    def list_students(self, query: str) -> str:
        students = db.list_students(self.conn, query=query)
        return json.dumps([asdict(s) for s in students], ensure_ascii=False)

    @Slot(str, result=str)
    def save_student(self, payload: str) -> str:
        data = json.loads(payload)
        student, errors, warnings = self._validate_student(data)
        if errors:
            return json.dumps({"ok": False, "errors": errors}, ensure_ascii=False)
        if student is None:
            return json.dumps({"ok": False, "errors": [self.translator.t("error.required")]})
        db.upsert_student(self.conn, student)
        return json.dumps({"ok": True, "warnings": warnings}, ensure_ascii=False)

    @Slot(str, result=str)
    def delete_student(self, student_id: str) -> str:
        db.delete_student(self.conn, student_id)
        return json.dumps({"ok": True})

    @Slot(str, result=str)
    def import_students(self, csv_text: str) -> str:
        import csv
        import io

        reader = csv.DictReader(io.StringIO(csv_text))
        if not reader.fieldnames:
            return json.dumps(
                {"ok": False, "errors": [self.translator.t("error.csv_header_mismatch")]},
                ensure_ascii=False,
            )
        fieldnames = list(reader.fieldnames)
        if fieldnames and fieldnames[0].startswith("\ufeff"):
            fieldnames[0] = fieldnames[0].lstrip("\ufeff")
        if fieldnames != STUDENT_CSV_HEADERS:
            expected = ", ".join(STUDENT_CSV_HEADERS)
            return json.dumps(
                {"ok": False, "errors": [self.translator.t("error.csv_header_mismatch", expected=expected)]},
                ensure_ascii=False,
            )
        errors = []
        warnings = []
        for idx, row in enumerate(reader, start=2):
            try:
                if None in row and row[None]:
                    errors.append(f"Row {idx}: {self.translator.t('error.csv_header_mismatch')}")
                    continue
                student, row_errors, row_warnings = self._validate_student(row)
                if row_errors:
                    for err in row_errors:
                        errors.append(f"Row {idx}: {err}")
                    continue
                if student is None:
                    errors.append(f"Row {idx}: {self.translator.t('error.required')}")
                    continue
                db.upsert_student(self.conn, student)
                warnings.extend([f"Row {idx}: {w}" for w in row_warnings])
            except Exception as exc:
                errors.append(f"Row {idx}: {exc}")
        return json.dumps({"ok": len(errors) == 0, "errors": errors, "warnings": warnings}, ensure_ascii=False)

    @Slot(result=str)
    def get_csv_template(self) -> str:
        return ",".join(STUDENT_CSV_HEADERS)

    @Slot(result=str)
    def export_csv_template(self) -> str:
        settings = load_settings()
        export_dir = self._export_dir(settings, key="csv_dir")
        caption = self.translator.t("dialog.save_csv")
        filter_text = self.translator.t("dialog.filter.csv")
        target, _ = QFileDialog.getSaveFileName(
            None, caption, str(export_dir / "students_template.csv"), filter_text
        )
        if not target:
            return json.dumps({"ok": True, "cancelled": True})
        if not target.lower().endswith(".csv"):
            target = f"{target}.csv"
        try:
            Path(target).write_text(self.get_csv_template() + "\n", encoding="utf-8")
        except Exception:
            return json.dumps({"ok": False, "error": "save_failed"}, ensure_ascii=False)
        settings["csv_dir"] = str(Path(target).parent)
        save_settings(settings)
        return json.dumps({"ok": True})

    @Slot(str, result=str)
    def save_config(self, payload: str) -> str:
        data = json.loads(payload)
        config = AllowanceConfig(
            living_allowance_by_degree={
                DegreeLevel.BACHELOR: Decimal(str(data["living_bachelor"])),
                DegreeLevel.MASTER: Decimal(str(data["living_master"])),
                DegreeLevel.PHD: Decimal(str(data["living_phd"])),
            },
            study_allowance_usd=Decimal(str(data["study_allowance"])),
            baggage_allowance_usd=Decimal(str(data["baggage_allowance"])),
            study_allowance_month=int(data.get("study_allowance_month", 10)),
            issue_study_if_entry_month=bool(data.get("issue_study_if_entry_month")),
            issue_study_if_exit_before_oct_entry_year=data["policy_switch"],
            fx_rate_usd_to_cny=Decimal(str(data["fx_rate"])),
            usd_quantize="0.01",
            cny_quantize="0.01",
            rounding_mode="ROUND_HALF_UP",
            rounding_policy=data.get("rounding_policy", "final_only"),
        )
        db.save_config(self.conn, config, withdrawn_living_default=data["withdrawn_default"])
        return json.dumps({"ok": True})

    @Slot(str, str, str, result=str)
    def run_settlement(self, settlement_month: str, baggage_ids: str, withdrawal_ids: str) -> str:
        cfg_row = db.get_latest_config(self.conn)
        config = db.config_row_to_model(cfg_row)
        students = db.list_students(self.conn)
        safe_month = self._normalize_month(settlement_month)
        settlement_date = parse_settlement_month(safe_month)
        baggage = set([s for s in baggage_ids.split(",") if s])
        withdrawal = set([s for s in withdrawal_ids.split(",") if s])

        result = compute_monthly_settlement(
            students=students,
            settlement_month=settlement_date,
            config=config,
            baggage_pay_ids=baggage,
            withdrawal_living_ids=withdrawal,
        )
        run = db.create_run(self.conn, cfg_row.version, safe_month, config.fx_rate_usd_to_cny)
        if result.records:
            db.save_records(self.conn, run.run_id, safe_month, result.records, config.fx_rate_usd_to_cny)
            for r in result.records:
                if r.allowance_type.value == "ExcessBaggage":
                    db.record_baggage_paid(self.conn, r.student_id, run.run_id, safe_month)
        return json.dumps({"ok": True, "run_id": run.run_id, "warnings": result.warnings}, ensure_ascii=False)

    @Slot(str, result=str)
    def get_reports(self, settlement_month: str) -> str:
        run = db.get_latest_run_for_month(self.conn, settlement_month)
        if not run:
            return json.dumps({"ok": False, "error": "no_run"})
        records = db.fetch_records_for_run(self.conn, run.run_id)
        students = db.list_students(self.conn)
        per_student = self._per_student_totals(records, students)
        return json.dumps(
            {"ok": True, "run": asdict(run), "records": [r.__dict__ for r in records], "per_student": per_student},
            ensure_ascii=False,
        )

    @Slot(str, str, result=str)
    def export_settlement(self, settlement_month: str, fmt: str) -> str:
        run = db.get_latest_run_for_month(self.conn, self._normalize_month(settlement_month))
        if not run:
            return json.dumps({"ok": False})
        records = db.fetch_records_for_run(self.conn, run.run_id)
        temp_path = export_records(records, self.translator, fmt)
        target, _ = QFileDialog.getSaveFileName(None, "", f"settlement_{settlement_month}.{fmt}")
        if target:
            Path(target).write_bytes(Path(temp_path).read_bytes())
        return json.dumps({"ok": True})

    @Slot(str, str, result=str)
    def export_settlement_excel(self, settlement_month: str, run_id: str) -> str:
        run = None
        if run_id:
            try:
                run = db.get_run(self.conn, int(run_id))
            except Exception:
                run = None
        if run is None:
            run = db.get_latest_run_for_month(self.conn, self._normalize_month(settlement_month))
        if not run:
            return json.dumps({"ok": False, "error": "no_run"})
        records = db.fetch_records_for_run(self.conn, run.run_id)
        students = db.list_students(self.conn)
        config_row = db.get_config_by_version(self.conn, run.config_version)
        temp_path = export_monthly_settlement_excel(
            run=run,
            config_row=config_row,
            students=students,
            records=records,
            translator=self.translator,
        )
        filename = f"OmanSettlement_{run.settlement_month}_{run.run_id}.xlsx"
        settings = load_settings()
        export_dir = self._export_dir(settings, key="export_dir")
        default_path = export_dir / filename
        caption = self.translator.t("dialog.save_excel")
        filter_text = self.translator.t("dialog.filter.xlsx")
        target, _ = QFileDialog.getSaveFileName(None, caption, str(default_path), filter_text)
        if not target:
            return json.dumps({"ok": True, "cancelled": True})
        if not target.lower().endswith(".xlsx"):
            target = f"{target}.xlsx"
        try:
            Path(target).write_bytes(Path(temp_path).read_bytes())
        except Exception:
            return json.dumps({"ok": False, "error": "save_failed"}, ensure_ascii=False)
        settings["export_dir"] = str(Path(target).parent)
        save_settings(settings)
        return json.dumps({"ok": True})

    @Slot(str, result=str)
    def delete_run(self, run_id: str) -> str:
        try:
            db.delete_run(self.conn, int(run_id))
        except Exception:
            return json.dumps({"ok": False}, ensure_ascii=False)
        return json.dumps({"ok": True})

    @Slot(str, result=str)
    def get_special(self, settlement_month: str) -> str:
        safe_month = self._normalize_month(settlement_month)
        return json.dumps({"ok": True, "special": self._special_list(safe_month)}, ensure_ascii=False)

    @Slot(str, result=str)
    def get_run_info(self, settlement_month: str) -> str:
        safe_month = self._normalize_month(settlement_month)
        run = db.get_latest_run_for_month(self.conn, safe_month)
        return json.dumps({"ok": True, "run": asdict(run) if run else None}, ensure_ascii=False)

    @Slot(result=str)
    def backup(self) -> str:
        path = create_backup()
        return json.dumps({"ok": True, "path": str(path)})

    @Slot(str, result=str)
    def restore(self, mode: str) -> str:
        path, _ = QFileDialog.getOpenFileName(None, "", "", "Backup (*.zip)")
        if not path:
            return json.dumps({"ok": False})
        added, skipped = restore_backup(Path(path), mode)
        return json.dumps({"ok": True, "added": added, "skipped": skipped})

    def _special_list(self, settlement_month: str) -> Dict:
        settlement_date = parse_settlement_month(settlement_month)
        students = db.list_students(self.conn)
        cfg = db.get_latest_config(self.conn)
        baggage = []
        withdrawal = []
        for s in students:
            if s.status == Status.GRADUATED and s.graduation_date and not db.is_baggage_paid(self.conn, s.student_id):
                baggage.append(self._student_to_dict(s))
            if s.status == Status.WITHDRAWN and s.withdrawal_date:
                if same_month(s.withdrawal_date, settlement_date):
                    item = self._student_to_dict(s)
                    item["default_checked"] = bool(cfg.withdrawn_living_default)
                    withdrawal.append(item)
        return {"baggage": baggage, "withdrawal": withdrawal}

    def _export_dir(self, settings: Dict[str, str], key: str) -> Path:
        last_dir = settings.get(key)
        if last_dir:
            path = Path(last_dir)
            if path.exists():
                return path
        home = Path.home()
        for name in ("Desktop", "Documents"):
            candidate = home / name
            if candidate.exists():
                return candidate
        return home

    def _normalize_month(self, value: str) -> str:
        if value:
            try:
                parse_settlement_month(value)
                return value
            except Exception:
                pass
        settings = load_settings()
        saved = settings.get("settlement_month")
        if saved:
            try:
                parse_settlement_month(saved)
                return saved
            except Exception:
                pass
        return date.today().strftime("%Y-%m")

    def _student_to_dict(self, student: db.StudentRow) -> Dict[str, str]:
        return {
            "student_id": student.student_id,
            "name": student.name,
            "degree_level": student.degree_level.value,
            "first_entry_date": student.first_entry_date.isoformat(),
            "status": student.status.value,
            "graduation_date": student.graduation_date.isoformat() if student.graduation_date else "",
            "withdrawal_date": student.withdrawal_date.isoformat() if student.withdrawal_date else "",
        }

    def _validate_student(self, data: Dict[str, str]) -> tuple[db.StudentRow | None, List[str], List[str]]:
        errors: List[str] = []
        warnings: List[str] = []

        student_id = (data.get("student_id") or "").strip()
        name = (data.get("name") or "").strip()
        if not student_id:
            errors.append(f"{self.translator.t('error.required')} ({self.translator.t('field.student_id')})")
        if not name:
            errors.append(f"{self.translator.t('error.required')} ({self.translator.t('field.name')})")

        try:
            degree_level = DegreeLevel((data.get("degree_level") or "").strip())
        except Exception:
            errors.append(f"{self.translator.t('error.required')} ({self.translator.t('field.degree')})")
            degree_level = None

        try:
            status = Status((data.get("status") or "").strip())
        except Exception:
            errors.append(f"{self.translator.t('error.required')} ({self.translator.t('field.status')})")
            status = None

        entry_raw = (data.get("first_entry_date") or "").strip()
        entry_date = None
        if entry_raw:
            try:
                entry_date = parse_date(entry_raw)
            except Exception:
                errors.append(f"{self.translator.t('error.invalid_date')} ({self.translator.t('field.entry_date')})")
        else:
            errors.append(f"{self.translator.t('error.required')} ({self.translator.t('field.entry_date')})")

        graduation_raw = (data.get("graduation_date") or "").strip()
        withdrawal_raw = (data.get("withdrawal_date") or "").strip()
        graduation_date = None
        withdrawal_date = None

        if graduation_raw:
            try:
                graduation_date = parse_date(graduation_raw)
            except Exception:
                errors.append(
                    f"{self.translator.t('error.invalid_date')} ({self.translator.t('field.graduation_date')})"
                )
        if withdrawal_raw:
            try:
                withdrawal_date = parse_date(withdrawal_raw)
            except Exception:
                errors.append(
                    f"{self.translator.t('error.invalid_date')} ({self.translator.t('field.withdrawal_date')})"
                )

        if status == Status.GRADUATED:
            if graduation_date is None:
                errors.append(self.translator.t("error.graduation_required"))
        elif status == Status.IN_STUDY:
            if graduation_date is not None:
                warnings.append(self.translator.t("hint.graduation"))
                graduation_date = None
        elif status == Status.WITHDRAWN:
            if withdrawal_date is None:
                errors.append(self.translator.t("error.withdrawal_required"))

        if status != Status.WITHDRAWN:
            withdrawal_date = None

        if entry_date and graduation_date and graduation_date < entry_date:
            errors.append(self.translator.t("error.entry_before_graduation"))
        if entry_date and withdrawal_date and withdrawal_date < entry_date:
            errors.append(self.translator.t("error.entry_before_withdrawal"))

        if errors or degree_level is None or status is None or entry_date is None:
            return None, errors, warnings

        student = db.StudentRow(
            student_id=student_id,
            name=name,
            degree_level=degree_level,
            first_entry_date=entry_date,
            status=status,
            graduation_date=graduation_date if status != Status.IN_STUDY else None,
            withdrawal_date=withdrawal_date if status == Status.WITHDRAWN else None,
        )
        return student, errors, warnings

    def _per_student_totals(self, records: List[db.RecordRow], students: List[db.StudentRow]) -> List[Dict[str, str]]:
        name_map = {s.student_id: s.name for s in students}
        totals: Dict[str, Decimal] = {}
        for r in records:
            totals.setdefault(r.student_id, Decimal("0"))
            totals[r.student_id] += Decimal(r.amount_cny)
        result = []
        for student_id, amount in totals.items():
            result.append(
                {
                    "student_id": student_id,
                    "name": name_map.get(student_id, ""),
                    "amount_cny": str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                }
            )
        return result


class WebApp(QWebEngineView):
    def __init__(self) -> None:
        super().__init__()
        self.conn = db.connect()
        db.init_db(self.conn)
        self.settings = load_settings()
        self.translator = Translator(Path(__file__).resolve().parents[1] / "i18n")
        self.translator.set_language(self.settings.get("language", "zh_CN"))

        self.channel = QWebChannel(self.page())
        self.backend = Backend(self.translator, self.conn)
        self.channel.registerObject("backend", self.backend)
        self.page().setWebChannel(self.channel)

        self.load(QUrl.fromLocalFile(str(ASSETS_DIR / "index.html")))

    def closeEvent(self, event) -> None:
        self.conn.close()
        event.accept()


def run() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    window = WebApp()
    window.resize(1280, 800)
    window.show()
    app.exec()
