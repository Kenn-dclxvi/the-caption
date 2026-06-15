import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, Final, List, Optional, Set

import pandas as pd
import yfinance as yf

from src.config.settings import DIR_COLLECTION_HISTORY
from src.domain.market_units_snapshot import MARKET_UNITS_CSV
from src.lib.logger import setup_logger

logger = setup_logger(__name__)

_MARKET_UNITS_CSV: Final[str] = MARKET_UNITS_CSV


class CollectionHistoryUpdater:
    __REV: Final[str] = "Rev. 1"

    def __init__(
        self,
        funds_csv_path: Optional[str] = None,
        history_dir: Optional[str] = None,
    ) -> None:
        logger.info(f"[{self.__REV}] Initializing CollectionHistoryUpdater")
        self.funds_csv_path = funds_csv_path or _MARKET_UNITS_CSV
        self.history_dir = history_dir or DIR_COLLECTION_HISTORY

    def refresh(
        self,
        target_date: Optional[str] = None,
        us_market_date: Optional[str] = None,
        only_assets: Optional[Set[str]] = None,
        end_date: Optional[str] = None,
    ) -> None:
        assets = self._load_fund_config()
        if not assets:
            logger.warning("[Guard] No collection assets loaded for v4 history refresh.")
            return
        selected_assets = assets
        if only_assets:
            selected_assets = [asset for asset in assets if asset["name"] in only_assets]
            if any(self._requires_fx(asset) for asset in selected_assets):
                fx_assets = [asset for asset in assets if asset["asset_class"] == "FX"]
                if fx_assets:
                    selected_names = {asset["name"] for asset in selected_assets}
                    for fx_asset in fx_assets:
                        if fx_asset["name"] not in selected_names:
                            selected_assets.append(fx_asset)
            logger.info(f"[Guard] V4 selective refresh: {len(selected_assets)}/{len(assets)} assets")
        for asset in selected_assets:
            self._fetch_asset(
                asset,
                target_date=target_date,
                us_market_date=us_market_date,
                end_date=end_date,
            )

    def fx_asset_names(self) -> Set[str]:
        assets = self._load_fund_config()
        return {asset["name"] for asset in assets if asset["asset_class"] == "FX"}

    def _load_fund_config(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []

        def _clean(value: Any, default: str = "") -> str:
            return str(value or default).strip()

        try:
            with open(self.funds_csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        name = _clean(row.get("name"))
                        asset_class = _clean(row.get("asset_class"), "MUTUAL_FUNDS") or "MUTUAL_FUNDS"
                        assets.append({
                            "name": name,
                            "asset_class": asset_class,
                            "source_symbol": _clean(row.get("source_symbol"), name) or name,
                            "csv_url": _clean(row.get("csv_url")),
                        })
                    except (KeyError, TypeError, ValueError, AttributeError) as row_err:
                        logger.warning(f"[Guard] Skipping malformed collection row: {row_err}")
        except FileNotFoundError:
            logger.warning(f"[Guard] Collection fund config missing: {self.funds_csv_path}")
        except Exception as exc:
            logger.error(f"[Guard] Failed to read collection fund config: {exc}")
        return assets

    def _fetch_asset(
        self,
        asset: Dict[str, Any],
        target_date: Optional[str] = None,
        us_market_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> None:
        if asset["asset_class"] == "MUTUAL_FUNDS":
            self._fetch_fund_history(asset)
            return
        market_end_date = self._resolve_market_end_date(
            asset,
            target_date=target_date,
            us_market_date=us_market_date,
            end_date=end_date,
        )
        self._fetch_market_history(asset, end_date=market_end_date)

    def _resolve_market_end_date(
        self,
        asset: Dict[str, Any],
        target_date: Optional[str],
        us_market_date: Optional[str],
        end_date: Optional[str],
    ) -> Optional[str]:
        # Backward compatibility for legacy callers.
        if end_date is not None:
            return end_date

        asset_class = str(asset.get("asset_class") or "")
        if asset_class == "JP_STOCK":
            return target_date
        if asset_class in {"US_STOCK", "COMMODITIES", "FX"}:
            return us_market_date or target_date
        return target_date

    def _requires_fx(self, asset: Dict[str, Any]) -> bool:
        asset_class = str(asset.get("asset_class") or "")
        return asset_class in {"US_STOCK", "COMMODITIES"}

    def _fetch_fund_history(self, asset: Dict[str, Any]) -> None:
        if not asset["csv_url"]:
            logger.warning(f"[Guard] CSV URL missing for collection asset: {asset['name']}")
            return
        try:
            req = urllib.request.Request(asset["csv_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_bytes: bytes = resp.read()
            self._save_fund_history(asset["name"], raw_bytes)
            logger.info(f"[Outcome] V4 collection history fetched: {asset['name']}")
        except Exception as exc:
            logger.error(f"[Guard] V4 collection fetch failed for {asset['name']}: {exc}")

    def _fetch_market_history(self, asset: Dict[str, Any], end_date: Optional[str] = None) -> None:
        try:
            kwargs: Dict[str, Any] = {"period": "2y", "progress": False}
            if end_date is not None:
                # yfinance の end は exclusive（当日を含まない）のため +1日する
                exclusive_end = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
                kwargs["end"] = exclusive_end
            raw = yf.download(asset["source_symbol"], **kwargs)
            if raw.empty:
                logger.warning(f"[Guard] No market history returned for: {asset['name']}")
                hist = pd.DataFrame(columns=["Date", "Close"])
            else:
                close = raw.get("Close")
                if close is None:
                    logger.warning(f"[Guard] Close column missing for: {asset['name']}")
                    hist = pd.DataFrame(columns=["Date", "Close"])
                elif isinstance(close, pd.DataFrame) and close.empty:
                    logger.warning(f"[Guard] No close rows returned for: {asset['name']}")
                    hist = pd.DataFrame(columns=["Date", "Close"])
                else:
                    if isinstance(close, pd.DataFrame):
                        close = close.iloc[:, 0]

                    hist = close.to_frame(name="Close").copy()
                    hist.index = pd.to_datetime(hist.index).tz_localize(None)
                    hist.index = hist.index.normalize()
                    hist = hist.rename_axis("Date").reset_index()
                    hist["Close"] = pd.to_numeric(hist["Close"], errors="coerce")
                    hist = hist.dropna(subset=["Date", "Close"])
            hist = self._maybe_merge_alpha_vantage_daily_close(asset, hist, end_date)
            if hist.empty:
                logger.warning(f"[Guard] No valid market rows for: {asset['name']}")
                return

            hist_path = os.path.join(self.history_dir, f"{asset['name']}.csv")
            if os.path.exists(hist_path):
                old_df = pd.read_csv(hist_path, parse_dates=["Date"])
                hist = pd.concat([old_df, hist]).drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
            os.makedirs(self.history_dir, exist_ok=True)
            hist.to_csv(hist_path, index=False)
            logger.info(f"[Outcome] V4 collection market history fetched: {asset['name']}")
        except Exception as exc:
            logger.error(f"[Guard] V4 collection market fetch failed for {asset['name']}: {exc}")

    def _maybe_merge_alpha_vantage_daily_close(
        self,
        asset: Dict[str, Any],
        hist: pd.DataFrame,
        end_date: Optional[str],
    ) -> pd.DataFrame:
        if asset.get("asset_class") != "US_STOCK" or end_date is None:
            return hist

        expected_date = pd.Timestamp(date.fromisoformat(end_date)).normalize()
        has_expected_close = False
        latest_date: Optional[pd.Timestamp] = None
        if not hist.empty:
            dates = pd.to_datetime(hist["Date"]).dt.normalize()
            has_expected_close = bool(((dates == expected_date) & hist["Close"].notna()).any())
            latest_date = dates.max()

        if has_expected_close and latest_date is not None and latest_date >= expected_date:
            return hist

        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            return hist

        close = self._fetch_alpha_vantage_daily_close(asset, end_date, api_key)
        if close is None:
            return hist

        fallback_row = pd.DataFrame({"Date": [expected_date], "Close": [close]})
        return (
            pd.concat([hist, fallback_row], ignore_index=True)
            .drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
        )

    def _fetch_alpha_vantage_daily_close(
        self,
        asset: Dict[str, Any],
        end_date: str,
        api_key: str,
    ) -> Optional[float]:
        try:
            params = urllib.parse.urlencode({
                "function": "TIME_SERIES_DAILY",
                "symbol": asset["source_symbol"],
                "outputsize": "compact",
                "apikey": api_key,
            })
            req = urllib.request.Request(
                f"https://www.alphavantage.co/query?{params}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_bytes: bytes = resp.read()
            payload = json.loads(raw_bytes.decode("utf-8"))
            if not isinstance(payload, dict):
                logger.warning(f"[Guard] Alpha Vantage response was not an object for: {asset['name']}")
                return None
            for error_key in ("Error Message", "Note", "Information"):
                if error_key in payload:
                    logger.warning(f"[Guard] Alpha Vantage API message for {asset['name']}: {payload[error_key]}")
                    return None
            daily = payload.get("Time Series (Daily)")
            if not isinstance(daily, dict):
                logger.warning(f"[Guard] Alpha Vantage daily series missing for: {asset['name']}")
                return None
            row = daily.get(end_date)
            if not isinstance(row, dict):
                logger.warning(f"[Guard] Alpha Vantage close missing for {asset['name']} on {end_date}")
                return None
            close = float(str(row.get("4. close", "")).strip())
            logger.info(f"[Outcome] Alpha Vantage fallback fetched: {asset['name']} {end_date}")
            return close
        except Exception as exc:
            logger.warning(f"[Guard] Alpha Vantage fallback failed for {asset['name']}: {exc}")
            return None

    def _save_fund_history(self, fund_name: str, raw_bytes: bytes) -> None:
        new_df = self._parse_nav_bytes(raw_bytes)
        if new_df is None or new_df.empty:
            logger.warning(f"[Guard] Could not parse collection CSV for: {fund_name}")
            return

        hist_path = os.path.join(self.history_dir, f"{fund_name}.csv")
        try:
            if os.path.exists(hist_path):
                old_df = pd.read_csv(hist_path, parse_dates=["基準日"])
                merged = pd.concat([old_df, new_df]).drop_duplicates(subset=["基準日"]).sort_values("基準日")
            else:
                merged = new_df.sort_values("基準日")
            os.makedirs(self.history_dir, exist_ok=True)
            merged.to_csv(hist_path, index=False)
        except Exception as exc:
            logger.error(f"[Guard] Failed to save collection history for {fund_name}: {exc}")

    def _parse_nav_bytes(self, raw_bytes: bytes) -> Optional[pd.DataFrame]:
        for encoding in ["utf-8", "shift-jis", "cp932"]:
            for skip in [0, 1]:
                try:
                    text = raw_bytes.decode(encoding)
                    df = pd.read_csv(io.StringIO(text), on_bad_lines="skip", skiprows=skip, dtype=str)
                    date_col = next((c for c in df.columns if "基準日" in c), None)
                    nav_col = next((c for c in df.columns if "基準価額" in c), None)
                    if date_col is None or nav_col is None:
                        continue

                    raw_dates = df[date_col].str.strip()
                    parsed = pd.to_datetime(raw_dates, format="%Y%m%d", errors="coerce")
                    if parsed.isna().all():
                        parsed = pd.to_datetime(raw_dates, format="%Y/%m/%d", errors="coerce")
                    if parsed.isna().all():
                        continue

                    df["基準日"] = parsed
                    df["基準価額"] = pd.to_numeric(
                        df[nav_col].str.replace(",", "", regex=False),
                        errors="coerce",
                    )
                    df = df.dropna(subset=["基準日", "基準価額"])
                    if not df.empty:
                        return df[["基準日", "基準価額"]].reset_index(drop=True)
                except Exception:
                    continue
        logger.error("[Guard] All encoding attempts failed for collection CSV parse.")
        return None
