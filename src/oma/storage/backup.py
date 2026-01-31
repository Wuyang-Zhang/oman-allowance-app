from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from . import db
from .paths import backup_dir, db_path


def create_backup() -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir() / f"backup_{timestamp}.zip"
    conn = db.connect()
    try:
        students = [asdict(s) for s in db.list_students(conn)]
        config = asdict(db.get_latest_config(conn))
        runs = _fetch_all(conn, "SELECT * FROM settlement_runs")
        records = _fetch_all(conn, "SELECT * FROM allowance_records")
        metadata = {"created_at": datetime.utcnow().isoformat() + "Z"}
    finally:
        conn.close()

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("students.json", json.dumps(students, ensure_ascii=True, indent=2, default=str))
        zf.writestr("config_versions.json", json.dumps([config], ensure_ascii=True, indent=2))
        zf.writestr("runs.json", json.dumps(runs, ensure_ascii=True, indent=2))
        zf.writestr("allowance_records.json", json.dumps(records, ensure_ascii=True, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=True, indent=2))
    return backup_path


def restore_backup(path: Path, mode: str) -> Tuple[int, int]:
    # returns (students_added, students_skipped)
    pre_backup = create_backup()
    if mode not in {"replace", "merge"}:
        raise ValueError("Invalid restore mode")

    with zipfile.ZipFile(path, "r") as zf:
        students = json.loads(zf.read("students.json").decode("utf-8"))
        configs = json.loads(zf.read("config_versions.json").decode("utf-8"))
        runs = json.loads(zf.read("runs.json").decode("utf-8"))
        records = json.loads(zf.read("allowance_records.json").decode("utf-8"))

    conn = db.connect()
    try:
        if mode == "replace":
            conn.executescript(
                """
                DELETE FROM allowance_records;
                DELETE FROM settlement_runs;
                DELETE FROM baggage_payments;
                DELETE FROM students;
                DELETE FROM configs;
                """
            )
            conn.commit()

            for cfg in configs:
                _insert_config(conn, cfg)
            for run in runs:
                _insert_run(conn, run)
            for record in records:
                _insert_record(conn, record)

            added = 0
            for s in students:
                if _insert_student(conn, s):
                    added += 1
            conn.commit()
            return added, 0

        # merge
        added = 0
        skipped = 0
        for s in students:
            if _insert_student(conn, s, skip_if_exists=True):
                added += 1
            else:
                skipped += 1
        conn.commit()
        return added, skipped
    finally:
        conn.close()


def _fetch_all(conn: sqlite3.Connection, query: str) -> List[Dict]:
    cur = conn.execute(query)
    return [dict(row) for row in cur.fetchall()]


def _insert_student(conn: sqlite3.Connection, s: Dict, skip_if_exists: bool = False) -> bool:
    if skip_if_exists:
        cur = conn.execute("SELECT 1 FROM students WHERE student_id = ?", (s["student_id"],))
        if cur.fetchone() is not None:
            return False
    conn.execute(
        """
        INSERT OR REPLACE INTO students (student_id, name, degree_level, first_entry_date, status, graduation_date, withdrawal_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            s["student_id"],
            s["name"],
            s["degree_level"],
            s["first_entry_date"],
            s.get("status"),
            s.get("graduation_date"),
            s.get("withdrawal_date"),
        ),
    )
    return True


def _insert_config(conn: sqlite3.Connection, cfg: Dict) -> None:
    conn.execute(
        """
        INSERT INTO configs (
            version, updated_at, living_allowance_bachelor, living_allowance_master, living_allowance_phd,
            study_allowance_usd, baggage_allowance_usd, issue_study_if_exit_before_oct_entry_year,
            withdrawn_living_default, fx_rate_usd_to_cny, usd_quantize, cny_quantize, rounding_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cfg["version"],
            cfg["updated_at"],
            cfg["living_allowance_bachelor"],
            cfg["living_allowance_master"],
            cfg["living_allowance_phd"],
            cfg["study_allowance_usd"],
            cfg["baggage_allowance_usd"],
            cfg["issue_study_if_exit_before_oct_entry_year"],
            cfg.get("withdrawn_living_default", 0),
            cfg["fx_rate_usd_to_cny"],
            cfg["usd_quantize"],
            cfg["cny_quantize"],
            cfg["rounding_mode"],
        ),
    )


def _insert_run(conn: sqlite3.Connection, run: Dict) -> None:
    conn.execute(
        """
        INSERT INTO settlement_runs (run_id, created_at, config_version, settlement_month, fx_rate)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            run["run_id"],
            run["created_at"],
            run["config_version"],
            run["settlement_month"],
            run["fx_rate"],
        ),
    )


def _insert_record(conn: sqlite3.Connection, record: Dict) -> None:
    conn.execute(
        """
        INSERT INTO allowance_records (
            record_id, run_id, settlement_month, student_id, allowance_type, period_start, period_end,
            amount_usd, amount_cny, fx_rate, rule_id, description, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["record_id"],
            record["run_id"],
            record["settlement_month"],
            record["student_id"],
            record["allowance_type"],
            record["period_start"],
            record["period_end"],
            record["amount_usd"],
            record["amount_cny"],
            record["fx_rate"],
            record["rule_id"],
            record["description"],
            record["metadata_json"],
        ),
    )
