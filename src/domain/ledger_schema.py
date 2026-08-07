import re
from datetime import datetime
from typing import Any, Dict, Final, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.lib.logger import setup_logger

logger = setup_logger(__name__)

_META_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_META_VALID_STATUSES = frozenset({"VERIFIED", "STAGNANT"})


class _MetaSchema(BaseModel):
    target_date: str
    version: str
    integrity_status: str
    generated_at: str
    has_next_day_record: bool = False

    @field_validator("target_date")
    @classmethod
    def _date_format(cls, v: str) -> str:
        if not _META_DATE_RE.match(v):
            raise ValueError(f"target_date format must be YYYY-MM-DD, got: {v!r}")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"target_date is not a valid calendar date: {v!r}")
        return v

    @field_validator("integrity_status")
    @classmethod
    def _status_enum(cls, v: str) -> str:
        if v not in _META_VALID_STATUSES:
            raise ValueError(f"integrity_status must be one of {sorted(_META_VALID_STATUSES)}, got: {v!r}")
        return v


class _SummarySchema(BaseModel):
    total_assets_jpy: int
    total_profit_loss_jpy: int
    cash_position_jpy: int
    total_diff_jpy: int
    total_diff_pct: float
    total_profit_loss_pct: float
    invested_capital_jpy: int
    capital_gain_jpy: int


class LedgerJsonSchema(BaseModel):
    meta: _MetaSchema
    summary: _SummarySchema
    assets: List[Dict[str, Any]]


ASSET_SOURCE_UNSPECIFIED: Final[str] = "UNSPECIFIED"


class MonthlyLedgerAsset(BaseModel):
    """月次集計が読む確定台帳の資産行。

    v4 の正本は計算元の区分（SSOT A / SSOT B）を `source` に持つが、v3 系の台帳は
    この列を持たない。欠落は `UNSPECIFIED` として明示し、既知の値以外は検証で弾く。
    月次が使わない列は保持しない。
    """

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    source: Literal["MARKET_UNITS", "ABSOLUTE_AMOUNT", "UNSPECIFIED"] = ASSET_SOURCE_UNSPECIFIED
    asset_class: str
    value_jpy: float


class _MonthlyLedgerMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_date: str
    integrity_status: str

    @field_validator("target_date")
    @classmethod
    def _date_format(cls, v: str) -> str:
        if not _META_DATE_RE.match(v):
            raise ValueError(f"target_date format must be YYYY-MM-DD, got: {v!r}")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"target_date is not a valid calendar date: {v!r}")
        return v

    @field_validator("integrity_status")
    @classmethod
    def _status_enum(cls, v: str) -> str:
        if v not in _META_VALID_STATUSES:
            raise ValueError(f"integrity_status must be one of {sorted(_META_VALID_STATUSES)}, got: {v!r}")
        return v


class _MonthlyLedgerSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_assets_jpy: Optional[float] = None


class MonthlyLedger(BaseModel):
    """月次集計へ渡す確定台帳の検証済み表現。

    `src/lib/models` の `Ledger` / `Position` は v3 の表示形状（取得原価・損益）を持ち、
    v4 の正本が持つ計算元区分 `source` を表現しない。月次が必要とするのは対象日・
    総額・（source, asset_class, value_jpy）だけなので、双方の台帳形状を受けられる
    専用モデルとして検証する（domain へ無検証の dict を渡さないため）。
    """

    model_config = ConfigDict(extra="ignore")

    meta: _MonthlyLedgerMeta
    summary: _MonthlyLedgerSummary = Field(default_factory=_MonthlyLedgerSummary)
    assets: List[MonthlyLedgerAsset] = Field(default_factory=list)

    @property
    def target_date(self) -> str:
        return self.meta.target_date

    @property
    def integrity_status(self) -> str:
        return self.meta.integrity_status

    @property
    def total_value_jpy(self) -> float:
        if self.summary.total_assets_jpy is None:
            return sum(asset.value_jpy for asset in self.assets)
        return float(self.summary.total_assets_jpy)


def parse_monthly_ledger(data: Dict[str, Any], source: str = "") -> Optional[MonthlyLedger]:
    """確定台帳の dict を月次用の検証済みモデルへ変換する。検証不能なら None を返す。"""
    try:
        return MonthlyLedger.model_validate(data)
    except Exception as exc:
        tag = f" ({source})" if source else ""
        logger.error(f"[Guard] Monthly ledger schema violation{tag}: {exc}")
        return None


class ShadowAssetRecord(BaseModel):
    source: Literal["MARKET_UNITS", "ABSOLUTE_AMOUNT"]
    name: str
    asset_class: str
    category: str
    currency: str = "JPY"
    units: Optional[float] = None
    price: Optional[float] = None
    fx_rate: Optional[float] = None
    source_symbol: Optional[str] = None
    source_date: Optional[str] = None
    current_value_jpy: float = Field(ge=0)
    diff_val_jpy: Optional[float] = None
    diff_pct: Optional[float] = None
    wtd_pct: Optional[float] = None
    mtd_pct: Optional[float] = None
    ytd_pct: Optional[float] = None
    pricing_status: Literal["PRICED", "STATIC", "MISSING", "STALE"] = "PRICED"
    warnings: List[str] = Field(default_factory=list)


class ShadowLedgerUnitsSource(BaseModel):
    type: Literal["SNAPSHOT", "LIVE_CSV"]
    path: str
    snapshot_target_date: Optional[str] = None


class ShadowLedger(BaseModel):
    schema_version: str = "v4.1-shadow-ledger"
    target_date: str
    jp_market_date: Optional[str] = None
    generated_at: str
    ssot_a_path: str
    units_source: Optional[ShadowLedgerUnitsSource] = None
    ssot_b_path: str
    ssot_b_active_key: str
    total_value_jpy: float = Field(ge=0)
    basis_active_key: Optional[str] = None
    return_base_value_jpy: Optional[float] = Field(default=None, ge=0)
    total_acquisition_cost_jpy: Optional[float] = Field(default=None, ge=0)
    total_return_jpy: Optional[float] = None
    total_return_pct: Optional[float] = None
    assets: List[ShadowAssetRecord]

    @field_validator("target_date")
    @classmethod
    def _target_date_format(cls, v: str) -> str:
        if not _META_DATE_RE.match(v):
            raise ValueError(f"target_date format must be YYYY-MM-DD, got: {v!r}")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"target_date is not a valid calendar date: {v!r}")
        return v

    @field_validator("jp_market_date")
    @classmethod
    def _jp_market_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _META_DATE_RE.match(v):
            raise ValueError(f"jp_market_date format must be YYYY-MM-DD, got: {v!r}")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"jp_market_date is not a valid calendar date: {v!r}")
        return v

    @model_validator(mode="after")
    def _total_matches_assets(self) -> "ShadowLedger":
        calculated = sum(asset.current_value_jpy for asset in self.assets)
        if abs(self.total_value_jpy - calculated) >= 0.01:
            raise ValueError(
                f"total_value_jpy must match asset sum: {self.total_value_jpy} != {calculated}"
            )
        return self


def validate_ledger_dict(data: Dict[str, Any], source: str = "") -> bool:
    try:
        LedgerJsonSchema.model_validate(data)
        return True
    except Exception as exc:
        tag = f" ({source})" if source else ""
        logger.error(f"[Guard] Ledger schema violation{tag}: {exc}")
        return False
