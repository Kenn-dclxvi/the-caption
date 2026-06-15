import json
import os
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
from src.lib.timeline_controller import TimelineController

logger = setup_logger(__name__)

_FX_ASSET_CLASS: Final[str] = "FX"
_US_STOCK_ASSET_CLASS: Final[str] = "US_STOCK"
_COMMODITY_ASSET_CLASS: Final[str] = "COMMODITIES"
_COMMODITY_OZ_TO_G: Final[float] = 31.1034768
_US_MARKET_DATE_CLASSES: Final[set[str]] = {"US_STOCK", "COMMODITIES", "FX"}


class UniversalIngester:
    __REV: Final[str] = "Rev. 1"

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
    ) -> ShadowLedger:
        active_date = target_date or datetime.now().strftime("%Y-%m-%d")
        units_resolution = self._resolve_market_units(active_date, units_mode, allow_live_csv_in_strict)
        market_assets = units_resolution["items"]
        external_items, active_key = self._load_external_assets(active_date)
        basis_key, total_acquisition_cost = self._load_portfolio_basis(active_date)
        us_market_date = self._resolve_us_market_date(active_date)

        fx_metrics = self._calculate_fx_metrics(market_assets, us_market_date)
        records: List[ShadowAssetRecord] = []
        for asset in market_assets:
            if asset["asset_class"] == _FX_ASSET_CLASS:
                continue
            records.append(self._build_market_record(asset, active_date, us_market_date, fx_metrics))

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

    def run(
        self,
        target_date: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> ShadowLedger:
        ledger = self.build_shadow_ledger(target_date)
        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(ledger.model_dump(), f, ensure_ascii=False, indent=2)
                f.write("\n")
        return ledger

    def _resolve_market_units(
        self,
        target_date: str,
        units_mode: Literal["daily", "strict"],
        allow_live_csv_in_strict: bool,
    ) -> UnitsResolution:
        if units_mode not in {"daily", "strict"}:
            raise ValueError(f"units_mode must be 'daily' or 'strict', got: {units_mode}")

        snapshot = snapshot_path(target_date, self.units_snapshot_dir)
        if os.path.exists(snapshot):
            try:
                return {
                    "items": load_units_snapshot(snapshot, target_date, self.ssot_a_path),
                    "source": {
                        "type": "SNAPSHOT",
                        "path": snapshot,
                        "snapshot_target_date": target_date,
                    },
                }
            except MarketUnitsSnapshotError as exc:
                if units_mode == "strict":
                    raise
                logger.warning(f"[Guard] Invalid market units snapshot; falling back to live CSV: {snapshot} ({exc})")
                return self._load_live_market_units()

        if units_mode == "strict" and not allow_live_csv_in_strict:
            raise MarketUnitsSnapshotError(f"market units snapshot missing: {snapshot}")

        logger.warning(f"[Guard] Market units snapshot missing; falling back to live CSV: {snapshot}")
        return self._load_live_market_units()

    def _load_live_market_units(self) -> UnitsResolution:
        return {
            "items": self._load_fund_config(),
            "source": {
                "type": "LIVE_CSV",
                "path": self.ssot_a_path,
            },
        }

    def _load_fund_config(self) -> List[Dict[str, Any]]:
        try:
            funds = load_market_units_csv(self.ssot_a_path)
            for row in funds:
                row["units"] = float(row["units"])
            return funds
        except FileNotFoundError:
            logger.warning(f"[Guard] v4 market units config missing: {self.ssot_a_path}")
        except Exception as exc:
            logger.error(f"[Guard] Failed to read v4 market units config: {exc}")
        return []

    def _load_external_assets(self, target_date: str) -> Tuple[List[Dict[str, Any]], str]:
        if not os.path.exists(self.external_assets_path):
            return [], "missing"

        try:
            with open(self.external_assets_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.error(f"[Guard] Failed to read v4 external assets: {exc}")
            return [], "invalid"

        if not isinstance(payload, dict):
            return [], "invalid"

        month_key = target_date[:7]
        if month_key in payload:
            return self._normalize_external_items(payload[month_key]), month_key
        if "default" in payload:
            return self._normalize_external_items(payload["default"]), "default"
        return self._normalize_external_items(payload), "legacy/none"

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

    def _normalize_external_items(self, entry: Any) -> List[Dict[str, Any]]:
        if isinstance(entry, dict) and isinstance(entry.get("items"), list):
            source_items = entry["items"]
        else:
            source_items = []

        items: List[Dict[str, Any]] = []
        for raw in source_items:
            item = raw if isinstance(raw, dict) else {}
            try:
                amount = float(item.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0.0
            items.append({
                "category": str(item.get("category", "") or "").strip(),
                "name": str(item.get("name", "") or "").strip(),
                "amount": amount if amount > 0 else 0.0,
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
        fx_metrics: Optional[Dict[str, Any]],
    ) -> ShadowAssetRecord:
        metrics = self._calculate_market_asset(asset, target_date, us_market_date, fx_metrics)
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
        expected_source_date = self._expected_source_date(asset, target_date, us_market_date)
        expected_fx_date = self._expected_fx_date(asset, target_date, us_market_date)
        fx_date = metrics.get("fx_date")
        is_price_stale = source_date < expected_source_date
        is_fx_stale = expected_fx_date is not None and (fx_date is None or fx_date < expected_fx_date)
        # Only check close status for exchange-traded assets on the current target date.
        # MUTUAL_FUNDS are excluded (NAV is settled externally, not via market close).
        # Past dates always pass — historical prices are final regardless of execution time.
        asset_class = asset.get("asset_class", "")
        is_close_unconfirmed = (
            not is_price_stale
            and asset_class in CLOSE_CHECK_ASSET_CLASSES
            and not self._is_closed_fn(asset_class, asset.get("source_symbol", ""), target_date)
        )
        is_stale = is_price_stale or is_fx_stale or is_close_unconfirmed
        warnings: List[str] = []
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

    def _expected_source_date(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
    ) -> str:
        asset_class = str(asset.get("asset_class") or "")
        currency = str(asset.get("currency") or "")
        if asset_class in _US_MARKET_DATE_CLASSES or currency == "USD":
            return us_market_date
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

    def _calculate_market_asset(
        self,
        asset: Dict[str, Any],
        target_date: str,
        us_market_date: str,
        fx_metrics: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if asset["asset_class"] == "MUTUAL_FUNDS":
            return self._calculate_fund_value(asset, target_date)
        if asset["asset_class"] == _COMMODITY_ASSET_CLASS:
            return self._calculate_commodity_value(asset, target_date, us_market_date, fx_metrics)
        return self._calculate_stock_value(asset, target_date, us_market_date, fx_metrics)

    def _calculate_fund_value(self, asset: Dict[str, Any], target_date: str) -> Optional[Dict[str, Any]]:
        df_up = self._history_rows_up(asset["name"], "基準日", target_date)
        if df_up is None or df_up.empty:
            return None
        latest = df_up.iloc[-1]
        prev = df_up.iloc[-2] if len(df_up) > 1 else latest
        nav = float(latest["基準価額"])
        prev_nav = float(prev["基準価額"])
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
        us_market_date: str,
        fx_metrics: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        # USD-denominated stocks use US market dates in the history CSV.
        # US Friday's close is first observed by the JP system on JP Monday
        # (the start of the new JP week), so the WTD origin must be anchored to
        # the JP target_date's week boundary rather than the US source date's.
        uses_us_market_date = asset["asset_class"] == _US_STOCK_ASSET_CLASS or asset["currency"] == "USD"
        price_target_date = us_market_date if uses_us_market_date else target_date
        week_origin = target_date if uses_us_market_date else None
        price_metrics = self._calculate_market_price(asset, price_target_date, week_origin=week_origin)
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
    ) -> Optional[Dict[str, Any]]:
        # Commodities (Gold, Silver, Platinum) are US-market traded; same JP-observation
        # lag as USD stocks — anchor WTD to JP target_date week boundary.
        price_metrics = self._calculate_market_price(asset, us_market_date, week_origin=target_date)
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
    ) -> Optional[Dict[str, Any]]:
        df_up = self._history_rows_up(asset["name"], "Date", target_date)
        if df_up is None or df_up.empty:
            return None
        latest = df_up.iloc[-1]
        prev = df_up.iloc[-2] if len(df_up) > 1 else latest
        close = float(latest["Close"])
        prev_close = float(prev["Close"])
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
