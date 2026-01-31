import os
import re
import sys
import zipfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oma.gui.exporter import export_monthly_settlement_excel
from oma.gui.i18n import Translator
from oma.models import DegreeLevel, Status
from oma.storage.db import ConfigRow, RecordRow, RunRow, StudentRow


class ExportWorkbookTests(unittest.TestCase):
    def test_export_contains_four_sheets_and_rows(self):
        run = RunRow(
            run_id=10,
            created_at="2024-01-31T00:00:00Z",
            config_version=1,
            settlement_month="2024-01",
            fx_rate="7.10",
        )
        config_row = ConfigRow(
            version=1,
            updated_at="2024-01-01T00:00:00Z",
            living_allowance_bachelor="300.00",
            living_allowance_master="350.00",
            living_allowance_phd="400.00",
            study_allowance_usd="800.00",
            baggage_allowance_usd="1200.00",
            issue_study_if_exit_before_oct_entry_year=0,
            withdrawn_living_default=0,
            fx_rate_usd_to_cny="7.10",
            usd_quantize="0.01",
            cny_quantize="0.01",
            rounding_mode="ROUND_HALF_UP",
            rounding_policy="final_only",
        )
        students = [
            StudentRow(
                student_id="S1",
                name="Alice",
                degree_level=DegreeLevel.BACHELOR,
                first_entry_date=date(2024, 1, 10),
                status=Status.IN_STUDY,
                graduation_date=None,
                withdrawal_date=None,
            ),
            StudentRow(
                student_id="S2",
                name="Bob",
                degree_level=DegreeLevel.MASTER,
                first_entry_date=date(2023, 9, 1),
                status=Status.GRADUATED,
                graduation_date=date(2024, 1, 20),
                withdrawal_date=None,
            ),
        ]
        records = [
            RecordRow(
                record_id=1,
                run_id=10,
                settlement_month="2024-01",
                student_id="S1",
                allowance_type="Living",
                period_start="2024-01-01",
                period_end="2024-01-31",
                amount_usd="212.90",
                amount_cny="1511.59",
                fx_rate="7.10",
                rule_id="LIVING_ENTRY_PRORATE",
                description="Prorated living allowance for entry month",
                metadata_json='{"monthly_usd":"300.00","fraction":"0.709677"}',
            ),
            RecordRow(
                record_id=2,
                run_id=10,
                settlement_month="2024-01",
                student_id="S2",
                allowance_type="Study",
                period_start="2024-01-01",
                period_end="2024-01-01",
                amount_usd="800.00",
                amount_cny="5680.00",
                fx_rate="7.10",
                rule_id="STUDY_OCT_IN_STUDY",
                description="Study allowance issued for October in-study",
                metadata_json='{"year":"2024"}',
            ),
            RecordRow(
                record_id=3,
                run_id=10,
                settlement_month="2024-01",
                student_id="S2",
                allowance_type="ExcessBaggage",
                period_start="2024-01-20",
                period_end="2024-01-20",
                amount_usd="1200.00",
                amount_cny="8520.00",
                fx_rate="7.10",
                rule_id="BAGGAGE_ON_GRADUATION",
                description="One-time excess baggage allowance after graduation",
                metadata_json='{"baggage_toggle":"true"}',
            ),
        ]
        translator = Translator(Path(__file__).resolve().parents[1] / "src" / "oma" / "i18n")
        temp_path = export_monthly_settlement_excel(
            run=run,
            config_row=config_row,
            students=students,
            records=records,
            translator=translator,
        )

        try:
            with zipfile.ZipFile(temp_path, "r") as zf:
                workbook = zf.read("xl/workbook.xml").decode("utf-8")
                self.assertIn("Summary_汇总", workbook)
                self.assertIn("Details_明细", workbook)
                self.assertIn("Students_学生信息", workbook)
                self.assertIn("Config_配置快照", workbook)

                sheet1 = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
                sheet2 = zf.read("xl/worksheets/sheet2.xml").decode("utf-8")
                sheet3 = zf.read("xl/worksheets/sheet3.xml").decode("utf-8")
                sheet4 = zf.read("xl/worksheets/sheet4.xml").decode("utf-8")

                self.assertEqual(_row_count(sheet1), 1 + 2)
                self.assertEqual(_row_count(sheet2), 1 + 3)
                self.assertEqual(_row_count(sheet3), 1 + 2)
                self.assertEqual(_row_count(sheet4), 1 + 1)
        finally:
            os.remove(temp_path)


def _row_count(xml_text: str) -> int:
    return len(re.findall(r'<row r="\d+">', xml_text))


if __name__ == "__main__":
    unittest.main()
