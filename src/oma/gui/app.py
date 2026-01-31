from __future__ import annotations

import csv
import json
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from ..config import AllowanceConfig
from ..models import DegreeLevel, Status, AllowanceType
from ..storage import db
from ..storage.backup import create_backup, restore_backup
from ..storage.paths import backup_dir
from .exporter import export_records
from .i18n import Translator
from .settings import load_settings, save_settings
from .settlement import compute_monthly_settlement, parse_settlement_month


def parse_date(value: str) -> Optional[date]:
    value = value.strip()
    if not value:
        return None
    normalized = value.replace("/", "-").replace(".", "-")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("invalid_date") from exc


def format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else ""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.translator = Translator(Path(__file__).resolve().parents[1] / "i18n")
        self.translator.set_language(self.settings.get("language", "zh_CN"))

        self.conn = db.connect()
        db.init_db(self.conn)

        self.setWindowTitle(self.translator.t("app.title"))
        self._build_ui()
        self._load_all()

    def closeEvent(self, event) -> None:
        self.conn.close()
        event.accept()

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._build_dashboard()
        self._build_students()
        self._build_config()
        self._build_reports()
        self._build_backup()
        self._build_about()

        self._build_toolbar()
        self._retranslate()

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("lang")
        bar.setMovable(False)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(self.translator.t("lang.zh"), "zh_CN")
        self.lang_combo.addItem(self.translator.t("lang.en"), "en_US")
        current = self.translator.lang
        index = 0 if current == "zh_CN" else 1
        self.lang_combo.setCurrentIndex(index)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        bar.addWidget(QLabel("  "))
        bar.addWidget(self.lang_combo)

    def _on_lang_changed(self) -> None:
        lang = self.lang_combo.currentData()
        self.translator.set_language(lang)
        self.settings["language"] = lang
        save_settings(self.settings)
        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(self.translator.t("app.title"))
        self.tabs.setTabText(0, self.translator.t("tab.dashboard"))
        self.tabs.setTabText(1, self.translator.t("tab.students"))
        self.tabs.setTabText(2, self.translator.t("tab.config"))
        self.tabs.setTabText(3, self.translator.t("tab.reports"))
        self.tabs.setTabText(4, self.translator.t("tab.backup"))
        self.tabs.setTabText(5, self.translator.t("tab.about"))
        self._refresh_texts()

    def _refresh_texts(self) -> None:
        self.dashboard_title.setText(self.translator.t("dashboard.settlement_month"))
        self.run_button.setText(self.translator.t("dashboard.run"))
        self.special_title.setText(self.translator.t("special.title"))
        self.special_hint.setText(self.translator.t("special.hint"))
        self.export_csv_btn.setText(self.translator.t("reports.export_csv"))
        self.export_xlsx_btn.setText(self.translator.t("reports.export_xlsx"))
        self.students_title.setText(self.translator.t("students.title"))
        self.student_add_btn.setText(self.translator.t("students.add"))
        self.student_edit_btn.setText(self.translator.t("students.edit"))
        self.student_delete_btn.setText(self.translator.t("students.delete"))
        self.student_import_btn.setText(self.translator.t("students.import"))
        self.student_template_btn.setText(self.translator.t("students.template"))
        self.config_title.setText(self.translator.t("config.title"))
        self.config_save_btn.setText(self.translator.t("config.save"))
        self.reports_title.setText(self.translator.t("reports.title"))
        self.backup_title.setText(self.translator.t("backup.title"))
        self.backup_create_btn.setText(self.translator.t("backup.create"))
        self.backup_restore_btn.setText(self.translator.t("backup.restore"))
        self.backup_replace_btn.setText(self.translator.t("backup.restore_replace"))
        self.backup_merge_btn.setText(self.translator.t("backup.restore_merge"))
        self.about_title.setText(self.translator.t("about.title"))
        self.about_version.setText(f"{self.translator.t('about.version')}: 1.0.0")
        self._refresh_tables()

    def _build_dashboard(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QHBoxLayout()
        self.dashboard_title = QLabel()
        self.settlement_month = QDateEdit()
        self.settlement_month.setDisplayFormat("yyyy-MM")
        self.settlement_month.setDate(date.today().replace(day=1))
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run_settlement)
        header.addWidget(self.dashboard_title)
        header.addWidget(self.settlement_month)
        header.addWidget(self.run_button)
        header.addStretch()
        layout.addLayout(header)

        self.special_title = QLabel()
        self.special_hint = QLabel()
        layout.addWidget(self.special_title)
        layout.addWidget(self.special_hint)
        self.special_table = QTableWidget(0, 5)
        layout.addWidget(self.special_table)

        export_layout = QHBoxLayout()
        self.export_csv_btn = QPushButton()
        self.export_xlsx_btn = QPushButton()
        self.export_csv_btn.clicked.connect(lambda: self._export_current("csv"))
        self.export_xlsx_btn.clicked.connect(lambda: self._export_current("xlsx"))
        export_layout.addWidget(self.export_csv_btn)
        export_layout.addWidget(self.export_xlsx_btn)
        export_layout.addStretch()
        layout.addLayout(export_layout)

        self.run_info = QLabel("")
        layout.addWidget(self.run_info)

        self.tabs.addTab(widget, "")

    def _build_students(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.students_title = QLabel()
        layout.addWidget(self.students_title)

        action_layout = QHBoxLayout()
        self.student_add_btn = QPushButton()
        self.student_edit_btn = QPushButton()
        self.student_delete_btn = QPushButton()
        self.student_import_btn = QPushButton()
        self.student_template_btn = QPushButton()
        self.student_add_btn.clicked.connect(self._add_student)
        self.student_edit_btn.clicked.connect(self._edit_student)
        self.student_delete_btn.clicked.connect(self._delete_student)
        self.student_import_btn.clicked.connect(self._import_students)
        self.student_template_btn.clicked.connect(self._export_template)
        action_layout.addWidget(self.student_add_btn)
        action_layout.addWidget(self.student_edit_btn)
        action_layout.addWidget(self.student_delete_btn)
        action_layout.addWidget(self.student_import_btn)
        action_layout.addWidget(self.student_template_btn)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        self.students_table = QTableWidget(0, 7)
        layout.addWidget(self.students_table)

        self.student_status = QLabel("")
        layout.addWidget(self.student_status)

        self.tabs.addTab(widget, "")

    def _build_config(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.config_title = QLabel()
        layout.addWidget(self.config_title)

        form = QFormLayout()
        self.living_bachelor = QLineEdit()
        self.living_master = QLineEdit()
        self.living_phd = QLineEdit()
        self.study_allowance = QLineEdit()
        self.baggage_allowance = QLineEdit()
        self.fx_rate = QLineEdit()
        self.policy_switch = QCheckBox()
        self.withdrawn_default = QCheckBox()
        form.addRow(self.translator.t("degree.bachelor"), self.living_bachelor)
        form.addRow(self.translator.t("degree.master"), self.living_master)
        form.addRow(self.translator.t("degree.phd"), self.living_phd)
        form.addRow(self.translator.t("config.study"), self.study_allowance)
        form.addRow(self.translator.t("config.baggage"), self.baggage_allowance)
        form.addRow(self.translator.t("config.fx_rate"), self.fx_rate)
        form.addRow(self.translator.t("config.policy"), self.policy_switch)
        form.addRow(self.translator.t("config.withdrawn_default"), self.withdrawn_default)
        layout.addLayout(form)

        self.config_save_btn = QPushButton()
        self.config_save_btn.clicked.connect(self._save_config)
        for field in [
            self.living_bachelor,
            self.living_master,
            self.living_phd,
            self.study_allowance,
            self.baggage_allowance,
            self.fx_rate,
        ]:
            field.editingFinished.connect(self._save_config)
        self.policy_switch.stateChanged.connect(self._save_config)
        self.withdrawn_default.stateChanged.connect(self._save_config)
        layout.addWidget(self.config_save_btn)
        self.config_status = QLabel("")
        layout.addWidget(self.config_status)

        self.tabs.addTab(widget, "")

    def _build_reports(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.reports_title = QLabel()
        layout.addWidget(self.reports_title)

        self.per_student_table = QTableWidget(0, 2)
        layout.addWidget(self.per_student_table)

        self.records_table = QTableWidget(0, 10)
        layout.addWidget(self.records_table)

        self.tabs.addTab(widget, "")

    def _build_backup(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.backup_title = QLabel()
        layout.addWidget(self.backup_title)

        self.backup_create_btn = QPushButton()
        self.backup_restore_btn = QPushButton()
        self.backup_replace_btn = QPushButton()
        self.backup_merge_btn = QPushButton()
        self.backup_create_btn.clicked.connect(self._backup)
        self.backup_restore_btn.clicked.connect(self._restore_prompt)
        self.backup_replace_btn.clicked.connect(lambda: self._restore("replace"))
        self.backup_merge_btn.clicked.connect(lambda: self._restore("merge"))
        layout.addWidget(self.backup_create_btn)
        layout.addWidget(self.backup_restore_btn)
        layout.addWidget(self.backup_replace_btn)
        layout.addWidget(self.backup_merge_btn)
        self.backup_status = QLabel("")
        layout.addWidget(self.backup_status)

        self.tabs.addTab(widget, "")

    def _build_about(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.about_title = QLabel()
        self.about_version = QLabel()
        layout.addWidget(self.about_title)
        layout.addWidget(self.about_version)
        layout.addStretch()
        self.tabs.addTab(widget, "")

    def _load_all(self) -> None:
        self._load_students()
        self._load_config()
        self._load_special_panel()
        self._load_reports()

    def _refresh_tables(self) -> None:
        self._load_students()
        self._load_special_panel()
        self._load_reports()

    def _load_students(self) -> None:
        students = db.list_students(self.conn)
        self.students_table.setRowCount(len(students))
        headers = [
            self.translator.t("field.student_id"),
            self.translator.t("field.name"),
            self.translator.t("field.degree"),
            self.translator.t("field.entry_date"),
            self.translator.t("field.status"),
            self.translator.t("field.graduation_date"),
            self.translator.t("field.withdrawal_date"),
        ]
        self.students_table.setColumnCount(len(headers))
        self.students_table.setHorizontalHeaderLabels(headers)
        for row, student in enumerate(students):
            self.students_table.setItem(row, 0, QTableWidgetItem(student.student_id))
            self.students_table.setItem(row, 1, QTableWidgetItem(student.name))
            self.students_table.setItem(row, 2, QTableWidgetItem(self._degree_label(student.degree_level)))
            self.students_table.setItem(row, 3, QTableWidgetItem(format_date(student.first_entry_date)))
            self.students_table.setItem(row, 4, QTableWidgetItem(self._status_label(student.status)))
            self.students_table.setItem(row, 5, QTableWidgetItem(format_date(student.graduation_date)))
            self.students_table.setItem(row, 6, QTableWidgetItem(format_date(student.withdrawal_date)))

    def _load_config(self) -> None:
        cfg = db.get_latest_config(self.conn)
        self.living_bachelor.setText(cfg.living_allowance_bachelor)
        self.living_master.setText(cfg.living_allowance_master)
        self.living_phd.setText(cfg.living_allowance_phd)
        self.study_allowance.setText(cfg.study_allowance_usd)
        self.baggage_allowance.setText(cfg.baggage_allowance_usd)
        self.fx_rate.setText(cfg.fx_rate_usd_to_cny)
        self.policy_switch.setChecked(bool(cfg.issue_study_if_exit_before_oct_entry_year))
        self.withdrawn_default.setChecked(bool(cfg.withdrawn_living_default))

    def _load_special_panel(self) -> None:
        settlement = self.settlement_month.date().toPython()
        students = db.list_students(self.conn)
        eligible = []
        cfg = db.get_latest_config(self.conn)
        for s in students:
            if s.status == Status.GRADUATED and s.graduation_date and not db.is_baggage_paid(self.conn, s.student_id):
                eligible.append((s, "baggage"))
            if s.status == Status.WITHDRAWN and s.withdrawal_date:
                if s.withdrawal_date.year == settlement.year and s.withdrawal_date.month == settlement.month:
                    eligible.append((s, "withdrawal"))
        self.special_table.setRowCount(len(eligible))
        headers = [
            self.translator.t("field.student_id"),
            self.translator.t("field.name"),
            self.translator.t("field.status"),
            self.translator.t("special.type"),
            self.translator.t("special.action"),
        ]
        self.special_table.setHorizontalHeaderLabels(headers)
        for row, (student, typ) in enumerate(eligible):
            self.special_table.setItem(row, 0, QTableWidgetItem(student.student_id))
            self.special_table.setItem(row, 1, QTableWidgetItem(student.name))
            self.special_table.setItem(row, 2, QTableWidgetItem(self._status_label(student.status)))
            if typ == "baggage":
                self.special_table.setItem(row, 3, QTableWidgetItem(self.translator.t("special.baggage")))
                checkbox = QCheckBox(self.translator.t("special.baggage_toggle"))
            else:
                self.special_table.setItem(row, 3, QTableWidgetItem(self.translator.t("special.withdrawal")))
                checkbox = QCheckBox(self.translator.t("special.withdrawal_toggle"))
                checkbox.setChecked(bool(cfg.withdrawn_living_default))
            checkbox.setProperty("student_id", student.student_id)
            checkbox.setProperty("special_type", typ)
            self.special_table.setCellWidget(row, 4, checkbox)

    def _load_reports(self) -> None:
        run = db.get_latest_run(self.conn)
        if not run:
            self.per_student_table.setRowCount(0)
            self.records_table.setRowCount(0)
            return
        records = db.fetch_records_for_run(self.conn, run.run_id)
        totals: Dict[str, Decimal] = {}
        for r in records:
            totals[r.student_id] = totals.get(r.student_id, Decimal("0")) + Decimal(r.amount_cny)

        self.per_student_table.setRowCount(len(totals))
        self.per_student_table.setColumnCount(2)
        self.per_student_table.setHorizontalHeaderLabels([
            self.translator.t("field.student_id"),
            self.translator.t("reports.per_student"),
        ])
        for row, (sid, total) in enumerate(totals.items()):
            self.per_student_table.setItem(row, 0, QTableWidgetItem(sid))
            self.per_student_table.setItem(row, 1, QTableWidgetItem(str(total)))

        self.records_table.setRowCount(len(records))
        headers = [
            self.translator.t("export.header.run_id"),
            self.translator.t("export.header.settlement_month"),
            self.translator.t("export.header.student_id"),
            self.translator.t("export.header.allowance_type"),
            self.translator.t("export.header.period_start"),
            self.translator.t("export.header.period_end"),
            self.translator.t("export.header.amount_usd"),
            self.translator.t("export.header.fx_rate"),
            self.translator.t("export.header.amount_cny"),
            self.translator.t("export.header.rule_id"),
        ]
        self.records_table.setColumnCount(len(headers))
        self.records_table.setHorizontalHeaderLabels(headers)
        for row, r in enumerate(records):
            values = [
                str(r.run_id),
                r.settlement_month,
                r.student_id,
                self._allowance_label(r.allowance_type),
                r.period_start,
                r.period_end,
                r.amount_usd,
                r.fx_rate,
                r.amount_cny,
                r.rule_id,
            ]
            for col, val in enumerate(values):
                self.records_table.setItem(row, col, QTableWidgetItem(val))

    def _run_settlement(self) -> None:
        settlement = self.settlement_month.date().toPython()
        settlement_str = settlement.strftime("%Y-%m")
        cfg_row = db.get_latest_config(self.conn)
        config = db.config_row_to_model(cfg_row)
        students = db.list_students(self.conn)

        baggage_ids = []
        withdrawal_ids = []
        for row in range(self.special_table.rowCount()):
            widget = self.special_table.cellWidget(row, 4)
            if isinstance(widget, QCheckBox) and widget.isChecked():
                sid = widget.property("student_id")
                typ = widget.property("special_type")
                if typ == "baggage":
                    baggage_ids.append(sid)
                elif typ == "withdrawal":
                    withdrawal_ids.append(sid)

        result = compute_monthly_settlement(
            students=students,
            settlement_month=settlement,
            config=config,
            baggage_pay_ids=baggage_ids,
            withdrawal_living_ids=withdrawal_ids,
        )

        run = db.create_run(self.conn, cfg_row.version, settlement_str, config.fx_rate_usd_to_cny)
        if result.records:
            db.save_records(self.conn, run.run_id, settlement_str, result.records, config.fx_rate_usd_to_cny)
            for r in result.records:
                if r.allowance_type == AllowanceType.BAGGAGE:
                    db.record_baggage_paid(self.conn, r.student_id, run.run_id, settlement_str)

        self.run_info.setText(
            f"{self.translator.t('dashboard.run_info')}: {self.translator.t('dashboard.run_id')}={run.run_id}, "
            f"{self.translator.t('dashboard.fx_rate')}={run.fx_rate}, {self.translator.t('dashboard.config_version')}={run.config_version}"
        )
        self._load_reports()
        self._load_special_panel()

    def _export_current(self, fmt: str) -> None:
        run = db.get_latest_run(self.conn)
        if not run:
            QMessageBox.warning(self, self.translator.t("reports.title"), self.translator.t("error.no_run"))
            return
        records = db.fetch_records_for_run(self.conn, run.run_id)
        path = export_records(records, self.translator, fmt)
        target, _ = QFileDialog.getSaveFileName(self, "", f"settlement_{run.settlement_month}.{fmt}")
        if target:
            shutil.copy(path, target)

    def _add_student(self) -> None:
        dialog = StudentDialog(self.translator)
        if dialog.exec():
            student = dialog.get_student()
            if student:
                db.upsert_student(self.conn, student)
                self._load_students()
                self._set_student_saved()

    def _edit_student(self) -> None:
        row = self.students_table.currentRow()
        if row < 0:
            return
        student_id = self.students_table.item(row, 0).text()
        student = db.get_student(self.conn, student_id)
        if not student:
            return
        dialog = StudentDialog(self.translator, student)
        if dialog.exec():
            updated = dialog.get_student()
            if updated:
                db.upsert_student(self.conn, updated)
                self._load_students()
                self._set_student_saved()

    def _delete_student(self) -> None:
        row = self.students_table.currentRow()
        if row < 0:
            return
        student_id = self.students_table.item(row, 0).text()
        if QMessageBox.question(self, "", self.translator.t("confirm.delete")) == QMessageBox.Yes:
            db.delete_student(self.conn, student_id)
            self._load_students()
            self._set_student_saved()

    def _set_student_saved(self) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.student_status.setText(
            f"{self.translator.t('students.saved')} - {self.translator.t('students.last_saved')}: {ts}"
        )

    def _import_students(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "", "", "CSV (*.csv)")
        if not path:
            return
        errors = []
        with open(path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            required = [
                "student_id",
                "name",
                "degree_level",
                "first_entry_date",
                "status",
                "graduation_date",
                "withdrawal_date",
            ]
            if not reader.fieldnames or any(c not in reader.fieldnames for c in required):
                QMessageBox.warning(self, "", self.translator.t("error.required"))
                return
            for idx, row in enumerate(reader, start=2):
                try:
                    student = _row_to_student(row)
                    db.upsert_student(self.conn, student)
                except Exception as exc:
                    msg = str(exc)
                    if msg == "invalid_date":
                        msg = self.translator.t("error.invalid_date")
                    errors.append(f"Row {idx}: {msg}")
        if errors:
            QMessageBox.warning(self, "", "\n".join(errors))
        self._load_students()

    def _export_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "", "students_template.csv")
        if not path:
            return
        headers = [
            "student_id",
            "name",
            "degree_level",
            "first_entry_date",
            "status",
            "graduation_date",
            "withdrawal_date",
        ]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)

    def _save_config(self) -> None:
        try:
            cfg = AllowanceConfig(
                living_allowance_by_degree={
                    DegreeLevel.BACHELOR: Decimal(self.living_bachelor.text()),
                    DegreeLevel.MASTER: Decimal(self.living_master.text()),
                    DegreeLevel.PHD: Decimal(self.living_phd.text()),
                },
                study_allowance_usd=Decimal(self.study_allowance.text()),
                baggage_allowance_usd=Decimal(self.baggage_allowance.text()),
                issue_study_if_exit_before_oct_entry_year=self.policy_switch.isChecked(),
                fx_rate_usd_to_cny=Decimal(self.fx_rate.text()),
                usd_quantize=Decimal("0.01"),
                cny_quantize=Decimal("0.01"),
                rounding_mode="ROUND_HALF_UP",
                rounding_policy="final_only",
            )
        except Exception:
            return
        db.save_config(self.conn, cfg, withdrawn_living_default=self.withdrawn_default.isChecked())
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.config_status.setText(f"{self.translator.t('config.saved')} - {ts}")

    def _backup(self) -> None:
        path = create_backup()
        self.backup_status.setText(str(path))

    def _restore_prompt(self) -> None:
        QMessageBox.information(self, "", self.translator.t("backup.pre_backup"))

    def _restore(self, mode: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "", "", "Backup (*.zip)")
        if not path:
            return
        if mode == "replace":
            if QMessageBox.question(self, "", self.translator.t("confirm.restore_replace")) != QMessageBox.Yes:
                return
        else:
            if QMessageBox.question(self, "", self.translator.t("confirm.restore")) != QMessageBox.Yes:
                return
        added, skipped = restore_backup(Path(path), mode)
        self.backup_status.setText(f"added={added}, skipped={skipped}")
        self._load_all()

    def _degree_label(self, degree: DegreeLevel) -> str:
        return self.translator.t(f"degree.{degree.name.lower()}")

    def _status_label(self, status: Status) -> str:
        if status == Status.IN_STUDY:
            return self.translator.t("status.in_study")
        if status == Status.GRADUATED:
            return self.translator.t("status.graduated")
        return self.translator.t("status.withdrawn")

    def _allowance_label(self, value: str) -> str:
        mapping = {
            "Living": "allowance.living",
            "Study": "allowance.study",
            "ExcessBaggage": "allowance.baggage",
        }
        key = mapping.get(value)
        return self.translator.t(key) if key else value


class StudentDialog(QDialog):
    def __init__(self, translator: Translator, student: Optional[db.StudentRow] = None) -> None:
        super().__init__()
        self.translator = translator
        self.student = student
        self.setWindowTitle(translator.t("students.edit") if student else translator.t("students.add"))

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        self.student_id = QLineEdit(student.student_id if student else "")
        self.name = QLineEdit(student.name if student else "")
        self.degree = QComboBox()
        for degree in DegreeLevel:
            self.degree.addItem(translator.t(f"degree.{degree.name.lower()}"), degree)
        if student:
            idx = list(DegreeLevel).index(student.degree_level)
            self.degree.setCurrentIndex(idx)
        self.entry_date = QDateEdit()
        self.entry_date.setDisplayFormat("yyyy-MM-dd")
        self.entry_date.setCalendarPopup(True)
        self.entry_date.lineEdit().setReadOnly(True)
        if student:
            self.entry_date.setDate(student.first_entry_date)
        else:
            self.entry_date.setDate(date.today())
        self.status = QComboBox()
        self.status.addItem(translator.t("status.in_study"), Status.IN_STUDY)
        self.status.addItem(translator.t("status.graduated"), Status.GRADUATED)
        self.status.addItem(translator.t("status.withdrawn"), Status.WITHDRAWN)
        if student:
            idx = {Status.IN_STUDY: 0, Status.GRADUATED: 1, Status.WITHDRAWN: 2}[student.status]
            self.status.setCurrentIndex(idx)
        self.graduation_date = QDateEdit()
        self.graduation_date.setDisplayFormat("yyyy-MM-dd")
        self.graduation_date.setCalendarPopup(True)
        self.graduation_date.lineEdit().setReadOnly(True)
        self.graduation_empty = QCheckBox(translator.t("field.empty_none"))

        self.withdrawal_date = QDateEdit()
        self.withdrawal_date.setDisplayFormat("yyyy-MM-dd")
        self.withdrawal_date.setCalendarPopup(True)
        self.withdrawal_date.lineEdit().setReadOnly(True)
        self.withdrawal_empty = QCheckBox(translator.t("field.empty_none"))

        if student and student.graduation_date:
            self.graduation_date.setDate(student.graduation_date)
            self.graduation_empty.setChecked(False)
        else:
            self.graduation_date.setDate(date.today())
            self.graduation_empty.setChecked(True)

        if student and student.withdrawal_date:
            self.withdrawal_date.setDate(student.withdrawal_date)
            self.withdrawal_empty.setChecked(False)
        else:
            self.withdrawal_date.setDate(date.today())
            self.withdrawal_empty.setChecked(True)

        form_layout.addRow(translator.t("field.student_id"), self.student_id)
        form_layout.addRow(translator.t("field.name"), self.name)
        form_layout.addRow(translator.t("field.degree"), self.degree)
        form_layout.addRow(translator.t("field.entry_date"), self.entry_date)
        form_layout.addRow(translator.t("field.status"), self.status)
        grad_row = QHBoxLayout()
        grad_row.addWidget(self.graduation_date)
        grad_row.addWidget(self.graduation_empty)
        grad_widget = QWidget()
        grad_widget.setLayout(grad_row)
        form_layout.addRow(translator.t("field.graduation_date"), grad_widget)
        form_layout.addRow("", QLabel(translator.t("hint.graduation")))
        wd_row = QHBoxLayout()
        wd_row.addWidget(self.withdrawal_date)
        wd_row.addWidget(self.withdrawal_empty)
        wd_widget = QWidget()
        wd_widget.setLayout(wd_row)
        form_layout.addRow(translator.t("field.withdrawal_date"), wd_widget)
        form_layout.addRow("", QLabel(translator.t("hint.withdrawal")))

        self.status.currentIndexChanged.connect(self._toggle_date_fields)
        self.graduation_empty.stateChanged.connect(self._toggle_date_fields)
        self.withdrawal_empty.stateChanged.connect(self._toggle_date_fields)
        self._toggle_date_fields()

        layout = QVBoxLayout()
        layout.addWidget(form_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_student(self) -> Optional[db.StudentRow]:
        try:
            student_id = self.student_id.text().strip()
            name = self.name.text().strip()
            if not student_id or not name:
                raise ValueError(self.translator.t("error.required"))
            entry_date = self.entry_date.date().toPython()
            status = self.status.currentData()
            graduation_date = None if self.graduation_empty.isChecked() else self.graduation_date.date().toPython()
            withdrawal_date = None if self.withdrawal_empty.isChecked() else self.withdrawal_date.date().toPython()
            if status == Status.GRADUATED and graduation_date is None:
                raise ValueError(self.translator.t("error.graduation_required"))
            if status == Status.WITHDRAWN and withdrawal_date is None:
                raise ValueError(self.translator.t("error.withdrawal_required"))
            if graduation_date and graduation_date < entry_date:
                raise ValueError(self.translator.t("error.entry_before_graduation"))
            if withdrawal_date and withdrawal_date < entry_date:
                raise ValueError(self.translator.t("error.entry_before_withdrawal"))
            if status == Status.IN_STUDY:
                graduation_date = None
            if status != Status.WITHDRAWN:
                withdrawal_date = None

            return db.StudentRow(
                student_id=student_id,
                name=name,
                degree_level=self.degree.currentData(),
                first_entry_date=entry_date,
                status=status,
                graduation_date=graduation_date,
                withdrawal_date=withdrawal_date,
            )
        except Exception as exc:
            QMessageBox.warning(self, "", str(exc))
            return None

    def _toggle_date_fields(self) -> None:
        status = self.status.currentData()
        is_graduated = status == Status.GRADUATED
        is_withdrawn = status == Status.WITHDRAWN

        if not is_graduated:
            self.graduation_empty.setChecked(True)
        self.graduation_empty.setEnabled(is_graduated)
        self.graduation_date.setEnabled(is_graduated and not self.graduation_empty.isChecked())

        if not is_withdrawn:
            self.withdrawal_empty.setChecked(True)
        self.withdrawal_empty.setEnabled(is_withdrawn)
        self.withdrawal_date.setEnabled(is_withdrawn and not self.withdrawal_empty.isChecked())


def _row_to_student(row: Dict[str, str]) -> db.StudentRow:
    status = Status(row["status"].strip())
    entry_date = parse_date(row["first_entry_date"])
    graduation_date = parse_date(row.get("graduation_date", ""))
    withdrawal_date = parse_date(row.get("withdrawal_date", ""))
    if status == Status.GRADUATED and graduation_date is None:
        raise ValueError("graduation_date required")
    if status == Status.WITHDRAWN and withdrawal_date is None:
        raise ValueError("withdrawal_date required")
    if graduation_date and entry_date and graduation_date < entry_date:
        raise ValueError("graduation_date before entry_date")
    if withdrawal_date and entry_date and withdrawal_date < entry_date:
        raise ValueError("withdrawal_date before entry_date")

    return db.StudentRow(
        student_id=row["student_id"].strip(),
        name=row["name"].strip(),
        degree_level=DegreeLevel(row["degree_level"].strip()),
        first_entry_date=entry_date,
        status=status,
        graduation_date=graduation_date if status != Status.IN_STUDY else None,
        withdrawal_date=withdrawal_date if status == Status.WITHDRAWN else None,
    )


def run() -> None:
    app = QApplication([])
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    app.exec()


if __name__ == "__main__":
    run()
