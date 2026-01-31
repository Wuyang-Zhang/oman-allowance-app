from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import AllowanceConfig
from ..models import AllowanceRecord, AllowanceType, DegreeLevel, Status
from .paths import db_path


@dataclass(frozen=True)
class StudentRow:
    student_id: str
    name: str
    degree_level: DegreeLevel
    first_entry_date: date
    status: Status
    graduation_date: Optional[date]
    withdrawal_date: Optional[date]


@dataclass(frozen=True)
class ConfigRow:
    version: int
    updated_at: str
    living_allowance_bachelor: str
    living_allowance_master: str
    living_allowance_phd: str
    study_allowance_usd: str
    baggage_allowance_usd: str
    issue_study_if_exit_before_oct_entry_year: int
    withdrawn_living_default: int
    fx_rate_usd_to_cny: str
    usd_quantize: str
    cny_quantize: str
    rounding_mode: str


@dataclass(frozen=True)
class RunRow:
    run_id: int
    created_at: str
    config_version: int
    settlement_month: str
    fx_rate: str


@dataclass(frozen=True)
class RecordRow:
    record_id: int
    run_id: int
    settlement_month: str
    student_id: str
    allowance_type: str
    period_start: str
    period_end: str
    amount_usd: str
    amount_cny: str
    fx_rate: str
    rule_id: str
    description: str
    metadata_json: str


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            degree_level TEXT NOT NULL,
            first_entry_date TEXT NOT NULL,
            status TEXT NOT NULL,
            graduation_date TEXT,
            withdrawal_date TEXT
        );

        CREATE TABLE IF NOT EXISTS configs (
            version INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT NOT NULL,
            living_allowance_bachelor TEXT NOT NULL,
            living_allowance_master TEXT NOT NULL,
            living_allowance_phd TEXT NOT NULL,
            study_allowance_usd TEXT NOT NULL,
            baggage_allowance_usd TEXT NOT NULL,
            issue_study_if_exit_before_oct_entry_year INTEGER NOT NULL,
            withdrawn_living_default INTEGER NOT NULL,
            fx_rate_usd_to_cny TEXT NOT NULL,
            usd_quantize TEXT NOT NULL,
            cny_quantize TEXT NOT NULL,
            rounding_mode TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settlement_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            config_version INTEGER NOT NULL,
            settlement_month TEXT NOT NULL,
            fx_rate TEXT NOT NULL,
            FOREIGN KEY(config_version) REFERENCES configs(version)
        );

        CREATE TABLE IF NOT EXISTS allowance_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            settlement_month TEXT NOT NULL,
            student_id TEXT NOT NULL,
            allowance_type TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            amount_usd TEXT NOT NULL,
            amount_cny TEXT NOT NULL,
            fx_rate TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            description TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES settlement_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS baggage_payments (
            student_id TEXT PRIMARY KEY,
            paid_at TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            settlement_month TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES settlement_runs(run_id)
        );
        """
    )
    conn.commit()
    _ensure_default_config(conn)


def _ensure_default_config(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM configs")
    if cur.fetchone()["cnt"]:
        return
    cfg = AllowanceConfig.default()
    save_config(conn, cfg, withdrawn_living_default=False)


def config_row_to_model(row: ConfigRow) -> AllowanceConfig:
    return AllowanceConfig(
        living_allowance_by_degree={
            DegreeLevel.BACHELOR: Decimal(row.living_allowance_bachelor),
            DegreeLevel.MASTER: Decimal(row.living_allowance_master),
            DegreeLevel.PHD: Decimal(row.living_allowance_phd),
        },
        study_allowance_usd=Decimal(row.study_allowance_usd),
        baggage_allowance_usd=Decimal(row.baggage_allowance_usd),
        issue_study_if_exit_before_oct_entry_year=bool(row.issue_study_if_exit_before_oct_entry_year),
        fx_rate_usd_to_cny=Decimal(row.fx_rate_usd_to_cny),
        usd_quantize=Decimal(row.usd_quantize),
        cny_quantize=Decimal(row.cny_quantize),
        rounding_mode=row.rounding_mode,
    )


def get_latest_config(conn: sqlite3.Connection) -> ConfigRow:
    cur = conn.execute("SELECT * FROM configs ORDER BY version DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No config found")
    return ConfigRow(**dict(row))


def save_config(conn: sqlite3.Connection, config: AllowanceConfig, withdrawn_living_default: bool) -> ConfigRow:
    updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    row = (
        updated_at,
        str(config.living_allowance_by_degree[DegreeLevel.BACHELOR]),
        str(config.living_allowance_by_degree[DegreeLevel.MASTER]),
        str(config.living_allowance_by_degree[DegreeLevel.PHD]),
        str(config.study_allowance_usd),
        str(config.baggage_allowance_usd),
        1 if config.issue_study_if_exit_before_oct_entry_year else 0,
        1 if withdrawn_living_default else 0,
        str(config.fx_rate_usd_to_cny),
        str(config.usd_quantize),
        str(config.cny_quantize),
        str(config.rounding_mode),
    )
    cur = conn.execute(
        """
        INSERT INTO configs (
            updated_at,
            living_allowance_bachelor,
            living_allowance_master,
            living_allowance_phd,
            study_allowance_usd,
            baggage_allowance_usd,
            issue_study_if_exit_before_oct_entry_year,
            withdrawn_living_default,
            fx_rate_usd_to_cny,
            usd_quantize,
            cny_quantize,
            rounding_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )
    conn.commit()
    return get_latest_config(conn)


