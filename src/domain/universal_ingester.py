import csv
import json
import math
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, Final, List, Literal, Optional, Tuple

import pandas as pd

from src.config.settings import DATA_DIR, DIR_COLLECTION_HISTORY
from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.infra.market_data import is_market_closed, CLOSE_CHECK_ASSET_CLASSES
from src.domain.market_units_snapshot import (
    MARKET_UNITS_CSV,
    MarketUnitsSnapshotError,
    UnitsResolution,
    load_market_units_csv,
    load_units_snapshot,
    snapshot_path,
)
from src.lib.logger import setup_logger
from src.lib.atomic_write import atomic_write_json
from src.lib.timeline_controller import TimelineController

logger = setup_logger(__name__)

_FX_ASSET_CLASS: Final[str] = "FX"
_US_STOCK_ASSET_CLASS: Final[str] = "US_STOCK"
_COMMODITY_ASSET_CLASS: Final[str] = "COMMODITIES"
_COMMODITY_OZ_TO_G: Final[float] = 31.1034768
_US_MARKET_DATE_CLASSES: Final[set[str]] = {"US_STOCK", "COMMODITIES", "FX"}
_JP_MARKET_DATE_CLASSES: Final[set[str]] = {"MUTUAL_FUNDS", "JP_STOCK"}
_REQUIRED_SSOT_A_COLUMNS: Final[set[str]] = {
    "name",
    "units",
    "csv_url",
}
_EXTERNAL_MONTH_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


class CanonicalLedgerInputError(ValueError):
    """A required Canonical Ledger input is missing, unreadable, or invalid."""


