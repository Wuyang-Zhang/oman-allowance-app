import unittest
from datetime import date
from decimal import Decimal

from oma.config import AllowanceConfig
from oma.gui.settlement import compute_monthly_settlement
from oma.storage.db import StudentRow
from oma.models import DegreeLevel, Status


class GuiSettlementTests(unittest.TestCase):
    def setUp(self):
        self.config = AllowanceConfig.default()

    def test_entry_month_proration(self):
        student = StudentRow(
            student_id="S1",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 1, 10),
            status=Status.IN_STUDY,
            graduation_date=None,
            withdrawal_date=None,
        )
        result = compute_monthly_settlement(
            [student], date(2024, 1, 1), self.config, [], []
        )
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertEqual(len(living), 1)

    def test_october_study_allowance(self):
        student = StudentRow(
            student_id="S2",
            name="Test",
            degree_level=DegreeLevel.MASTER,
            first_entry_date=date(2024, 9, 1),
            status=Status.IN_STUDY,
            graduation_date=None,
            withdrawal_date=None,
        )
        result = compute_monthly_settlement(
            [student], date(2024, 10, 1), self.config, [], []
        )
        study = [r for r in result.records if r.allowance_type.value == "Study"]
        self.assertEqual(len(study), 1)

    def test_baggage_once_after_graduation(self):
        student = StudentRow(
            student_id="S3",
            name="Test",
            degree_level=DegreeLevel.PHD,
            first_entry_date=date(2023, 1, 1),
            status=Status.GRADUATED,
            graduation_date=date(2024, 6, 30),
            withdrawal_date=None,
        )
        result = compute_monthly_settlement(
            [student], date(2024, 5, 1), self.config, ["S3"], []
        )
        baggage = [r for r in result.records if r.allowance_type.value == "ExcessBaggage"]
        self.assertEqual(len(baggage), 0)

    def test_withdrawal_month_toggle(self):
        student = StudentRow(
            student_id="S4",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2023, 1, 1),
            status=Status.WITHDRAWN,
            graduation_date=None,
            withdrawal_date=date(2024, 5, 20),
        )
        result = compute_monthly_settlement(
            [student], date(2024, 5, 1), self.config, [], ["S4"]
        )
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertGreaterEqual(len(living), 1)

    def test_fx_rounding(self):
        config = AllowanceConfig(
            living_allowance_by_degree={DegreeLevel.BACHELOR: Decimal("100.005")},
            study_allowance_usd=Decimal("0"),
            baggage_allowance_usd=Decimal("0"),
            issue_study_if_exit_before_oct_entry_year=False,
            fx_rate_usd_to_cny=Decimal("7.12345"),
            usd_quantize=Decimal("0.01"),
            cny_quantize=Decimal("0.01"),
            rounding_mode="ROUND_HALF_UP",
        )
        student = StudentRow(
            student_id="S5",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 5, 1),
            status=Status.IN_STUDY,
            graduation_date=None,
            withdrawal_date=None,
        )
        result = compute_monthly_settlement(
            [student], date(2024, 5, 1), config, [], []
        )
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertEqual(living[0].amount.usd, Decimal("100.01"))
        self.assertEqual(living[0].amount.cny, Decimal("712.42"))


if __name__ == "__main__":
    unittest.main()
