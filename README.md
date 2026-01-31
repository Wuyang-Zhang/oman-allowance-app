# Oman Students Allowance Calculator (Web UI)

This project provides a deterministic core calculation library plus:\n+- A Windows offline desktop app (PySide6)\n+- A minimal FastAPI + Jinja2 web UI (optional/dev)

## Requirements

- Python 3.9+
- Optional web dependencies:
  - fastapi
  - uvicorn
  - jinja2
  - python-multipart

Install (from repo root):

```
python3 -m pip install -e ".[web]"
```

## Run the Web App

```
python3 -m oma.web
```

Open `http://127.0.0.1:8000`.

By default the app stores data in `oma.db` in the working directory. To change location:

```
export OMA_DB_PATH=/path/to/oma.db
```

## CSV Import Template

Headers (required, case-sensitive):

```
student_id,name,degree_level,first_entry_date,graduation_date,status
```

Example row:

```
S001,Aisha Al-Harthy,Bachelor,2022-09-10,2026-06-30,Graduated
```

Allowed values:
- `degree_level`: `Bachelor`, `Master`, `PhD`
- `status`: `In-study`, `Graduated`, `Withdrawn`
- Dates: `YYYY-MM-DD`

Download the template from the Students page or via `/exports/template`.

## Operational Flow

1. Configure allowances and FX in **Configuration**.
2. Import or create students in **Students**.
3. Run calculations from **Dashboard** or per student.
4. View breakdowns in **Reports** and export settlement files.

## Settlement Export Rules

- Export is in CNY with 2 decimals, ROUND_HALF_UP.
- Includes FX rate used per record, plus rule_id/description for traceability.
- Records are stored per calculation run with the config version used.

## Tests

```
python3 -m pip install -e ".[test,web]"
python3 -m unittest
```

## Notes

- The deterministic core library remains unchanged; the web app uses it as a dependency.
- Tables are auto-created on startup; no manual migration step required.
- UI language can be switched between Chinese and English from the top navigation bar; the choice is stored in a cookie and applies to exports.
- Translations are loaded from `src/oma/web/i18n/zh_CN.json` and `src/oma/web/i18n/en_US.json`.
- Desktop translations are loaded from `src/oma/i18n/zh_CN.json` and `src/oma/i18n/en_US.json`.
