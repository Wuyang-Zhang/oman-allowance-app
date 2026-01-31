from __future__ import annotations

import csv
import json
import os
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QStackedWidget,
    QSpinBox,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QScrollArea,
    QSizePolicy,
)
from PySide6.QtGui import QBrush, QColor, QCursor
from PySide6.QtWidgets import QHeaderView
from PySide6.QtWidgets import QStyledItemDelegate

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


def configure_date_edit(widget: QDateEdit, display_format: str) -> None:
    widget.setDisplayFormat(display_format)
    widget.setCalendarPopup(True)
    widget.setKeyboardTracking(False)
    widget.setFocusPolicy(Qt.StrongFocus)
    widget.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
    widget.setCursor(Qt.IBeamCursor)
    today = date.today()
    min_date = QDate(today.year - 20, 1, 1)
    max_date = QDate(today.year + 50, 12, 31)
    widget.setMinimumDate(min_date)
    widget.setMaximumDate(max_date)
    calendar = widget.calendarWidget()
    if calendar:
        calendar.setDateRange(min_date, max_date)
        calendar.setNavigationBarVisible(True)
        calendar.setGridVisible(True)
        _install_calendar_year_dropdown(calendar, min_date, max_date)
    line = widget.lineEdit()
    if line:
        line.setReadOnly(False)
        line.setFocusPolicy(Qt.StrongFocus)


def _install_calendar_year_dropdown(calendar: QWidget, min_date: QDate, max_date: QDate) -> None:
    nav = calendar.findChild(QWidget, "qt_calendar_navigationbar")
    year_edit = calendar.findChild(QSpinBox, "qt_calendar_yearedit")
    year_button = calendar.findChild(QToolButton, "qt_calendar_yearbutton")
    if not nav or not year_edit:
        return
    if nav.findChild(QComboBox, "oma_year_combo"):
        return

    combo = QComboBox(nav)
    combo.setObjectName("oma_year_combo")
    combo.setFont(year_edit.font())
    for year in range(min_date.year(), max_date.year() + 1):
        combo.addItem(str(year), year)

    layout = nav.layout()
    year_edit.setEnabled(False)
    year_edit.setVisible(False)
    year_edit.setMaximumWidth(0)
    year_edit.setMaximumHeight(0)
    year_edit.setStyleSheet("QSpinBox{border:0;padding:0;margin:0;min-width:0;max-width:0;min-height:0;max-height:0;}")
    if layout:
        index = layout.indexOf(year_edit)
        if index >= 0:
            layout.removeWidget(year_edit)
            layout.insertWidget(index, combo, 1, Qt.AlignCenter)
        else:
            mid = max(0, layout.count() // 2)
            layout.insertWidget(mid, combo, 1, Qt.AlignCenter)
        layout.setAlignment(combo, Qt.AlignCenter)
    else:
        combo.setParent(calendar)

    hidden = calendar.findChild(QWidget, "oma_hidden_year_container")
    if hidden is None:
        hidden = QWidget(calendar)
        hidden.setObjectName("oma_hidden_year_container")
        hidden.hide()
    year_edit.setParent(hidden)
    if year_button:
        year_button.setEnabled(False)
        year_button.setVisible(False)
        if layout:
            layout.removeWidget(year_button)
        year_button.setParent(hidden)

    def sync_from_calendar(year: int, month: int) -> None:
        idx = combo.findData(year)
        if idx >= 0 and combo.currentIndex() != idx:
            combo.blockSignals(True)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def on_combo_changed(_: int) -> None:
        year_value = combo.currentData()
        if isinstance(year_value, int):
            calendar.setCurrentPage(year_value, calendar.monthShown())

    combo.currentIndexChanged.connect(on_combo_changed)
    calendar.currentPageChanged.connect(sync_from_calendar)
    sync_from_calendar(calendar.yearShown(), calendar.monthShown())


class DateDebugFilter(QObject):
    def __init__(self, name: str, enabled: bool) -> None:
        super().__init__()
        self.name = name
        self.enabled = enabled

    def eventFilter(self, obj, event) -> bool:
        if not self.enabled:
            return False
        if event.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.FocusIn):
            widget_at = QApplication.widgetAt(QCursor.pos())
            widget_name = widget_at.__class__.__name__ if widget_at else "None"
            print(
                f"[DATE_DEBUG] {self.name} event={event.type()} widget_at={widget_name}"
            )
        return False


class ColumnStripeDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter
        if index.column() % 2 == 0:
            option.backgroundBrush = QBrush(QColor("#f5f7fb"))
        else:
            option.backgroundBrush = QBrush(QColor("#eef2f7"))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        # Set OMA_GUI_DEBUG=1 to trace date widget state/events on Windows.
        self.debug_ui = os.environ.get("OMA_GUI_DEBUG", "").lower() in {"1", "true", "yes"}
        self.translator = Translator(Path(__file__).resolve().parents[1] / "i18n")
        self.translator.set_language(self.settings.get("language", "zh_CN"))

        self.conn = db.connect()
        db.init_db(self.conn)
        self.latest_run = None

        self.setWindowTitle(self.translator.t("app.title"))
        self._build_ui()
        self.setMinimumSize(1100, 720)
        self._load_all()

    def closeEvent(self, event) -> None:
        self.conn.close()
        event.accept()

    def _build_ui(self) -> None:
        self.table_states: Dict[str, Dict[str, QWidget]] = {}
        self.page_index: Dict[str, int] = {}
        self.page_order: List[str] = []

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_appbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(200)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        body.addWidget(self.nav)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)

        root.addLayout(body)
        self.setCentralWidget(central)

        self._build_pages()
        self._retranslate()

    def _build_appbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("appbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(12)

        self.app_title = QLabel()
        self.app_title.setProperty("role", "appbar-title")
        self.app_meta = QLabel()
        self.app_meta.setProperty("role", "appbar-meta")
        self.app_status = QLabel()
        self.app_status.setProperty("role", "appbar-meta")

        layout.addWidget(self.app_title)
        layout.addWidget(self.app_meta)
        layout.addWidget(self.app_status)
        layout.addStretch()

        self.export_csv_btn_global = QPushButton()
        self.export_xlsx_btn_global = QPushButton()
        self.help_btn = QPushButton()
        self.export_csv_btn_global.setProperty("variant", "secondary")
        self.export_xlsx_btn_global.setProperty("variant", "secondary")
        self.help_btn.setProperty("variant", "secondary")
        self.export_csv_btn_global.clicked.connect(lambda: self._export_current("csv"))
        self.export_xlsx_btn_global.clicked.connect(lambda: self._export_current("xlsx"))
        self.help_btn.clicked.connect(self._show_about)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(self.translator.t("lang.zh"), "zh_CN")
        self.lang_combo.addItem(self.translator.t("lang.en"), "en_US")
        current = self.translator.lang
        index = 0 if current == "zh_CN" else 1
        self.lang_combo.setCurrentIndex(index)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)

        layout.addWidget(self.export_csv_btn_global)
        layout.addWidget(self.export_xlsx_btn_global)
        layout.addWidget(self.help_btn)
        layout.addWidget(self.lang_combo)
        return bar

    def _build_pages(self) -> None:
        pages = [
            ("dashboard", self._build_dashboard),
            ("students", self._build_students),
            ("config", self._build_config),
            ("reports", self._build_reports),
            ("backup", self._build_backup),
            ("about", self._build_about),
        ]
        for key, builder in pages:
            widget = builder()
            self._add_page(widget, key)
            self.nav.addItem(QListWidgetItem(""))
            self.page_order.append(key)
        self.nav.setCurrentRow(0)

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        self.pages.setCurrentIndex(row)

    def _show_about(self) -> None:
        if "about" in self.page_index:
            self.nav.setCurrentRow(self.page_index["about"])

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
        labels = {
            "dashboard": self.translator.t("tab.dashboard"),
            "students": self.translator.t("tab.students"),
            "config": self.translator.t("tab.config"),
            "reports": self.translator.t("tab.reports"),
            "backup": self.translator.t("tab.backup"),
            "about": self.translator.t("tab.about"),
        }
        for idx, key in enumerate(self.page_order):
            if idx < self.nav.count():
                item = self.nav.item(idx)
                if item:
                    item.setText(labels.get(key, key))
        self._refresh_texts()

    def _refresh_texts(self) -> None:
        self.app_title.setText(self.translator.t("app.title"))
        self.export_csv_btn_global.setText(self.translator.t("reports.export_csv"))
        self.export_xlsx_btn_global.setText(self.translator.t("reports.export_xlsx"))
        self.help_btn.setText(self.translator.t("appbar.help"))

        self.dashboard_title.setText(self.translator.t("tab.dashboard"))
        self.dashboard_subtitle.setText(self.translator.t("page.dashboard.desc"))
        self.dashboard_subtitle.setVisible(True)
        self.dashboard_month_label.setText(self.translator.t("dashboard.settlement_month"))
        self.run_button.setText(self.translator.t("dashboard.run"))
        self.jump_current_btn.setText(self.translator.t("dashboard.jump_current"))
        self.special_title.setText(self.translator.t("special.title"))
        self.special_hint.setText(self.translator.t("special.hint"))
        self.students_title.setText(self.translator.t("students.title"))
        self.students_subtitle.setText(self.translator.t("page.students.desc"))
        self.students_subtitle.setVisible(True)
        self.student_add_btn.setText(self.translator.t("students.add"))
        self.student_edit_btn.setText(self.translator.t("students.edit"))
        self.student_delete_btn.setText(self.translator.t("students.delete"))
        self.student_import_btn.setText(self.translator.t("students.import"))
        self.student_template_btn.setText(self.translator.t("students.template"))
        self.config_title.setText(self.translator.t("config.title"))
        self.config_subtitle.setText(self.translator.t("page.config.desc"))
        self.config_subtitle.setVisible(True)
        self.config_save_btn.setText(self.translator.t("config.save"))
        self.config_section_titles["standard"].setText(self.translator.t("config.section.standard"))
        self.config_section_titles["usd"].setText(self.translator.t("config.section.usd"))
        self.config_section_titles["policy"].setText(self.translator.t("config.section.policy"))
        self.reports_title.setText(self.translator.t("reports.title"))
        self.reports_subtitle.setText(self.translator.t("page.reports.desc"))
        self.reports_subtitle.setVisible(True)
        self.per_student_title.setText(self.translator.t("reports.per_student"))
        self.records_title.setText(self.translator.t("reports.records"))
        self.backup_title.setText(self.translator.t("backup.title"))
        self.backup_subtitle.setText(self.translator.t("page.backup.desc"))
        self.backup_subtitle.setVisible(True)
        self.backup_create_btn.setText(self.translator.t("backup.create"))
        self.backup_restore_btn.setText(self.translator.t("backup.restore"))
        self.backup_replace_btn.setText(self.translator.t("backup.restore_replace"))
        self.backup_merge_btn.setText(self.translator.t("backup.restore_merge"))
        self.backup_info.setText(self.translator.t("backup.pre_backup"))
        self.about_title.setText(self.translator.t("about.title"))
        self.about_subtitle.setText(self.translator.t("page.about.desc"))
        self.about_subtitle.setVisible(True)
        self.about_version.setText(f"{self.translator.t('about.version')}: 1.0.0")
        self._refresh_table_state_texts()
        self._refresh_appbar()
        self._refresh_tables()

    def _refresh_table_state_texts(self) -> None:
        if "students" in self.table_states:
            info = self.table_states["students"]
            info["empty_title"].setText(self.translator.t("empty.students.title"))
            info["empty_hint"].setText(self.translator.t("empty.students.hint"))
            if info.get("empty_action"):
                info["empty_action"].setText(self.translator.t("empty.students.action"))
        if "special" in self.table_states:
            info = self.table_states["special"]
            info["empty_title"].setText(self.translator.t("empty.special.title"))
            info["empty_hint"].setText(self.translator.t("empty.special.hint"))
        for key in ("per_student", "records"):
            if key in self.table_states:
                info = self.table_states[key]
                info["empty_title"].setText(self.translator.t("empty.reports.title"))
                info["empty_hint"].setText(self.translator.t("empty.reports.hint"))
                if info.get("empty_action"):
                    info["empty_action"].setText(self.translator.t("empty.reports.action"))
        for info in self.table_states.values():
            info["loading_title"].setText(self.translator.t("loading.title"))
            info["loading_hint"].setText(self.translator.t("loading.hint"))

    def _refresh_appbar(self) -> None:
        month = self.settlement_month.date().toPython()
        self.app_meta.setText(f"{self.translator.t('appbar.month')}: {month:%Y-%m}")
        if getattr(self, "latest_run", None):
            self.app_status.setText(
                f"{self.translator.t('appbar.last_run')}: {self.latest_run.settlement_month}"
            )
        else:
            self.app_status.setText(self.translator.t("appbar.no_run"))

    def _build_dashboard(self) -> QWidget:
        page, title, subtitle, toolbar, content, footer = self._create_page_shell()
        self.dashboard_title = title
        self.dashboard_subtitle = subtitle

        self.dashboard_month_label = QLabel()
        self.dashboard_month_label.setProperty("role", "toolbar-label")
        self.settlement_month = QDateEdit()
        self.settlement_month.setMinimumWidth(160)
        configure_date_edit(self.settlement_month, "yyyy-MM")
        saved_month = self.settings.get("settlement_month")
        if saved_month:
            try:
                parts = saved_month.split("-")
                self.settlement_month.setDate(date(int(parts[0]), int(parts[1]), 1))
            except Exception:
                self.settlement_month.setDate(date.today().replace(day=1))
        else:
            self.settlement_month.setDate(date.today().replace(day=1))
        self.settlement_month.dateChanged.connect(self._on_settlement_month_changed)
        self.jump_current_btn = QPushButton()
        self.jump_current_btn.setProperty("variant", "secondary")
        self.jump_current_btn.clicked.connect(self._jump_current_month)
        self._install_date_debug(self.settlement_month, "settlement_month")
        self.run_button = QPushButton()
        self.run_button.setProperty("variant", "primary")
        self.run_button.clicked.connect(self._run_settlement)

        toolbar.addWidget(self.dashboard_month_label)
        toolbar.addWidget(self.settlement_month)
        toolbar.addWidget(self.jump_current_btn)
        toolbar.addWidget(self.run_button)
        toolbar.addStretch()

        self.special_title = QLabel()
        self.special_hint = QLabel()
        self.special_title.setProperty("role", "section")
        self.special_hint.setProperty("role", "hint")
        special_card, special_layout = self._create_card(self.special_title, self.special_hint)
        self.special_table = QTableWidget(0, 5)
        self._configure_table(self.special_table)
        special_stack = self._wrap_table_with_state(
            "special",
            self.special_table,
            self.translator.t("empty.special.title"),
            self.translator.t("empty.special.hint"),
        )
        special_layout.addWidget(special_stack)
        content.addWidget(special_card)

        self.run_info = QLabel("")
        self.run_info.setProperty("role", "hint")
        footer.addWidget(self.run_info)

        return page

    def _build_students(self) -> QWidget:
        page, title, subtitle, toolbar, content, footer = self._create_page_shell()
        self.students_title = title
        self.students_subtitle = subtitle

        self.student_add_btn = QPushButton()
        self.student_edit_btn = QPushButton()
        self.student_delete_btn = QPushButton()
        self.student_import_btn = QPushButton()
        self.student_template_btn = QPushButton()
        self.student_add_btn.setProperty("variant", "primary")
        self.student_edit_btn.setProperty("variant", "secondary")
        self.student_delete_btn.setProperty("variant", "danger")
        self.student_import_btn.setProperty("variant", "secondary")
        self.student_template_btn.setProperty("variant", "secondary")
        self.student_add_btn.clicked.connect(self._add_student)
        self.student_edit_btn.clicked.connect(self._edit_student)
        self.student_delete_btn.clicked.connect(self._delete_student)
        self.student_import_btn.clicked.connect(self._import_students)
        self.student_template_btn.clicked.connect(self._export_template)
        toolbar.addWidget(self.student_add_btn)
        toolbar.addWidget(self.student_edit_btn)
        toolbar.addWidget(self.student_delete_btn)
        toolbar.addWidget(self.student_import_btn)
        toolbar.addWidget(self.student_template_btn)
        toolbar.addStretch()

        self.students_table = QTableWidget(0, 7)
        self._configure_table(self.students_table)
        students_card, students_layout = self._create_card()
        students_stack = self._wrap_table_with_state(
            "students",
            self.students_table,
            self.translator.t("empty.students.title"),
            self.translator.t("empty.students.hint"),
            self.translator.t("empty.students.action"),
            self._import_students,
        )
        students_layout.addWidget(students_stack)
        content.addWidget(students_card)

        self.student_status = QLabel("")
        self.student_status.setProperty("role", "hint")
        footer.addWidget(self.student_status)

        return page

    def _build_config(self) -> QWidget:
        page, title, subtitle, toolbar, content, footer = self._create_page_shell()
        self.config_title = title
        self.config_subtitle = subtitle

        self.config_save_btn = QPushButton()
        self.config_save_btn.setProperty("variant", "primary")
        self.config_save_btn.clicked.connect(self._save_config)
        toolbar.addStretch()
        toolbar.addWidget(self.config_save_btn)

        self.living_bachelor = QLineEdit()
        self.living_master = QLineEdit()
        self.living_phd = QLineEdit()
        self.study_allowance = QLineEdit()
        self.study_allowance_month = QComboBox()
        for month in range(1, 13):
            self.study_allowance_month.addItem(f"{month:02d}", month)
        self.baggage_allowance = QLineEdit()
        self.fx_rate = QLineEdit()
        self.policy_switch = QCheckBox()
        self.entry_month_switch = QCheckBox()
        self.withdrawn_default = QCheckBox()

        standard_title = QLabel()
        standard_title.setProperty("role", "section")
        standard_card, standard_layout = self._create_card(standard_title)
        standard_form = QFormLayout()
        standard_form.setHorizontalSpacing(18)
        standard_form.setVerticalSpacing(12)
        standard_form.addRow(
            self.translator.t("degree.bachelor"),
            self._field_with_unit(
                self.living_bachelor,
                self.translator.t("unit.usd_per_month"),
                self.translator.t("config.hint.living"),
            ),
        )
        standard_form.addRow(
            self.translator.t("degree.master"),
            self._field_with_unit(
                self.living_master,
                self.translator.t("unit.usd_per_month"),
                self.translator.t("config.hint.living"),
            ),
        )
        standard_form.addRow(
            self.translator.t("degree.phd"),
            self._field_with_unit(
                self.living_phd,
                self.translator.t("unit.usd_per_month"),
                self.translator.t("config.hint.living"),
            ),
        )
        standard_layout.addLayout(standard_form)
        content.addWidget(standard_card)

        usd_title = QLabel()
        usd_title.setProperty("role", "section")
        usd_card, usd_layout = self._create_card(usd_title)
        usd_form = QFormLayout()
        usd_form.setHorizontalSpacing(18)
        usd_form.setVerticalSpacing(12)
        usd_form.addRow(
            self.translator.t("config.study"),
            self._field_with_unit(
                self.study_allowance,
                self.translator.t("unit.usd"),
                self.translator.t("config.hint.study"),
            ),
        )
        usd_form.addRow(
            self.translator.t("config.study_month"),
            self._field_with_hint(
                self.study_allowance_month,
                self.translator.t("config.hint.study_month"),
            ),
        )
        usd_form.addRow(
            self.translator.t("config.baggage"),
            self._field_with_unit(
                self.baggage_allowance,
                self.translator.t("unit.usd"),
                self.translator.t("config.hint.baggage"),
            ),
        )
        usd_form.addRow(
            self.translator.t("config.fx_rate"),
            self._field_with_unit(
                self.fx_rate,
                self.translator.t("unit.fx_rate"),
                self.translator.t("config.hint.fx_rate"),
            ),
        )
        usd_layout.addLayout(usd_form)
        content.addWidget(usd_card)

        policy_title = QLabel()
        policy_title.setProperty("role", "section")
        policy_card, policy_layout = self._create_card(policy_title)
        policy_form = QFormLayout()
        policy_form.setHorizontalSpacing(18)
        policy_form.setVerticalSpacing(12)
        policy_form.addRow(
            self.translator.t("config.policy"),
            self._field_with_hint(self.policy_switch, self.translator.t("config.hint.policy")),
        )
        policy_form.addRow(
            self.translator.t("config.issue_entry_month"),
            self._field_with_hint(self.entry_month_switch, self.translator.t("config.hint.entry_month")),
        )
        policy_form.addRow(
            self.translator.t("config.withdrawn_default"),
            self._field_with_hint(
                self.withdrawn_default, self.translator.t("config.hint.withdrawn")
            ),
        )
        policy_layout.addLayout(policy_form)
        content.addWidget(policy_card)

        for field in [
            self.living_bachelor,
            self.living_master,
            self.living_phd,
            self.study_allowance,
            self.baggage_allowance,
            self.fx_rate,
        ]:
            field.editingFinished.connect(self._save_config)
        self.study_allowance_month.currentIndexChanged.connect(self._save_config)
        self.policy_switch.stateChanged.connect(self._save_config)
        self.entry_month_switch.stateChanged.connect(self._save_config)
        self.withdrawn_default.stateChanged.connect(self._save_config)

        self.config_status = QLabel("")
        self.config_status.setProperty("role", "hint")
        footer.addWidget(self.config_status)

        self.config_section_titles = {
            "standard": standard_title,
            "usd": usd_title,
            "policy": policy_title,
        }

        return page

    def _build_reports(self) -> QWidget:
        page, title, subtitle, toolbar, content, footer = self._create_page_shell()
        self.reports_title = title
        self.reports_subtitle = subtitle
        toolbar.addStretch()

        self.per_student_title = QLabel()
        self.per_student_title.setProperty("role", "section")
        per_student_card, per_student_layout = self._create_card(self.per_student_title)
        self.per_student_table = QTableWidget(0, 2)
        self._configure_table(self.per_student_table)
        per_student_stack = self._wrap_table_with_state(
            "per_student",
            self.per_student_table,
            self.translator.t("empty.reports.title"),
            self.translator.t("empty.reports.hint"),
            self.translator.t("empty.reports.action"),
            self._run_settlement,
        )
        per_student_layout.addWidget(per_student_stack)
        content.addWidget(per_student_card)

        self.records_title = QLabel()
        self.records_title.setProperty("role", "section")
        records_card, records_layout = self._create_card(self.records_title)
        self.records_table = QTableWidget(0, 10)
        self._configure_table(self.records_table)
        records_stack = self._wrap_table_with_state(
            "records",
            self.records_table,
            self.translator.t("empty.reports.title"),
            self.translator.t("empty.reports.hint"),
            self.translator.t("empty.reports.action"),
            self._run_settlement,
        )
        records_layout.addWidget(records_stack)
        content.addWidget(records_card)

        return page

    def _build_backup(self) -> QWidget:
        page, title, subtitle, toolbar, content, footer = self._create_page_shell()
        self.backup_title = title
        self.backup_subtitle = subtitle

        self.backup_create_btn = QPushButton()
        self.backup_restore_btn = QPushButton()
        self.backup_replace_btn = QPushButton()
        self.backup_merge_btn = QPushButton()
        self.backup_create_btn.setProperty("variant", "primary")
        self.backup_restore_btn.setProperty("variant", "secondary")
        self.backup_replace_btn.setProperty("variant", "danger")
        self.backup_merge_btn.setProperty("variant", "secondary")
        self.backup_create_btn.clicked.connect(self._backup)
        self.backup_restore_btn.clicked.connect(self._restore_prompt)
        self.backup_replace_btn.clicked.connect(lambda: self._restore("replace"))
        self.backup_merge_btn.clicked.connect(lambda: self._restore("merge"))

        toolbar.addWidget(self.backup_create_btn)
        toolbar.addWidget(self.backup_restore_btn)
        toolbar.addWidget(self.backup_replace_btn)
        toolbar.addWidget(self.backup_merge_btn)
        toolbar.addStretch()

        backup_card, backup_layout = self._create_card()
        self.backup_info = QLabel()
        self.backup_info.setProperty("role", "hint")
        self.backup_info.setWordWrap(True)
        backup_layout.addWidget(self.backup_info)
        content.addWidget(backup_card)

        self.backup_status = QLabel("")
        self.backup_status.setProperty("role", "hint")
        footer.addWidget(self.backup_status)

        return page

    def _build_about(self) -> QWidget:
        page, title, subtitle, toolbar, content, footer = self._create_page_shell()
        self.about_title = title
        self.about_subtitle = subtitle

        about_card, about_layout = self._create_card()
        self.about_version = QLabel()
        self.about_version.setProperty("role", "hint")
        about_layout.addWidget(self.about_version)
        content.addWidget(about_card)

        return page

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
        self._set_table_state("students", "loading")
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
        if students:
            self._set_table_state("students", "normal")
        else:
            self._set_table_state("students", "empty")

    def _load_config(self) -> None:
        cfg = db.get_latest_config(self.conn)
        self.living_bachelor.setText(cfg.living_allowance_bachelor)
        self.living_master.setText(cfg.living_allowance_master)
        self.living_phd.setText(cfg.living_allowance_phd)
        self.study_allowance.setText(cfg.study_allowance_usd)
        month_value = getattr(cfg, "study_allowance_month", 10) or 10
        month_index = self.study_allowance_month.findData(int(month_value))
        if month_index >= 0:
            self.study_allowance_month.setCurrentIndex(month_index)
        self.baggage_allowance.setText(cfg.baggage_allowance_usd)
        self.fx_rate.setText(cfg.fx_rate_usd_to_cny)
        self.policy_switch.setChecked(bool(cfg.issue_study_if_exit_before_oct_entry_year))
        self.entry_month_switch.setChecked(bool(getattr(cfg, "issue_study_if_entry_month", 0)))
        self.withdrawn_default.setChecked(bool(cfg.withdrawn_living_default))

    def _load_special_panel(self) -> None:
        self._set_table_state("special", "loading")
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
        if eligible:
            self._set_table_state("special", "normal")
        else:
            self._set_table_state("special", "empty")

    def _load_reports(self) -> None:
        self._set_table_state("per_student", "loading")
        self._set_table_state("records", "loading")
        run = db.get_latest_run(self.conn)
        self.latest_run = run
        if not run:
            self.per_student_table.setRowCount(0)
            self.records_table.setRowCount(0)
            self._set_table_state("per_student", "empty")
            self._set_table_state("records", "empty")
            self._refresh_appbar()
            return
        records = db.fetch_records_for_run(self.conn, run.run_id)
        students = db.list_students(self.conn)
        student_map = {s.student_id: s for s in students}
        totals: Dict[str, Decimal] = {}
        for r in records:
            totals[r.student_id] = totals.get(r.student_id, Decimal("0")) + Decimal(r.amount_cny)

        self.per_student_table.setRowCount(len(totals))
        self.per_student_table.setColumnCount(4)
        self.per_student_table.setHorizontalHeaderLabels([
            self.translator.t("field.student_id"),
            self.translator.t("field.name"),
            self.translator.t("field.entry_date"),
            self.translator.t("reports.per_student"),
        ])
        for row, (sid, total) in enumerate(totals.items()):
            student = student_map.get(sid)
            self.per_student_table.setItem(row, 0, QTableWidgetItem(sid))
            self.per_student_table.setItem(row, 1, QTableWidgetItem(student.name if student else ""))
            self.per_student_table.setItem(
                row, 2, QTableWidgetItem(format_date(student.first_entry_date) if student else "")
            )
            self.per_student_table.setItem(row, 3, QTableWidgetItem(str(total)))
        if totals:
            self._set_table_state("per_student", "normal")
        else:
            self._set_table_state("per_student", "empty")

        self.records_table.setRowCount(len(records))
        headers = [
            self.translator.t("export.header.run_id"),
            self.translator.t("export.header.settlement_month"),
            self.translator.t("export.header.student_id"),
            self.translator.t("export.header.name"),
            self.translator.t("export.header.entry_date"),
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
            student = student_map.get(r.student_id)
            values = [
                str(r.run_id),
                r.settlement_month,
                r.student_id,
                student.name if student else "",
                format_date(student.first_entry_date) if student else "",
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
        if records:
            self._set_table_state("records", "normal")
        else:
            self._set_table_state("records", "empty")
        self._refresh_appbar()

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
        self.latest_run = run
        self._load_reports()
        self._load_special_panel()

    def _add_page(self, widget: QWidget, key: str) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(widget)
        index = self.pages.addWidget(scroll)
        self.page_index[key] = index

    def _configure_table(self, table: QTableWidget) -> None:
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignCenter)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setItemDelegate(ColumnStripeDelegate(table))

    def _apply_section_layout(self, layout: QVBoxLayout) -> None:
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

    def _create_page_shell(
        self,
    ) -> Tuple[QWidget, QLabel, QLabel, QHBoxLayout, QVBoxLayout, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._apply_section_layout(layout)

        title = QLabel()
        title.setProperty("role", "title")
        subtitle = QLabel()
        subtitle.setProperty("role", "hint")
        subtitle.setWordWrap(True)
        subtitle.setVisible(False)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        layout.addLayout(toolbar)

        content = QVBoxLayout()
        content.setSpacing(12)
        layout.addLayout(content)

        footer = QVBoxLayout()
        footer.setSpacing(6)
        layout.addLayout(footer)

        return page, title, subtitle, toolbar, content, footer

    def _create_card(
        self, title: Optional[QLabel] = None, hint: Optional[QLabel] = None
    ) -> Tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        if title:
            layout.addWidget(title)
        if hint:
            layout.addWidget(hint)
        return card, layout

    def _create_state_widget(
        self,
        title_text: str,
        hint_text: str,
        action_text: Optional[str] = None,
        action_callback=None,
    ) -> Tuple[QWidget, QLabel, QLabel, Optional[QPushButton]]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(title_text)
        title.setProperty("role", "empty-title")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel(hint_text)
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(hint)

        action_btn = None
        if action_text:
            action_btn = QPushButton(action_text)
            action_btn.setProperty("variant", "secondary")
            if action_callback:
                action_btn.clicked.connect(action_callback)
            layout.addWidget(action_btn, alignment=Qt.AlignCenter)
        return widget, title, hint, action_btn

    def _wrap_table_with_state(
        self,
        key: str,
        table: QTableWidget,
        empty_title: str,
        empty_hint: str,
        empty_action_text: Optional[str] = None,
        empty_action=None,
    ) -> QStackedWidget:
        stack = QStackedWidget()
        stack.addWidget(table)

        empty_widget, empty_title_label, empty_hint_label, empty_action_btn = self._create_state_widget(
            empty_title, empty_hint, empty_action_text, empty_action
        )
        stack.addWidget(empty_widget)

        loading_widget, loading_title_label, loading_hint_label, _ = self._create_state_widget(
            self.translator.t("loading.title"), self.translator.t("loading.hint")
        )
        stack.addWidget(loading_widget)

        self.table_states[key] = {
            "stack": stack,
            "table": table,
            "empty_title": empty_title_label,
            "empty_hint": empty_hint_label,
            "empty_action": empty_action_btn,
            "loading_title": loading_title_label,
            "loading_hint": loading_hint_label,
        }
        return stack

    def _set_table_state(self, key: str, state: str) -> None:
        info = self.table_states.get(key)
        if not info:
            return
        mapping = {"normal": 0, "empty": 1, "loading": 2}
        info["stack"].setCurrentIndex(mapping.get(state, 0))
        if state == "loading":
            QApplication.processEvents()

    def _field_with_unit(self, field: QWidget, unit: str, hint: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field, 1)
        unit_label = QLabel(unit)
        unit_label.setProperty("role", "unit")
        row.addWidget(unit_label)
        row.addStretch()
        layout.addLayout(row)
        hint_label = QLabel(hint)
        hint_label.setProperty("role", "hint")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        return widget

    def _field_with_hint(self, field: QWidget, hint: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(field)
        hint_label = QLabel(hint)
        hint_label.setProperty("role", "hint")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        return widget

    def _install_date_debug(self, widget: QDateEdit, name: str) -> None:
        if not self.debug_ui:
            return
        widget.installEventFilter(DateDebugFilter(name, True))
        self._log_date_widget(name, widget)

    def _log_date_widget(self, name: str, widget: QDateEdit) -> None:
        if not self.debug_ui:
            return
        line = widget.lineEdit()
        read_only = line.isReadOnly() if line else None
        parent_chain = []
        parent = widget.parent()
        while parent:
            parent_chain.append(parent.__class__.__name__)
            parent = parent.parent()
        print(
            "[DATE_DEBUG] "
            f"{name} enabled={widget.isEnabled()} visible={widget.isVisible()} "
            f"calendarPopup={widget.calendarPopup()} displayFormat={widget.displayFormat()} "
            f"keyboardTracking={widget.keyboardTracking()} lineReadOnly={read_only} "
            f"geometry={widget.geometry().getRect()} parents={parent_chain}"
        )

    def _on_settlement_month_changed(self) -> None:
        value = self.settlement_month.date().toPython()
        month = date(value.year, value.month, 1)
        if value.day != 1:
            self.settlement_month.blockSignals(True)
            self.settlement_month.setDate(month)
            self.settlement_month.blockSignals(False)
        self.settings["settlement_month"] = month.strftime("%Y-%m")
        save_settings(self.settings)
        self._load_special_panel()
        self._refresh_appbar()

    def _jump_current_month(self) -> None:
        today = date.today().replace(day=1)
        self.settlement_month.setDate(today)

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
        dialog = StudentDialog(self.translator, debug_ui=self.debug_ui)
        if dialog.exec():
            student = dialog.get_student()
            if student:
                existing = db.get_student(self.conn, student.student_id)
                if existing:
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Warning)
                    box.setWindowTitle(self.translator.t("students.duplicate_title"))
                    box.setText(self.translator.t("students.duplicate_title"))
                    box.setInformativeText(self.translator.t("students.duplicate_body"))
                    overwrite_btn = box.addButton(
                        self.translator.t("students.duplicate_overwrite"), QMessageBox.AcceptRole
                    )
                    edit_btn = box.addButton(
                        self.translator.t("students.duplicate_edit"), QMessageBox.ActionRole
                    )
                    cancel_btn = box.addButton(
                        self.translator.t("students.duplicate_cancel"), QMessageBox.RejectRole
                    )
                    box.setDefaultButton(edit_btn)
                    box.exec()
                    clicked = box.clickedButton()
                    if clicked == overwrite_btn:
                        db.upsert_student(self.conn, student)
                        self._load_students()
                        self._set_student_saved()
                    elif clicked == edit_btn:
                        self._edit_student_by_id(student.student_id)
                    return
                db.upsert_student(self.conn, student)
                self._load_students()
                self._set_student_saved()

    def _edit_student(self) -> None:
        row = self.students_table.currentRow()
        if row < 0:
            return
        student_id = self.students_table.item(row, 0).text()
        self._edit_student_by_id(student_id)

    def _edit_student_by_id(self, student_id: str) -> None:
        student = db.get_student(self.conn, student_id)
        if not student:
            return
        dialog = StudentDialog(self.translator, student, debug_ui=self.debug_ui)
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
            from ..schema import STUDENT_CSV_HEADERS
            if not reader.fieldnames:
                QMessageBox.warning(self, "", self.translator.t("error.csv_header_mismatch"))
                return
            fieldnames = list(reader.fieldnames)
            if fieldnames and fieldnames[0].startswith("\ufeff"):
                fieldnames[0] = fieldnames[0].lstrip("\ufeff")
            if fieldnames != STUDENT_CSV_HEADERS:
                expected = ", ".join(STUDENT_CSV_HEADERS)
                QMessageBox.warning(
                    self, "", self.translator.t("error.csv_header_mismatch", expected=expected)
                )
                return
            for idx, row in enumerate(reader, start=2):
                try:
                    if None in row and row[None]:
                        raise ValueError(self.translator.t("error.csv_header_mismatch"))
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
        from ..schema import STUDENT_CSV_HEADERS
        headers = STUDENT_CSV_HEADERS
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
                study_allowance_month=int(self.study_allowance_month.currentData()),
                issue_study_if_entry_month=self.entry_month_switch.isChecked(),
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
    def __init__(self, translator: Translator, student: Optional[db.StudentRow] = None, debug_ui: bool = False) -> None:
        super().__init__()
        self.translator = translator
        self.student = student
        self.debug_ui = debug_ui
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
        configure_date_edit(self.entry_date, "yyyy-MM-dd")
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
        configure_date_edit(self.graduation_date, "yyyy-MM-dd")
        self.graduation_empty = QCheckBox(translator.t("field.empty_none"))

        self.withdrawal_date = QDateEdit()
        configure_date_edit(self.withdrawal_date, "yyyy-MM-dd")
        self.withdrawal_empty = QCheckBox(translator.t("field.empty_none"))
        self._install_date_debug(self.entry_date, "entry_date")
        self._install_date_debug(self.graduation_date, "graduation_date")
        self._install_date_debug(self.withdrawal_date, "withdrawal_date")

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

    def _install_date_debug(self, widget: QDateEdit, name: str) -> None:
        if not self.debug_ui:
            return
        widget.installEventFilter(DateDebugFilter(name, True))
        self._log_date_widget(name, widget)

    def _log_date_widget(self, name: str, widget: QDateEdit) -> None:
        if not self.debug_ui:
            return
        line = widget.lineEdit()
        read_only = line.isReadOnly() if line else None
        parent_chain = []
        parent = widget.parent()
        while parent:
            parent_chain.append(parent.__class__.__name__)
            parent = parent.parent()
        print(
            "[DATE_DEBUG] "
            f"{name} enabled={widget.isEnabled()} visible={widget.isVisible()} "
            f"calendarPopup={widget.calendarPopup()} displayFormat={widget.displayFormat()} "
            f"keyboardTracking={widget.keyboardTracking()} lineReadOnly={read_only} "
            f"geometry={widget.geometry().getRect()} parents={parent_chain}"
        )

    def get_student(self) -> Optional[db.StudentRow]:
        try:
            student_id = self.student_id.text().strip()
            name = self.name.text().strip()
            if not student_id or not name:
                raise ValueError(self.translator.t("error.required"))
            entry_date = self.entry_date.date().toPython()
            status = self.status.currentData()
            if isinstance(status, str):
                try:
                    status = Status(status)
                except Exception:
                    pass
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

            degree_level = self.degree.currentData()
            if isinstance(degree_level, str):
                try:
                    degree_level = DegreeLevel(degree_level)
                except Exception:
                    pass

            return db.StudentRow(
                student_id=student_id,
                name=name,
                degree_level=degree_level,
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
    app.setStyleSheet(
        """
        * { font-family: "Segoe UI", "Microsoft YaHei"; font-size: 14px; color: #111827; }
        QMainWindow { background: #f3f4f6; }
        #appbar { background: #ffffff; border-bottom: 1px solid #e5e7eb; }
        #sidebar { background: #ffffff; border-right: 1px solid #e5e7eb; }
        #sidebar::item { padding: 10px 14px; margin: 4px 8px; border-radius: 8px; }
        #sidebar::item:selected { background: #111827; color: #ffffff; }
        #sidebar::item:selected:hover { background: #111827; color: #ffffff; }
        #sidebar::item:hover { background: #f3f4f6; color: #111827; }
        QLabel[role="appbar-title"] { font-size: 16px; font-weight: 600; }
        QLabel[role="appbar-meta"] { color: #6b7280; font-size: 12px; }
        QLabel[role="title"] { font-size: 20px; font-weight: 600; }
        QLabel[role="section"] { font-size: 16px; font-weight: 600; }
        QLabel[role="hint"] { color: #6b7280; font-size: 12px; }
        QLabel[role="toolbar-label"] { color: #374151; font-weight: 500; }
        QLabel[role="empty-title"] { font-size: 16px; font-weight: 600; }
        QLabel[role="unit"] { color: #6b7280; font-size: 12px; padding-left: 6px; }
        QToolBar { background: transparent; border: 0; }
        QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            padding: 6px 8px;
            selection-background-color: #e5e7eb;
        }
        QComboBox::drop-down { border: 0; width: 22px; }
        QComboBox::down-arrow { image: none; border: 0; }
        QDateEdit { padding-right: 34px; }
        QDateEdit::drop-down {
            border-left: 1px solid #d1d5db;
            width: 30px;
            background: #eef1f5;
        }
        QDateEdit::down-arrow {
            image: none;
            border: 0;
        }
        QDateEdit::drop-down:hover { background: #e2e8f0; }
        QCalendarWidget {
            background: #ffffff;
            color: #111827;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            min-width: 340px;
            min-height: 280px;
        }
        QCalendarWidget QToolButton {
            background: #eef1f5;
            color: #111827;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 6px 10px;
            min-width: 64px;
            font-size: 14px;
            font-weight: 600;
        }
        QCalendarWidget QToolButton:hover { background: #e2e8f0; }
        QCalendarWidget QToolButton::menu-indicator { image: none; }
        QCalendarWidget QSpinBox {
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 14px;
            font-weight: 600;
        }
        QCalendarWidget QComboBox {
            background: #ffffff;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 14px;
            font-weight: 600;
        }
        QCalendarWidget QAbstractItemView {
            font-size: 14px;
            selection-background-color: #111827;
            selection-color: #ffffff;
            gridline-color: #e5e7eb;
        }
        QCalendarWidget QAbstractItemView::item:selected {
            background: #111827;
            color: #ffffff;
        }
        QPushButton { border-radius: 8px; padding: 6px 12px; }
        QPushButton[variant="primary"] { background: #111827; color: #ffffff; border: 1px solid #111827; }
        QPushButton[variant="secondary"] { background: #ffffff; color: #111827; border: 1px solid #d1d5db; }
        QPushButton[variant="danger"] { background: #ffffff; color: #b91c1c; border: 1px solid #fca5a5; }
        QPushButton:hover[variant="primary"] { background: #0f172a; }
        QPushButton:hover[variant="secondary"] { background: #f3f4f6; }
        QPushButton:hover[variant="danger"] { background: #fef2f2; }
        QPushButton:disabled { background: #f4f4f5; color: #9ca3af; border: 1px solid #e5e7eb; }
        QCheckBox { spacing: 6px; }
        QFrame[role="card"] { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; }
        QTableWidget {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            gridline-color: #e1e6ee;
        }
        QHeaderView::section {
            background: #f9fafb;
            color: #111827;
            padding: 8px;
            border: 0;
            border-bottom: 1px solid #d7dde7;
            font-weight: 600;
        }
        QTableWidget::item:selected { background: #e5e7eb; color: #111827; }
        QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
        QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 5px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QMessageBox { background: #ffffff; }
        """
    )
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    app.exec()


if __name__ == "__main__":
    run()
