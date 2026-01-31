from datetime import date

from oma import AllowanceConfig, DegreeLevel, Status, Student, build_report_tables, calculate_student_allowances
from oma.export import Table, write_csv, write_excel_xlsx


def main() -> None:
    config = AllowanceConfig.default()

    students = [
        Student(
            student_id="S001",
            name="Aisha Al-Harthy",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2022, 9, 10),
            graduation_date=date(2026, 6, 30),
            status=Status.GRADUATED,
        ),
        Student(
            student_id="S002",
            name="Salim Al-Saadi",
            degree_level=DegreeLevel.MASTER,
            first_entry_date=date(2024, 2, 1),
            graduation_date=date(2025, 9, 15),
            status=Status.WITHDRAWN,
        ),
    ]

    results = [calculate_student_allowances(student, config) for student in students]
    reports = build_report_tables(students, results)

    output_dir = "outputs"
    write_csv(f"{output_dir}/per_student_records.csv", reports.per_student_records, _headers(reports.per_student_records))
    write_csv(f"{output_dir}/summary_by_student.csv", reports.summary_by_student, _headers(reports.summary_by_student))
    write_csv(f"{output_dir}/summary_by_year.csv", reports.summary_by_year, _headers(reports.summary_by_year))
    write_csv(f"{output_dir}/summary_by_type.csv", reports.summary_by_type, _headers(reports.summary_by_type))

    tables = [
        Table("PerStudentRecords", reports.per_student_records, _headers(reports.per_student_records)),
        Table("SummaryByStudent", reports.summary_by_student, _headers(reports.summary_by_student)),
        Table("SummaryByYear", reports.summary_by_year, _headers(reports.summary_by_year)),
        Table("SummaryByType", reports.summary_by_type, _headers(reports.summary_by_type)),
    ]
    write_excel_xlsx(f"{output_dir}/allowance_reports.xlsx", tables)


def _headers(rows):
    return list(rows[0].keys()) if rows else []


if __name__ == "__main__":
    main()
