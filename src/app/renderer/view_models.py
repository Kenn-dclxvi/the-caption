from typing import Final, Dict, Any, List, Optional
from src.lib.models import Position, LedgerSummary

__REV: Final[str] = "Rev. 15"

_C_INK = "#1e293b"
_C_GOLD = "#c5a059"
_C_SLATE = "#64748b"

_LABEL_MAP: Final[Dict[str, str]] = {
    "MUTUAL_FUNDS": "MUTUAL FUNDS",
    "US_STOCK": "US STOCKS",
    "COMMODITIES": "COMMODITIES",
    "JP_STOCK": "JAPAN STOCKS",
    "SHORT_TERM": "CASH EQUIVALENTS",
    "CRYPTO": "CRYPTO ASSETS",
    "BOND": "BONDS",
    "REIT": "REITs"
}

class PositionViewModel:
    def __init__(self, position: Position) -> None:
        self.__pos: Final[Position] = position

    @property
    def id(self) -> str: return self.__pos.id

    @property
    def name(self) -> str: return self.__pos.name

    @property
    def label(self) -> str:
        if self.__pos.category == "AGGREGATED":
            return _LABEL_MAP.get(self.__pos.asset_class, self.__pos.asset_class)
        return self.__pos.name

    @property
    def fmt_value(self) -> str: return f"{self.__pos.value_jpy:,}"
    @property
    def fmt_diff_jpy(self) -> str: return f"{self.__pos.prev_day_diff_jpy:+,}"
    @property
    def fmt_diff_pct(self) -> str: return f"{self.__pos.prev_day_diff_pct:+.2f}%"
    @property
    def share_pct(self) -> float: return self.__pos.share
    
    @property
    def wtd(self) -> str: return self.__pos.wtd
    @property
    def mtd(self) -> str: return self.__pos.mtd
    @property
    def ytd(self) -> str: return self.__pos.ytd

    @property
    def is_cash(self) -> bool:
        return self.__pos.asset_class in ["SHORT_TERM", "CASH_EQUIVALENTS"]

    @property
    def metrics_display_style(self) -> str:
        return "display: none;" if self.is_cash else "display: block;"

class SummaryViewModel:
    def __init__(self, summary: LedgerSummary) -> None:
        self.__sum: Final[LedgerSummary] = summary

    @property
    def fmt_total_assets(self) -> str: return f"{self.__sum.total_assets_jpy:,}"
    
    @property
    def fmt_exposure(self) -> str: return f"{self.__sum.exposure_jpy:,}"

    @property
    def fmt_total_pl(self) -> str: return f"{self.__sum.capital_gain_jpy:+,}"
    @property
    def fmt_total_diff(self) -> str: return f"{self.__sum.total_diff_jpy:+,}"
    @property
    def fmt_total_diff_pct(self) -> str: return f"{self.__sum.total_diff_pct:+.2f}%"
    
    @property
    def total_wtd(self) -> str: return self.__sum.total_wtd
    @property
    def total_mtd(self) -> str: return self.__sum.total_mtd
    @property
    def total_ytd(self) -> str: return self.__sum.total_ytd
    
    @property
    def fmt_weekly_range(self) -> str:
        if self.__sum.weekly_high == 0: return "---"
        return f"{self.__sum.weekly_low:,} - {self.__sum.weekly_high:,}"
    
    @property
    def fmt_iron_bank(self) -> str: return f"{self.__sum.iron_bank_jpy:,}"
    @property
    def fmt_safe_ratio(self) -> str: return f"{self.__sum.safe_ratio_pct:.1f}%"
    @property
    def gold_share(self) -> float:
        pl, exp = self.__sum.capital_gain_jpy, self.__sum.exposure_jpy
        return min((pl / exp) * 100, 100.0) if pl > 0 and exp > 0 else 0.0
    @property
    def slate_share(self) -> float: return 100.0 - self.gold_share
    @property
    def exposure_width_pct(self) -> float: return self.__sum.damper_coef * 100
    @property
    def safe_ratio_pct(self) -> float: return self.__sum.safe_ratio_pct
    @property
    def is_profit(self) -> bool: return self.__sum.capital_gain_jpy > 0

    @property
    def total_pl_color(self) -> str:
        if self.__sum.capital_gain_jpy > 0:
            return _C_GOLD
        if self.__sum.capital_gain_jpy < 0:
            return _C_INK
        return _C_INK

    @property
    def day_color(self) -> str:
        if self.__sum.total_diff_jpy > 0:
            return _C_GOLD
        if self.__sum.total_diff_jpy < 0:
            return _C_SLATE
        return _C_INK