class UniversalIngester:
    __REV: Final[str] = "Rev. 2"

    def __init__(
        self,
        funds_csv_path: Optional[str] = None,
        external_assets_path: Optional[str] = None,
        portfolio_basis_path: Optional[str] = None,
        history_dir: Optional[str] = None,
        units_snapshot_dir: Optional[str] = None,
        timeline: Optional[TimelineController] = None,
        is_closed_fn: Optional[Callable[[str, str, Optional[str]], bool]] = None,
    ) -> None:
        logger.info(f"[{self.__REV}] Initializing UniversalIngester")
        self.funds_csv_path = funds_csv_path or MARKET_UNITS_CSV
        self.ssot_a_path = self.funds_csv_path
        self.external_assets_path = external_assets_path or os.path.join(DATA_DIR, "external_assets.json")
        self.portfolio_basis_path = portfolio_basis_path or os.path.join(DATA_DIR, "portfolio_basis.json")
        self.history_dir = history_dir or DIR_COLLECTION_HISTORY
        self.units_snapshot_dir = units_snapshot_dir
        self.timeline = timeline or TimelineController()
        self._is_closed_fn: Callable[[str, str, Optional[str]], bool] = is_closed_fn or is_market_closed

    def build_shadow_ledger(
        self,
        target_date: Optional[str] = None,
        units_mode: Literal["daily", "strict"] = "daily",
        allow_live_csv_in_strict: bool = False,
        previous_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ShadowLedger:
        active_date = target_date or datetime.now().strftime("%Y-%m-%d")
        canonical_market_assets = self._load_fund_config()
        units_resolution = self._resolve_market_units(
            active_date,
            units_mode,
            allow_live_csv_in_strict,
            live_market_assets=canonical_market_assets,
        )
        market_assets = units_resolution["items"]
        external_items, active_key = self._load_external_assets(active_date)
        basis_key, total_acquisition_cost = self._load_portfolio_basis(active_date)
        us_market_date = self._resolve_us_market_date(active_date)
        jp_market_date = self._resolve_jp_market_date(active_date)

        fx_metrics = self._calculate_fx_metrics(market_assets, us_market_date)
        records: List[ShadowAssetRecord] = []
        for asset in market_assets:
            if asset["asset_class"] == _FX_ASSET_CLASS:
                continue
            records.append(
                self._build_market_record(
                    asset,
                    active_date,
                    us_market_date,
                    jp_market_date,
                    fx_metrics,
                    previous_records,
                )
            )

        for item in external_items:
            records.append(self._build_external_record(item))

        total_value = sum(record.current_value_jpy for record in records)
        return_base_value = sum(record.current_value_jpy for record in records if record.source == "MARKET_UNITS")
        total_return = return_base_value - total_acquisition_cost if total_acquisition_cost is not None else None
        total_return_pct = (
            (total_return / total_acquisition_cost * 100.0)
            if total_return is not None and total_acquisition_cost and total_acquisition_cost > 0
            else None
        )
        return ShadowLedger(
            target_date=active_date,
            jp_market_date=jp_market_date,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            ssot_a_path=self.ssot_a_path,
            units_source=units_resolution["source"],
            ssot_b_path=self.external_assets_path,
            ssot_b_active_key=active_key,
            total_value_jpy=total_value,
            basis_active_key=basis_key,
            return_base_value_jpy=return_base_value,
            total_acquisition_cost_jpy=total_acquisition_cost,
            total_return_jpy=total_return,
            total_return_pct=total_return_pct,
            assets=records,
        )

    def _resolve_us_market_date(self, target_date: str) -> str:
        try:
            us_context = self.timeline.get_us_market_context(target_date)
            trading_date = us_context.get("trading_date") if isinstance(us_context, dict) else None
            if trading_date:
                return str(trading_date)
        except Exception as exc:
            logger.warning(f"[Guard] Failed to resolve US market date for {target_date}; using target_date: {exc}")
        return target_date

    def _resolve_jp_market_date(self, target_date: str) -> str:
        try:
            trading_date = self.timeline.determine_jp_market_date(target_date)
            if trading_date:
                return str(trading_date)
        except Exception as exc:
            logger.warning(f"[Guard] Failed to resolve JP market date for {target_date}; using target_date: {exc}")
        return target_date

    def run(
        self,
        target_date: Optional[str] = None,
        output_path: Optional[str] = None,
        units_mode: Literal["daily", "strict"] = "daily",
        allow_live_csv_in_strict: bool = False,
        previous_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ShadowLedger:
        ledger = self.build_shadow_ledger(
            target_date,
            units_mode=units_mode,
            allow_live_csv_in_strict=allow_live_csv_in_strict,
            previous_records=previous_records,
        )
        if output_path:
            atomic_write_json(output_path, ledger.model_dump())
        return ledger

    def _resolve_market_units(
        self,
        target_date: str,
        units_mode: Literal["daily", "strict"],
        allow_live_csv_in_strict: bool,
        live_market_assets: Optional[List[Dict[str, Any]]] = None,
    ) -> UnitsResolution:
        if units_mode not in {"daily", "strict"}:
            raise ValueError(f"units_mode must be 'daily' or 'strict', got: {units_mode}")

        snapshot = snapshot_path(target_date, self.units_snapshot_dir)
        if os.path.exists(snapshot):
            try:
                snapshot_items = load_units_snapshot(snapshot, target_date, self.ssot_a_path)
                self._validate_market_items(snapshot_items, snapshot)
                return {
                    "items": snapshot_items,
                    "source": {
                        "type": "SNAPSHOT",
                        "path": snapshot,
                        "snapshot_target_date": target_date,
                    },
                }
            except (MarketUnitsSnapshotError, CanonicalLedgerInputError) as exc:
                if units_mode == "strict":
                    raise
                logger.warning(f"[Guard] Invalid market units snapshot; falling back to live CSV: {snapshot} ({exc})")
                return self._load_live_market_units(live_market_assets)

        if units_mode == "strict" and not allow_live_csv_in_strict:
            raise MarketUnitsSnapshotError(f"market units snapshot missing: {snapshot}")

        logger.warning(f"[Guard] Market units snapshot missing; falling back to live CSV: {snapshot}")
        return self._load_live_market_units(live_market_assets)

    def _load_live_market_units(
        self,
        live_market_assets: Optional[List[Dict[str, Any]]] = None,
    ) -> UnitsResolution:
        return {
            "items": live_market_assets if live_market_assets is not None else self._load_fund_config(),
            "source": {
                "type": "LIVE_CSV",
                "path": self.ssot_a_path,
            },
        }

    def _load_fund_config(self) -> List[Dict[str, Any]]:
        try:
            with open(self.ssot_a_path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                columns = set(reader.fieldnames or [])
            missing_columns = sorted(_REQUIRED_SSOT_A_COLUMNS - columns)
            if missing_columns:
                raise CanonicalLedgerInputError(
                    f"SSOT A missing required columns {missing_columns}: {self.ssot_a_path}"
                )
            funds = load_market_units_csv(self.ssot_a_path)
            self._validate_market_items(funds, self.ssot_a_path)
            return funds
        except CanonicalLedgerInputError:
            raise
        except FileNotFoundError as exc:
            raise CanonicalLedgerInputError(f"SSOT A missing: {self.ssot_a_path}") from exc
        except Exception as exc:
            raise CanonicalLedgerInputError(
                f"SSOT A unreadable or structurally invalid: {self.ssot_a_path} ({exc})"
            ) from exc

    def _validate_market_items(self, items: List[Dict[str, Any]], source: str) -> None:
        for index, row in enumerate(items):
            name = str(row.get("name") or "").strip()
            asset_class = str(row.get("asset_class") or "").strip()
            currency = str(row.get("currency") or "").strip()
            source_symbol = str(row.get("source_symbol") or "").strip()
            if not all((name, asset_class, currency, source_symbol)):
                raise CanonicalLedgerInputError(
                    f"SSOT A item[{index}] missing required identity fields: {source}"
                )
            try:
                units = float(row.get("units"))
            except (TypeError, ValueError) as exc:
                raise CanonicalLedgerInputError(
                    f"SSOT A item[{index}] units must be numeric: {source}"
                ) from exc
            if not math.isfinite(units) or units < 0:
                raise CanonicalLedgerInputError(
                    f"SSOT A item[{index}] units must be finite and non-negative: {source}"
                )
            row["units"] = units

    def _load_external_assets(self, target_date: str) -> Tuple[List[Dict[str, Any]], str]:
        try:
            with open(self.external_assets_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError as exc:
            raise CanonicalLedgerInputError(f"SSOT B missing: {self.external_assets_path}") from exc
        except Exception as exc:
            raise CanonicalLedgerInputError(
                f"SSOT B unreadable: {self.external_assets_path} ({exc})"
            ) from exc

        if not isinstance(payload, dict):
            raise CanonicalLedgerInputError(f"SSOT B root must be an object: {self.external_assets_path}")

        if "items" in payload:
            if set(payload) != {"items"}:
                raise CanonicalLedgerInputError(
                    f"SSOT B legacy payload cannot mix items with monthly keys: {self.external_assets_path}"
                )
            return self._normalize_external_items(payload, "legacy/none"), "legacy/none"

        normalized_by_key: Dict[str, List[Dict[str, Any]]] = {}
        for key, entry in payload.items():
            if key != "default" and not _EXTERNAL_MONTH_KEY_RE.fullmatch(key):
                raise CanonicalLedgerInputError(
                    f"SSOT B invalid top-level key {key!r}: {self.external_assets_path}"
                )
            normalized_by_key[key] = self._normalize_external_items(entry, key)

        month_key = target_date[:7]
        if month_key in normalized_by_key:
            return normalized_by_key[month_key], month_key
        if "default" in normalized_by_key:
            return normalized_by_key["default"], "default"
        return [], "legacy/none"

    def _load_portfolio_basis(self, target_date: str) -> Tuple[Optional[str], Optional[float]]:
        if not os.path.exists(self.portfolio_basis_path):
            return None, None

        try:
            with open(self.portfolio_basis_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.error(f"[Guard] Failed to read v4 portfolio basis: {exc}")
            return None, None

        if not isinstance(payload, dict):
            return None, None

        month_key = target_date[:7]
        if month_key in payload:
            return month_key, self._normalize_total_acquisition_cost(payload[month_key])
        if "default" in payload:
            return "default", self._normalize_total_acquisition_cost(payload["default"])
        return None, None

    def _normalize_total_acquisition_cost(self, entry: Any) -> Optional[float]:
        source = entry if isinstance(entry, dict) else {}
        raw = source.get("total_acquisition_cost_jpy") if isinstance(source, dict) else None
        try:
            amount = float(raw)
        except (TypeError, ValueError):
            return None
        return amount if amount > 0 else None

    def _normalize_external_items(self, entry: Any, source_key: str) -> List[Dict[str, Any]]:
        if not isinstance(entry, dict) or not isinstance(entry.get("items"), list):
            raise CanonicalLedgerInputError(
                f"SSOT B {source_key!r} entry must contain an items array: {self.external_assets_path}"
            )
        source_items = entry["items"]

        items: List[Dict[str, Any]] = []
        for index, raw in enumerate(source_items):
            if not isinstance(raw, dict):
                raise CanonicalLedgerInputError(
                    f"SSOT B {source_key!r} item[{index}] must be an object: {self.external_assets_path}"
                )
            category = raw.get("category")
            name = raw.get("name", "")
            if not isinstance(category, str) or not category.strip():
                raise CanonicalLedgerInputError(
                    f"SSOT B {source_key!r} item[{index}] category must be a non-empty string"
                )
            if not isinstance(name, str):
                raise CanonicalLedgerInputError(
                    f"SSOT B {source_key!r} item[{index}] name must be a string"
                )
            try:
                raw_amount = raw.get("amount")
                if isinstance(raw_amount, bool):
                    raise ValueError("boolean amount")
                amount = float(raw_amount)
            except (TypeError, ValueError) as exc:
                raise CanonicalLedgerInputError(
                    f"SSOT B {source_key!r} item[{index}] amount must be numeric"
                ) from exc
            if not math.isfinite(amount) or amount < 0:
                raise CanonicalLedgerInputError(
                    f"SSOT B {source_key!r} item[{index}] amount must be finite and non-negative"
                )
            items.append({
                "category": category.strip(),
                "name": name.strip(),
                "amount": amount,
            })
        return items

    def _build_external_record(self, item: Dict[str, Any]) -> ShadowAssetRecord:
        category = item["category"] or "EXTERNAL_ASSET"
        return ShadowAssetRecord(
            source="ABSOLUTE_AMOUNT",
            name=item["name"] or category,
            asset_class=category,
            category=category,
            currency="JPY",
            current_value_jpy=item["amount"],
            pricing_status="STATIC",
        )

    def _build_market_record(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
        jp_market_date: str,
        fx_metrics: Optional[Dict[str, Any]],
        previous_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ShadowAssetRecord:
        expected_source_date = self._expected_source_date(
            asset,
            target_date,
            us_market_date,
            jp_market_date,
        )
        metrics = self._calculate_market_asset(
            asset,
            target_date,
            us_market_date,
            expected_source_date,
            fx_metrics,
            self._previous_ledger_price(asset, previous_records),
        )
        if metrics is None:
            return ShadowAssetRecord(
                source="MARKET_UNITS",
                name=asset["name"],
                asset_class=asset["asset_class"],
                category=asset["asset_class"],
                currency=asset["currency"],
                units=asset["units"],
                source_symbol=asset["source_symbol"],
                current_value_jpy=0,
                pricing_status="MISSING",
                warnings=["price unavailable from local collection history"],
            )

        source_date = metrics["date"]
        expected_fx_date = self._expected_fx_date(asset, target_date, us_market_date)
        fx_date = metrics.get("fx_date")
        is_price_stale = source_date < expected_source_date
        is_fx_stale = expected_fx_date is not None and (fx_date is None or fx_date < expected_fx_date)
        # Only check close status for exchange-traded assets on the expected price date.
        # MUTUAL_FUNDS are excluded (NAV is settled externally, not via market close).
        # Past dates always pass — historical prices are final regardless of execution time.
        asset_class = asset.get("asset_class", "")
        is_close_unconfirmed = (
            not is_price_stale
            and asset_class in CLOSE_CHECK_ASSET_CLASSES
            and not self._is_closed_fn(asset_class, asset.get("source_symbol", ""), expected_source_date)
        )
        warnings: List[str] = []
        if is_price_stale:
            inherited_date = self._inheritable_confirmed_date(
                asset,
                previous_records,
                expected_source_date,
                metrics["price"],
            )
            if inherited_date is not None:
                # 期待日の価格が取得元に無い場合、前営業日に確定した正本の値をその確定日の
                # 値として継承する (ADR-0002)。取得元が前回確定時と同一であることを
                # 価格一致で確認しているため、確定内容を遡って揺らさない。
                warnings.append(f"inherited confirmed value from canonical ledger {inherited_date}")
                source_date = inherited_date
                is_price_stale = False

        is_stale = is_price_stale or is_fx_stale or is_close_unconfirmed
        if is_fx_stale:
            warnings.append("fx rate stale or unavailable for expected market date")
        if is_close_unconfirmed:
            warnings.append("market session not yet closed; intraday price, not confirmed close")
        return ShadowAssetRecord(
            source="MARKET_UNITS",
            name=asset["name"],
            asset_class=asset["asset_class"],
            category=asset["asset_class"],
            currency=asset["currency"],
            units=asset["units"],
            price=metrics["price"],
            fx_rate=metrics["fx_rate"],
            source_symbol=asset["source_symbol"],
            source_date=source_date,
            current_value_jpy=metrics["current_value_jpy"],
            diff_val_jpy=metrics.get("diff_val_jpy"),
            diff_pct=metrics.get("diff_pct"),
            wtd_pct=metrics.get("wtd_pct"),
            mtd_pct=metrics.get("mtd_pct"),
            ytd_pct=metrics.get("ytd_pct"),
            pricing_status="STALE" if is_stale else "PRICED",
            warnings=warnings,
        )

    def _inheritable_confirmed_date(
        self,
        asset: Dict[str, Any],
        previous_records: Optional[Dict[str, Dict[str, Any]]],
        expected_source_date: str,
        current_price: Any,
    ) -> Optional[str]:
        """前営業日の正本から確定値を継承できる場合、その確定日を返す。

        継承は次を全て満たす場合に限る。
        - 前営業日の正本がその資産を `PRICED`（確定）として記録している
        - その正本の対象日が期待日以降である（期待日の状態を満たす確定である）
        - 取得元から算出した価格が正本の価格と一致する（確定時と同じ根拠である）

        価格一致を要件にすることで、取得元が更新された場合は継承せず通常判定へ戻す。
        """
        record = self._previous_ledger_record(asset, previous_records)
        if record is None or record.get("pricing_status") != "PRICED":
            return None
        confirmed_date = record.get("target_date")
        if not isinstance(confirmed_date, str) or confirmed_date < expected_source_date:
            return None
        price = record.get("price")
        if not isinstance(price, (int, float)) or not isinstance(current_price, (int, float)):
            return None
        if float(price) != float(current_price):
            return None
        return confirmed_date

    def _expected_source_date(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
        jp_market_date: str,
    ) -> str:
        asset_class = str(asset.get("asset_class") or "")
        currency = str(asset.get("currency") or "")
        if asset_class in _US_MARKET_DATE_CLASSES or currency == "USD":
            return us_market_date
        if asset_class in _JP_MARKET_DATE_CLASSES:
            return jp_market_date
        return target_date

    def _expected_fx_date(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
    ) -> Optional[str]:
        asset_class = str(asset.get("asset_class") or "")
        currency = str(asset.get("currency") or "")
        if currency == "USD" or asset_class == _COMMODITY_ASSET_CLASS:
            return us_market_date
        return None

    def _calculate_fx_metrics(
        self,
        assets: List[Dict[str, Any]],
        target_date: str,
    ) -> Optional[Dict[str, Any]]:
        fx_asset = next((asset for asset in assets if asset["asset_class"] == _FX_ASSET_CLASS), None)
        if fx_asset is None:
            return None
        return self._calculate_market_price(fx_asset, target_date)

    @staticmethod
    def _previous_ledger_record(
        asset: Dict[str, Any],
        previous_records: Optional[Dict[str, Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        # 正本である前営業日の確定台帳のレコードを引く。
        # 台帳は id に source_symbol を持ち、無い資産は name で記録される。
        if not previous_records:
            return None
        for key in (asset.get("source_symbol"), asset.get("name")):
            if not key:
                continue
            record = previous_records.get(str(key))
            if isinstance(record, dict):
                return record
        return None

    @staticmethod
    def _previous_ledger_price(
        asset: Dict[str, Any],
        previous_records: Optional[Dict[str, Dict[str, Any]]],
    ) -> Optional[float]:
        # 前営業日の確定台帳に記録された価格を DAY 比較の基準にする。
        record = UniversalIngester._previous_ledger_record(asset, previous_records)
        if record is None:
            return None
        price = record.get("price")
        if isinstance(price, (int, float)) and price > 0:
            return float(price)
        return None

    def _calculate_market_asset(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
        expected_source_date: str,
        fx_metrics: Optional[Dict[str, Any]],
        previous_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if asset["asset_class"] == "MUTUAL_FUNDS":
            return self._calculate_fund_value(asset, target_date, expected_source_date, previous_price)
        if asset["asset_class"] == _COMMODITY_ASSET_CLASS:
            return self._calculate_commodity_value(asset, target_date, us_market_date, fx_metrics, previous_price)
        return self._calculate_stock_value(asset, target_date, expected_source_date, fx_metrics, previous_price)

    def _calculate_fund_value(
        self,
        asset: Dict[str, Any],
        target_date: str,
        price_target_date: str,
        previous_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        df_up = self._history_rows_up(asset["name"], "基準日", price_target_date)
        if df_up is None or df_up.empty:
            return None
        latest = df_up.iloc[-1]
        prev = df_up.iloc[-2] if len(df_up) > 1 else latest
        nav = float(latest["基準価額"])
        prev_nav = previous_price if previous_price is not None else float(prev["基準価額"])
        current_value = (nav / 10000) * float(asset["units"])
        source_date_str = latest["基準日"].strftime("%Y-%m-%d")
        if source_date_str < target_date:
            diff_val = 0.0
            diff_pct = 0.0
        else:
            diff_val = ((nav - prev_nav) / 10000) * float(asset["units"])
            diff_pct = self._pct(nav, prev_nav)
        return {
            "date": source_date_str,
            "price": nav,
            "fx_rate": 1.0,
            "current_value_jpy": current_value,
            "diff_val_jpy": diff_val,
            "diff_pct": diff_pct,
            "wtd_pct": self._pct(nav, self._period_base_value(df_up, "基準日", "基準価額", latest["基準日"], "WEEK", nav)),
            "mtd_pct": self._pct(nav, self._period_base_value(df_up, "基準日", "基準価額", latest["基準日"], "MONTH", nav)),
            "ytd_pct": self._pct(nav, self._period_base_value(df_up, "基準日", "基準価額", latest["基準日"], "YEAR", nav)),
        }

    def _calculate_stock_value(
        self,
        asset: Dict[str, Any],
        target_date: str,
        price_target_date: str,
        fx_metrics: Optional[Dict[str, Any]],
        previous_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        # USD-denominated stocks use US market dates in the history CSV.
        # US Friday's close is first observed by the JP system on JP Monday
        # (the start of the new JP week), so the WTD origin must be anchored to
        # the JP target_date's week boundary rather than the US source date's.
        uses_us_market_date = asset["asset_class"] == _US_STOCK_ASSET_CLASS or asset["currency"] == "USD"
        week_origin = target_date if uses_us_market_date else None
        price_metrics = self._calculate_market_price(
            asset,
            price_target_date,
            week_origin=week_origin,
            previous_price=previous_price,
        )
        if price_metrics is None:
            return None

        fx_rate = 1.0
        if asset["currency"] == "USD":
            if fx_metrics is None:
                return None
            fx_rate = float(fx_metrics["price"])

        current_value = float(price_metrics["price"]) * float(asset["units"]) * fx_rate
        diff_val = float(price_metrics.get("diff_price", 0.0)) * float(asset["units"]) * fx_rate
        return {
            "date": price_metrics["date"],
            "price": price_metrics["price"],
            "fx_rate": fx_rate,
            "fx_date": fx_metrics.get("date") if asset["currency"] == "USD" and fx_metrics else None,
            "current_value_jpy": current_value,
            "diff_val_jpy": diff_val,
            "diff_pct": price_metrics.get("diff_pct"),
            "wtd_pct": price_metrics.get("wtd_pct"),
            "mtd_pct": price_metrics.get("mtd_pct"),
            "ytd_pct": price_metrics.get("ytd_pct"),
        }

    def _calculate_commodity_value(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
        fx_metrics: Optional[Dict[str, Any]],
        previous_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        # Commodities (Gold, Silver, Platinum) are US-market traded; same JP-observation
        # lag as USD stocks — anchor WTD to JP target_date week boundary.
        price_metrics = self._calculate_market_price(
            asset,
            us_market_date,
            week_origin=target_date,
            previous_price=previous_price,
        )
        if price_metrics is None or fx_metrics is None:
            return None

        price = float(price_metrics["price"])
        fx_rate = float(fx_metrics["price"])
        current_price_jpy = price * fx_rate / _COMMODITY_OZ_TO_G
        current_value = current_price_jpy * float(asset["units"])
        diff_val = float(price_metrics.get("diff_price", 0.0)) * fx_rate / _COMMODITY_OZ_TO_G * float(asset["units"])
        return {
            "date": price_metrics["date"],
            "price": price,
            "fx_rate": fx_rate,
            "fx_date": fx_metrics.get("date"),
            "current_value_jpy": current_value,
            "diff_val_jpy": diff_val,
            "diff_pct": price_metrics.get("diff_pct"),
            "wtd_pct": price_metrics.get("wtd_pct"),
            "mtd_pct": price_metrics.get("mtd_pct"),
            "ytd_pct": price_metrics.get("ytd_pct"),
        }

    def _calculate_market_price(
        self,
        asset: Dict[str, Any],
        target_date: str,
        week_origin: Optional[str] = None,
        previous_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        df_up = self._history_rows_up(asset["name"], "Date", target_date)
        if df_up is None or df_up.empty:
            return None
        latest = df_up.iloc[-1]
        prev = df_up.iloc[-2] if len(df_up) > 1 else latest
        close = float(latest["Close"])
        prev_close = previous_price if previous_price is not None else float(prev["Close"])
        return {
            "date": latest["Date"].strftime("%Y-%m-%d"),
            "price": close,
            "diff_price": close - prev_close,
            "diff_pct": self._pct(close, prev_close),
            "wtd_pct": self._pct(close, self._period_base_value(df_up, "Date", "Close", latest["Date"], "WEEK", close, week_origin)),
            "mtd_pct": self._pct(close, self._period_base_value(df_up, "Date", "Close", latest["Date"], "MONTH", close, week_origin)),
            "ytd_pct": self._pct(close, self._period_base_value(df_up, "Date", "Close", latest["Date"], "YEAR", close, week_origin)),
        }

    def _latest_history_row(self, asset_name: str, date_col: str, target_date: str) -> Optional[pd.Series]:
        df_up = self._history_rows_up(asset_name, date_col, target_date)
        if df_up is None or df_up.empty:
            return None
        return df_up.iloc[-1]

    def _history_rows_up(self, asset_name: str, date_col: str, target_date: str) -> Optional[pd.DataFrame]:
        hist_path = os.path.join(self.history_dir, f"{asset_name}.csv")
        if not os.path.exists(hist_path):
            return None

        try:
            df = pd.read_csv(hist_path, parse_dates=[date_col])
            df = df.sort_values(date_col).reset_index(drop=True)
            df_up = df[df[date_col] <= pd.to_datetime(target_date)]
            if df_up.empty:
                return None
            return df_up
        except Exception as exc:
            logger.warning(f"[Guard] Failed to read v4 history for {asset_name}: {exc}")
            return None

    def _period_base_value(
        self,
        df_up: pd.DataFrame,
        date_col: str,
        value_col: str,
        current_date: Any,
        period: str,
        fallback: float,
        week_origin: Optional[str] = None,
    ) -> float:
        if period == "WEEK":
            if week_origin is not None:
                # For assets with US market dates (USD stocks, commodities): the US Friday
                # close is first observed by the JP system on JP Monday (the start of the new
                # JP week), so it must NOT be used as the WTD base.  Anchor the lookback to
                # the JP target_date's week, then exclude the US Friday by using the JP
                # Friday of the previous JP week as the exclusive upper bound.
                #   JP Monday  = ref - ref.weekday() days  (weekday=0 on Monday)
                #   JP prev Fri = JP Monday - 3 days
                ref = pd.Timestamp(week_origin)
                jp_monday = ref - pd.Timedelta(days=ref.weekday())
                jp_prev_friday = jp_monday - pd.Timedelta(days=3)
                base_df = df_up[df_up[date_col] < jp_prev_friday]
            else:
                start_of_week = current_date - pd.Timedelta(days=current_date.weekday())
                base_df = df_up[df_up[date_col] < start_of_week]
        elif period == "MONTH":
            if week_origin is not None:
                # Same JP-observation lag as WEEK: the US close that the JP system
                # first observes on the JP period-start day is the period's first
                # data point, not its base.  Anchor the period start to the JP
                # target_date (week_origin) and exclude rows from the JP period
                # start onward by using the prior JP weekday as the exclusive bound.
                jp_period_start = pd.Timestamp(week_origin).replace(day=1)
                cut = self._prev_jp_weekday(jp_period_start)
                base_df = df_up[df_up[date_col] < cut]
            else:
                base_df = df_up[df_up[date_col] < current_date.replace(day=1)]
        elif period == "YEAR":
            if week_origin is not None:
                jp_period_start = pd.Timestamp(week_origin).replace(month=1, day=1)
                cut = self._prev_jp_weekday(jp_period_start)
                base_df = df_up[df_up[date_col] < cut]
            else:
                base_df = df_up[df_up[date_col] < current_date.replace(month=1, day=1)]
        else:
            base_df = pd.DataFrame()
        return float(base_df.iloc[-1][value_col]) if not base_df.empty else fallback

    @staticmethod
    def _prev_jp_weekday(day: pd.Timestamp) -> pd.Timestamp:
        # The most recent JP weekday (Mon–Fri) strictly before ``day``: step back
        # one day, then skip Saturday/Sunday back to the preceding Friday.
        cut = day - pd.Timedelta(days=1)
        while cut.weekday() >= 5:  # 5=Sat, 6=Sun
            cut = cut - pd.Timedelta(days=1)
        return cut

    def _pct(self, current: float, reference: float) -> float:
        return ((current - reference) / reference * 100.0) if reference else 0.0
