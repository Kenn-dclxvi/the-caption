from typing import Any, Dict, Final, List

from src.config.settings import VERSION
from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.lib.models import Ledger, LedgerMeta, LedgerSummary, Position

_CASH_CLASSES: Final[set[str]] = {"CASH", "CASH_EXTERNAL", "SHORT_TERM", "CASH_EQUIVALENTS"}


class ShadowLedgerAdapter:
    __REV: Final[str] = "Rev. 1"

    def to_legacy_ledger(self, shadow_ledger: ShadowLedger) -> Ledger:
        assets = [self._to_position(index, record) for index, record in enumerate(shadow_ledger.assets, start=1)]
        total_assets = int(round(sum(position.value_jpy for position in assets)))
        cash_position = int(round(sum(position.value_jpy for position in assets if position.asset_class in _CASH_CLASSES)))
        class_totals = self._class_totals(assets)
        exposure = total_assets - cash_position
        iron_bank = cash_position
        total_diff_jpy = int(round(sum(
            (record.diff_val_jpy or 0.0)
            for record in shadow_ledger.assets
            if not self._is_cash_record(record)
        )))
        previous_exposure = exposure - total_diff_jpy
        total_return_jpy = int(round(shadow_ledger.total_return_jpy)) if shadow_ledger.total_return_jpy is not None else 0
        total_return_pct = float(shadow_ledger.total_return_pct) if shadow_ledger.total_return_pct is not None else 0.0

        summary = LedgerSummary(
            total_assets_jpy=total_assets,
            total_profit_loss_jpy=total_return_jpy,
            cash_position_jpy=cash_position,
            total_diff_jpy=total_diff_jpy,
            total_diff_pct=round((total_diff_jpy / previous_exposure) * 100.0, 2) if previous_exposure > 0 else 0.0,
            total_profit_loss_pct=total_return_pct,
            invested_capital_jpy=exposure,
            capital_gain_jpy=total_return_jpy,
            class_totals=class_totals,
            total_wtd=self._weighted_period_pct(assets, "wtd"),
            total_mtd=self._weighted_period_pct(assets, "mtd"),
            total_ytd=self._weighted_period_pct(assets, "ytd"),
            exposure_jpy=exposure,
            iron_bank_jpy=iron_bank,
            safe_ratio_pct=(iron_bank / total_assets * 100.0) if total_assets > 0 else 0.0,
            damper_coef=(exposure / total_assets) if total_assets > 0 else 0.0,
            weekly_high=exposure,
            weekly_low=exposure,
        )

        integrity_status = (
            "STAGNANT"
            if any(record.pricing_status in ("MISSING", "STALE") for record in shadow_ledger.assets)
            else "VERIFIED"
        )
        return Ledger(
            meta=LedgerMeta(
                generated_at=shadow_ledger.generated_at,
                target_date=shadow_ledger.target_date,
                version=f"{VERSION}-v4",
                integrity_status=integrity_status,
                has_next_day_record=False,
            ),
            summary=summary,
            assets=assets,
        )

    def to_canonical_document(self, shadow_ledger: ShadowLedger) -> Dict[str, Any]:
        """日次で保存する出力の正本を構築する（ADR-0002）。

        v3 の Position は資産別の取得原価と損益を持つが、v4 の計算元（SSOT A / B）に
        資産別原価は存在せず、`portfolio_basis.json` は月次総額のみを持つ。
        正本へダミー値を混入させないため、v4 で意味を持つ値だけを保持し、
        代わりに v4 固有の鮮度（`pricing_status` / `source_date` / `warnings`）を残す。
        `meta` と `summary` は週次/月次の読み取り互換のため v3 形式を維持する。
        """
        legacy = self.to_legacy_ledger(shadow_ledger)
        return {
            "meta": dict(legacy.meta.__dict__),
            "summary": dict(legacy.summary.__dict__),
            "assets": [
                self._to_canonical_asset(index, record)
                for index, record in enumerate(shadow_ledger.assets, start=1)
            ],
        }

    def _to_canonical_asset(self, index: int, record: ShadowAssetRecord) -> Dict[str, Any]:
        is_cash = self._is_cash_record(record)
        return {
            "id": record.source_symbol or record.name or f"shadow-{index}",
            "name": record.name,
            "source": record.source,
            "asset_class": record.asset_class,
            "category": record.category,
            "currency": record.currency,
            "units": record.units,
            "price": record.price,
            "fx_rate": record.fx_rate,
            "source_symbol": record.source_symbol,
            "source_date": record.source_date,
            "value_jpy": int(round(record.current_value_jpy)),
            "day_diff_jpy": 0.0 if is_cash else record.diff_val_jpy,
            "day_diff_pct": 0.0 if is_cash else record.diff_pct,
            "wtd_pct": None if is_cash else record.wtd_pct,
            "mtd_pct": None if is_cash else record.mtd_pct,
            "ytd_pct": None if is_cash else record.ytd_pct,
            "pricing_status": record.pricing_status,
            "warnings": list(record.warnings),
        }

    def _to_position(self, index: int, record: ShadowAssetRecord) -> Position:
        value_jpy = int(round(record.current_value_jpy))
        price = float(record.price or 0.0)
        asset_id = record.source_symbol or record.name or f"shadow-{index}"
        is_cash = record.source == "ABSOLUTE_AMOUNT" or record.asset_class in _CASH_CLASSES
        diff_jpy = 0 if is_cash else int(round(record.diff_val_jpy or 0.0))
        diff_pct = 0.0 if is_cash else float(record.diff_pct or 0.0)
        return Position(
            id=asset_id,
            name=record.name,
            raw_name=record.name,
            asset_class="SHORT_TERM" if is_cash else record.asset_class,
            category="CASH" if is_cash else "INVESTMENT",
            quantity=float(record.units or 0.0),
            unit_price=price,
            current_price=price,
            currency=record.currency,
            value_jpy=value_jpy,
            acquisition_price=value_jpy,
            profit_loss=0,
            profit_loss_pct=0.0,
            prev_day_diff_jpy=diff_jpy,
            prev_day_diff_pct=diff_pct,
            is_nisa=False,
            is_specific=False,
            wtd=self._fmt_pct(record.wtd_pct) if not is_cash else "---",
            mtd=self._fmt_pct(record.mtd_pct) if not is_cash else "---",
            ytd=self._fmt_pct(record.ytd_pct) if not is_cash else "---",
        )

    def _class_totals(self, assets: List[Position]) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for asset in assets:
            totals[asset.asset_class] = totals.get(asset.asset_class, 0) + asset.value_jpy
        return totals

    def _is_cash_record(self, record: ShadowAssetRecord) -> bool:
        return record.source == "ABSOLUTE_AMOUNT" or record.asset_class in _CASH_CLASSES

    def _weighted_period_pct(self, assets: List[Position], attr: str) -> str:
        market_assets = [asset for asset in assets if asset.category != "CASH" and asset.value_jpy > 0]
        if not market_assets:
            return "---"

        weighted = 0.0
        period_base_total = 0.0
        has_value = False
        for asset in market_assets:
            raw = getattr(asset, attr, "---")
            if raw == "---":
                # Preserve the existing conservative missing-data treatment:
                # keep the asset in the denominator with zero contribution.
                period_base_total += asset.value_jpy
                continue
            period_pct = float(str(raw).replace("%", ""))
            growth_factor = 1.0 + period_pct / 100.0
            if growth_factor <= 0:
                return "---"
            period_base_value = asset.value_jpy / growth_factor
            period_base_total += period_base_value
            weighted += period_pct * period_base_value
            has_value = True
        return f"{weighted / period_base_total:+.2f}%" if has_value and period_base_total > 0 else "---"

    def _fmt_pct(self, value: float | None) -> str:
        return f"{value:+.2f}%" if value is not None else "---"