class CollectionPositionViewModel:
    def __init__(self, name: str, metrics: Dict[str, Any], code: Optional[str] = None) -> None:
        self.__name: Final[str] = name
        self.__metrics: Final[Dict[str, Any]] = metrics
        self.__code: Final[str] = code or str(metrics.get("code") or metrics.get("source_symbol") or name)

    @property
    def name(self) -> str: return self.__name

    @property
    def code(self) -> str: return self.__code

    @property
    def section_key(self) -> str: return self.__metrics["asset_class"]

    @property
    def asset_class(self) -> str: return self.__metrics["asset_class"]

    @property
    def currency(self) -> str: return self.__metrics["currency"]

    @property
    def sort_value_jpy(self) -> int:
        return int(self.__metrics.get("current_value") or 0)

    @property
    def is_us_stock(self) -> bool: return self.asset_class == "US_STOCK"

    @property
    def fmt_value(self) -> str: return f"{self.sort_value_jpy:,}"

    @property
    def fmt_diff_jpy(self) -> str: return f"{int(self.__metrics['diff_val']):+,}"

    @property
    def fmt_diff_pct(self) -> str: return f"{self.__metrics['diff_pct']:+.2f}%"

    @property
    def fmt_mtd(self) -> str: return f"{self.__metrics['m_pct']:+.2f}%"

    @property
    def fmt_ytd(self) -> str: return f"{self.__metrics['y_pct']:+.2f}%"

    @property
    def share_pct(self) -> float: return self.__metrics.get('share_pct', 0.0)

    @property
    def fx_caption(self) -> str:
        fx_rate = self.__metrics.get("fx_rate")
        if not self.is_us_stock or fx_rate is None:
            return ""
        return f"USD/JPY {fx_rate:.2f}"

    @property
    def fmt_usd_value(self) -> str:
        if not self.is_us_stock:
            return ""
        return f"{self.__metrics['native_value']:,.2f}"

    @property
    def has_day_detail_line(self) -> bool:
        return self.is_us_stock

    @property
    def diff_color(self) -> str:
        return _C_GOLD if self.__metrics['diff_pct'] > 0 else _C_INK

    @property
    def day_color(self) -> str:
        return _C_GOLD if self.__metrics['diff_pct'] > 0 else "#64748b"

    @property
    def day_is_positive(self) -> bool:
        return self.__metrics['diff_pct'] > 0


class CollectionSummaryViewModel:
    def __init__(
        self,
        total_value: float,
        total_diff_jpy: float,
        total_diff_pct: float,
        display_date: str,
        fx_rate: Optional[float] = None,
        fx_date: Optional[str] = None,
    ) -> None:
        self.__total_value: Final[float] = total_value
        self.__total_diff_jpy: Final[float] = total_diff_jpy
        self.__total_diff_pct: Final[float] = total_diff_pct
        self.__display_date: Final[str] = display_date
        self.__fx_rate: Final[Optional[float]] = fx_rate
        self.__fx_date: Final[Optional[str]] = fx_date

    @property
    def fmt_total_value(self) -> str: return f"{int(self.__total_value):,}"

    @property
    def fmt_total_diff(self) -> str: return f"{int(self.__total_diff_jpy):+,}"

    @property
    def fmt_total_diff_pct(self) -> str: return f"{self.__total_diff_pct:+.2f}%"

    @property
    def display_date(self) -> str: return self.__display_date

    @property
    def has_fx_reference(self) -> bool:
        return self.__fx_rate is not None

    @property
    def fmt_fx_reference(self) -> str:
        if self.__fx_rate is None:
            return ""
        suffix = f" ({self.__fx_date})" if self.__fx_date else ""
        return f"USD/JPY {self.__fx_rate:.2f}{suffix}"

    @property
    def total_diff_color(self) -> str:
        return _C_GOLD if self.__total_diff_jpy > 0 else "#64748b"

    @property
    def day_color(self) -> str:
        return self.total_diff_color


class CollectionSectionViewModel:
    def __init__(self, title: str, key: str, positions: List[CollectionPositionViewModel]) -> None:
        self.__title: Final[str] = title
        self.__key: Final[str] = key
        self.__positions: Final[List[CollectionPositionViewModel]] = positions

    @property
    def title(self) -> str: return self.__title

    @property
    def key(self) -> str: return self.__key

    @property
    def positions(self) -> List[CollectionPositionViewModel]: return self.__positions
