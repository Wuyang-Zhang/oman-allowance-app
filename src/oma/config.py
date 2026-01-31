from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

from .models import DegreeLevel


@dataclass(frozen=True)
class AllowanceConfig:
    """Configuration for allowance calculation and currency conversion."""

    living_allowance_by_degree: Dict[DegreeLevel, Decimal]
    study_allowance_usd: Decimal
    baggage_allowance_usd: Decimal
    issue_study_if_exit_before_oct_entry_year: bool
    fx_rate_usd_to_cny: Decimal
    usd_quantize: Decimal
    cny_quantize: Decimal
    rounding_mode: str
    rounding_policy: str

    @staticmethod
    def default() -> "AllowanceConfig":
        return AllowanceConfig(
            living_allowance_by_degree={
                DegreeLevel.BACHELOR: Decimal("300.00"),
                DegreeLevel.MASTER: Decimal("350.00"),
                DegreeLevel.PHD: Decimal("400.00"),
            },
            study_allowance_usd=Decimal("800.00"),
            baggage_allowance_usd=Decimal("1200.00"),
            issue_study_if_exit_before_oct_entry_year=False,
            fx_rate_usd_to_cny=Decimal("7.10"),
            usd_quantize=Decimal("0.01"),
            cny_quantize=Decimal("0.01"),
            rounding_mode=ROUND_HALF_UP,
            rounding_policy="final_only",
        )
