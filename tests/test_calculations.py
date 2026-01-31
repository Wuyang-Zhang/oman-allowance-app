import os
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oma import AllowanceConfig, DegreeLevel, Status, Student, calculate_student_allowances


class AllowanceCalculationTests(unittest.TestCase):
    def test_prorated_entry_month(self):
        config = AllowanceConfig.default()
        config = AllowanceConfig(
            living_allowance_by_degree={DegreeLevel.BACHELOR: Decimal("300.00")},
            study_allowance_usd=config.study_allowance_usd,
            baggage_allowance_usd=config.baggage_allowance_usd,
            issue_study_if_exit_before_oct_entry_year=config.issue_study_if_exit_before_oct_entry_year,
            fx_rate_usd_to_cny=Decimal("7.10"),
            usd_quantize=Decimal("0.01"),
            cny_quantize=Decimal("0.01"),
            rounding_mode=ROUND_HALF_UP,
        )
        student = Student(
            student_id="S001",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 1, 10),
            graduation_date=date(2024, 1, 20),
            status=Status.GRADUATED,
        )
        result = calculate_student_allowances(student, config)
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertEqual(len(living), 1)
        # 22 days out of 31
        self.assertEqual(living[0].amount.usd, Decimal("212.90"))

    def test_living_full_months_inclusive_graduation(self):
        config = AllowanceConfig.default()
        student = Student(
            student_id="S002",
            name="Test",
            degree_level=DegreeLevel.MASTER,
            first_entry_date=date(2024, 1, 10),
            graduation_date=date(2024, 3, 20),
            status=Status.GRADUATED,
        )
        result = calculate_student_allowances(student, config)
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertEqual(len(living), 3)
        # Jan prorate (22/31), Feb full, Mar full
        monthly = config.living_allowance_by_degree[DegreeLevel.MASTER]
        expected = (monthly * Decimal(22) / Decimal(31)).quantize(Decimal("0.01")) + monthly * 2
        total = sum(r.amount.usd for r in living)
        self.assertEqual(total, expected)

    def test_study_allowance_october_rule(self):
        config = AllowanceConfig.default()
        student = Student(
            student_id="S003",
            name="Test",
            degree_level=DegreeLevel.PHD,
            first_entry_date=date(2023, 9, 1),
            graduation_date=date(2025, 6, 30),
            status=Status.GRADUATED,
        )
        result = calculate_student_allowances(student, config)
        study = [r for r in result.records if r.allowance_type.value == "Study"]
        self.assertEqual(len(study), 2)
        years = {r.period_start.year for r in study}
        self.assertEqual(years, {2023, 2024})

    def test_study_allowance_entry_year_override(self):
        config = AllowanceConfig.default()
        student = Student(
            student_id="S004",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 1, 5),
            graduation_date=date(2024, 8, 15),
            status=Status.WITHDRAWN,
        )
        result_default = calculate_student_allowances(student, config)
        study_default = [r for r in result_default.records if r.allowance_type.value == "Study"]
        self.assertEqual(len(study_default), 0)

        override_config = AllowanceConfig(
            living_allowance_by_degree=config.living_allowance_by_degree,
            study_allowance_usd=config.study_allowance_usd,
            baggage_allowance_usd=config.baggage_allowance_usd,
            issue_study_if_exit_before_oct_entry_year=True,
            fx_rate_usd_to_cny=config.fx_rate_usd_to_cny,
            usd_quantize=config.usd_quantize,
            cny_quantize=config.cny_quantize,
            rounding_mode=config.rounding_mode,
        )
        result_override = calculate_student_allowances(student, override_config)
        study_override = [r for r in result_override.records if r.allowance_type.value == "Study"]
        self.assertEqual(len(study_override), 1)
        self.assertEqual(study_override[0].period_start.year, 2024)

    def test_fx_rounding_applied_per_record(self):
        config = AllowanceConfig(
            living_allowance_by_degree={DegreeLevel.BACHELOR: Decimal("100.005")},
            study_allowance_usd=Decimal("0"),
            baggage_allowance_usd=Decimal("0"),
            issue_study_if_exit_before_oct_entry_year=False,
            fx_rate_usd_to_cny=Decimal("7.12345"),
            usd_quantize=Decimal("0.01"),
            cny_quantize=Decimal("0.01"),
            rounding_mode=ROUND_HALF_UP,
        )
        student = Student(
            student_id="S005",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 5, 1),
            graduation_date=date(2024, 5, 1),
            status=Status.GRADUATED,
        )
        result = calculate_student_allowances(student, config)
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertEqual(len(living), 1)
        self.assertEqual(living[0].amount.usd, Decimal("100.01"))
        self.assertEqual(living[0].amount.cny, Decimal("712.42"))

    def test_in_study_without_graduation_date_uses_calculation_date(self):
        config = AllowanceConfig.default()
        student = Student(
            student_id="S006",
            name="Test",
            degree_level=DegreeLevel.BACHELOR,
            first_entry_date=date(2024, 1, 10),
            graduation_date=None,
            status=Status.IN_STUDY,
        )
        result = calculate_student_allowances(student, config, calculation_date=date(2024, 3, 15))
        living = [r for r in result.records if r.allowance_type.value == "Living"]
        self.assertEqual(len(living), 3)


if __name__ == "__main__":
    unittest.main()
