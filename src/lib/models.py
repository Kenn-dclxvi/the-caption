from dataclasses import dataclass, field
from typing import List, Dict, Any, Final

__REV: Final[str] = "Rev. 42"

@dataclass
class LedgerMeta:
    generated_at: str
    target_date: str
    version: str
    integrity_status: str
    has_next_day_record: bool = False

@dataclass
class LedgerSummary:
    total_assets_jpy: int
    total_profit_loss_jpy: int
    cash_position_jpy: int
    total_diff_jpy: int
    total_diff_pct: float
    total_profit_loss_pct: float
    invested_capital_jpy: int
    capital_gain_jpy: int
    class_totals: Dict[str, int] = field(default_factory=dict)
    
    total_wtd: str = "---"
    total_mtd: str = "---"
    total_ytd: str = "---"

    exposure_jpy: int = 0
    iron_bank_jpy: int = 0
    safe_ratio_pct: float = 0.0
    damper_coef: float = 0.0
    
    weekly_high: int = 0
    weekly_low: int = 0

@dataclass
class Position:
    id: str
    name: str
    raw_name: str
    asset_class: str
    category: str
    quantity: float
    unit_price: float
    current_price: float
    currency: str
    value_jpy: int
    acquisition_price: int
    profit_loss: int
    profit_loss_pct: float
    prev_day_diff_jpy: int
    prev_day_diff_pct: float
    is_nisa: bool
    is_specific: bool

    share: float = 0.0
    wtd: str = "---"
    mtd: str = "---"
    ytd: str = "---"

@dataclass
class Ledger:
    meta: LedgerMeta
    summary: LedgerSummary
    assets: List[Position]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": self.meta.__dict__,
            "summary": self.summary.__dict__,
            "assets": [a.__dict__ for a in self.assets]
        }