def list_students(conn: sqlite3.Connection, query: str = "", status: str = "", degree: str = "") -> List[StudentRow]:
    clauses = []
    params: List[Any] = []
    if query:
        clauses.append("(student_id LIKE ? OR name LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    if status:
        clauses.append("status = ?")
        params.append(status)
    if degree:
        clauses.append("degree_level = ?")
        params.append(degree)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur = conn.execute(f"SELECT * FROM students {where_sql} ORDER BY student_id", params)
    return [_row_to_student(row) for row in cur.fetchall()]


def get_student(conn: sqlite3.Connection, student_id: str) -> Optional[StudentRow]:
    cur = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    row = cur.fetchone()
    if not row:
        return None
    return _row_to_student(row)


def upsert_student(conn: sqlite3.Connection, student: StudentRow) -> None:
    conn.execute(
        """
        INSERT INTO students (
            student_id, name, degree_level, first_entry_date, status, graduation_date, withdrawal_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET
            name = excluded.name,
            degree_level = excluded.degree_level,
            first_entry_date = excluded.first_entry_date,
            status = excluded.status,
            graduation_date = excluded.graduation_date,
            withdrawal_date = excluded.withdrawal_date
        """,
        (
            student.student_id,
            student.name,
            student.degree_level.value,
            student.first_entry_date.isoformat(),
            student.status.value,
            student.graduation_date.isoformat() if student.graduation_date else None,
            student.withdrawal_date.isoformat() if student.withdrawal_date else None,
        ),
    )
    conn.commit()


def delete_student(conn: sqlite3.Connection, student_id: str) -> None:
    conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    conn.commit()


def student_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    cur = conn.execute("SELECT status, COUNT(*) AS cnt FROM students GROUP BY status")
    counts = {"total": 0, "In-study": 0, "Graduated": 0, "Withdrawn": 0}
    for row in cur.fetchall():
        counts[row["status"]] = row["cnt"]
        counts["total"] += row["cnt"]
    return counts


def create_run(conn: sqlite3.Connection, config_version: int, settlement_month: str, fx_rate: Decimal) -> RunRow:
    created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    cur = conn.execute(
        "INSERT INTO settlement_runs (created_at, config_version, settlement_month, fx_rate) VALUES (?, ?, ?, ?)",
        (created_at, config_version, settlement_month, str(fx_rate)),
    )
    conn.commit()
    return get_run(conn, cur.lastrowid)


def get_run(conn: sqlite3.Connection, run_id: int) -> RunRow:
    cur = conn.execute("SELECT * FROM settlement_runs WHERE run_id = ?", (run_id,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Run not found")
    return RunRow(**dict(row))


def get_latest_run(conn: sqlite3.Connection) -> Optional[RunRow]:
    cur = conn.execute("SELECT * FROM settlement_runs ORDER BY run_id DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        return None
    return RunRow(**dict(row))


def get_latest_run_for_month(conn: sqlite3.Connection, settlement_month: str) -> Optional[RunRow]:
    cur = conn.execute(
        "SELECT * FROM settlement_runs WHERE settlement_month = ? ORDER BY run_id DESC LIMIT 1",
        (settlement_month,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return RunRow(**dict(row))


def save_records(conn: sqlite3.Connection, run_id: int, settlement_month: str, records: Iterable[AllowanceRecord], fx_rate: Decimal) -> None:
    payload = [
        (
            run_id,
            settlement_month,
            record.student_id,
            record.allowance_type.value,
            record.period_start.isoformat(),
            record.period_end.isoformat(),
            str(record.amount.usd),
            str(record.amount.cny),
            str(fx_rate),
            record.rule_id,
            record.description,
            json.dumps(record.metadata, ensure_ascii=True),
        )
        for record in records
    ]
    conn.executemany(
        """
        INSERT INTO allowance_records (
            run_id, settlement_month, student_id, allowance_type, period_start, period_end,
            amount_usd, amount_cny, fx_rate, rule_id, description, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    conn.commit()


def fetch_records_for_run(conn: sqlite3.Connection, run_id: int) -> List[RecordRow]:
    cur = conn.execute(
        "SELECT * FROM allowance_records WHERE run_id = ? ORDER BY student_id, period_start",
        (run_id,),
    )
    return [RecordRow(**dict(row)) for row in cur.fetchall()]


def fetch_records_for_month(conn: sqlite3.Connection, settlement_month: str) -> List[RecordRow]:
    cur = conn.execute(
        "SELECT * FROM allowance_records WHERE settlement_month = ? ORDER BY student_id, period_start",
        (settlement_month,),
    )
    return [RecordRow(**dict(row)) for row in cur.fetchall()]


def is_baggage_paid(conn: sqlite3.Connection, student_id: str) -> bool:
    cur = conn.execute("SELECT 1 FROM baggage_payments WHERE student_id = ?", (student_id,))
    if cur.fetchone() is not None:
        return True
    cur = conn.execute(
        "SELECT 1 FROM allowance_records WHERE student_id = ? AND allowance_type = ? LIMIT 1",
        (student_id, "ExcessBaggage"),
    )
    return cur.fetchone() is not None


def record_baggage_paid(conn: sqlite3.Connection, student_id: str, run_id: int, settlement_month: str) -> None:
    paid_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    conn.execute(
        """
        INSERT INTO baggage_payments (student_id, paid_at, run_id, settlement_month)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(student_id) DO NOTHING
        """,
        (student_id, paid_at, run_id, settlement_month),
    )
    conn.commit()


def _row_to_student(row: sqlite3.Row) -> StudentRow:
    grad_value = row["graduation_date"]
    withdrawal_value = row["withdrawal_date"]
    return StudentRow(
        student_id=row["student_id"],
        name=row["name"],
        degree_level=DegreeLevel(row["degree_level"]),
        first_entry_date=datetime.fromisoformat(row["first_entry_date"]).date(),
        status=Status(row["status"]),
        graduation_date=datetime.fromisoformat(grad_value).date() if grad_value else None,
        withdrawal_date=datetime.fromisoformat(withdrawal_value).date() if withdrawal_value else None,
    )
