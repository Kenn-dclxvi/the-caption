import datetime
import math
from typing import Final, Optional

import pandas as pd
import yfinance as yf

from src.lib.logger import setup_logger

logger = setup_logger(__name__)

_JST = datetime.timezone(datetime.timedelta(hours=9))

# JP market closes at 15:30 JST; allow 5-min buffer for settlement
_JP_CLOSE_TIME = datetime.time(15, 35)
# US market (ET 16:00 = JST 06:00 next day); 06:30 JST gives a 30-min buffer
_US_CLOSE_TIME_JST = datetime.time(6, 30)
# US market reopens around 23:30 JST (ET 09:30)
_US_OPEN_TIME_JST = datetime.time(23, 30)

CLOSE_CHECK_ASSET_CLASSES: Final[frozenset] = frozenset({"JP_STOCK", "US_STOCK", "COMMODITIES", "FX"})


def is_market_closed(
    asset_class: str,
    symbol: str,
    target_date: Optional[str] = None,
    now_jst: Optional[datetime.datetime] = None,
) -> bool:
    """Return True if the market session for target_date has ended and closing price is final.

    For past dates (target_date < today JST) this always returns True — historical prices
    are always final regardless of current wall-clock time.
    Only JP_STOCK / US_STOCK / COMMODITIES / FX are subject to intraday checks;
    other asset classes (e.g. MUTUAL_FUNDS) are not handled here and callers must skip them.
    """
    if now_jst is None:
        now_jst = datetime.datetime.now(_JST)

    # Past dates are always settled — skip live checks entirely
    if target_date is not None:
        today_str = now_jst.strftime("%Y-%m-%d")
        if target_date < today_str:
            return True

    # Try yfinance marketState first
    try:
        info = yf.Ticker(symbol).fast_info
        market_state = getattr(info, "market_state", None)
        if market_state is not None:
            # CLOSED / POST / POSTPOST = session ended, price is final
            return market_state in ("CLOSED", "POST", "POSTPOST")
        logger.debug(f"[market_data] market_state unavailable for {symbol}; fallback to time rule")
    except Exception:
        logger.debug(f"[market_data] fast_info failed for {symbol}; fallback to time rule")

    # Fallback: time-based check
    now_time = now_jst.time()
    asset_class_upper = (asset_class or "").upper()
    if asset_class_upper in ("US_STOCK", "COMMODITIES", "FX"):
        # Closed during the window after US session ends and before it reopens
        return now_time >= _US_CLOSE_TIME_JST and now_time < _US_OPEN_TIME_JST
    else:
        # JP market: closed after 15:35 JST
        return now_time >= _JP_CLOSE_TIME


class MarketDataFetcher:
    __REV: Final[str] = "Rev. 6"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing MarketDataFetcher")

    @staticmethod
    def __safe(v) -> float | None:
        try:
            f = float(v)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def __pct(c, p) -> str:
        cv, pv = MarketDataFetcher.__safe(c), MarketDataFetcher.__safe(p)  # type: ignore[attr-defined]
        if cv is None or pv is None or pv == 0.0:
            return "N/A"
        return f"{(cv - pv) / pv * 100.0:+.2f}%"

    @staticmethod
    def __val(v, fmt: str) -> str:
        fv = MarketDataFetcher.__safe(v)  # type: ignore[attr-defined]
        return "N/A" if fv is None else format(fv, fmt)

    @staticmethod
    def __diff(c, p, fmt: str) -> str:
        cv, pv = MarketDataFetcher.__safe(c), MarketDataFetcher.__safe(p)  # type: ignore[attr-defined]
        if cv is None or pv is None:
            return "N/A"
        return format(cv - pv, fmt)

    def fetch_market_context(self, us_date_str: str) -> str:
        logger.info(f"[Acquisition] fetch_market_context: {us_date_str}")
        try:
            end_dt   = datetime.datetime.strptime(us_date_str, "%Y-%m-%d") + datetime.timedelta(days=1)
            start_dt = end_dt - datetime.timedelta(days=14)

            tickers = ["^GSPC", "^NDX", "^SOX", "^TNX", "JPY=X", "^VIX"]
            raw = yf.download(
                tickers,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                progress=False,
            )

            if raw.empty:
                logger.warning("[Guard] yfinance returned empty DataFrame")
                return "(Market data unavailable)"

            close = raw["Close"].ffill().dropna(how="all")
            if close.index.tz is not None:
                close.index = close.index.tz_convert(None)
            close.index = close.index.normalize()
            close = close.groupby(close.index).last()
            target_dt = pd.to_datetime(us_date_str)
            close = close[close.index <= target_dt]

            if not close.empty:
                latest_available = close.index[-1]
                days_gap = (target_dt - latest_available).days
                if days_gap > 2:
                    logger.warning(
                        f"[Guard] Market data gap detected: target={us_date_str}, "
                        f"latest_available={latest_available.strftime('%Y-%m-%d')}, gap={days_gap}d"
                    )

            if len(close) < 2:
                logger.warning(f"[Guard] Insufficient trading rows: {len(close)}")
                return "(Market data unavailable)"

            prev = close.iloc[-2]
            curr = close.iloc[-1]

            sp500_pct   = self.__pct(curr["^GSPC"], prev["^GSPC"])
            ndx_pct     = self.__pct(curr["^NDX"],  prev["^NDX"])
            sox_pct     = self.__pct(curr["^SOX"],  prev["^SOX"])
            tnx_curr    = self.__val(curr["^TNX"],  ".2f")
            tnx_diff    = self.__diff(curr["^TNX"],  prev["^TNX"],  "+.2f")
            usdjpy_curr = self.__val(curr["JPY=X"], ".2f")
            usdjpy_pct  = self.__pct(curr["JPY=X"], prev["JPY=X"])
            vix_curr    = self.__val(curr["^VIX"],  ".2f")
            vix_diff    = self.__diff(curr["^VIX"],  prev["^VIX"],  "+.2f")

            result = (
                f"S&P500: {sp500_pct} | "
                f"NASDAQ100: {ndx_pct} | "
                f"SOX: {sox_pct} | "
                f"米10年債: {tnx_curr}% ({tnx_diff}) | "
                f"USD/JPY: {usdjpy_curr} ({usdjpy_pct}) | "
                f"VIX: {vix_curr} ({vix_diff})"
            )

            logger.info(f"[Outcome] Market context acquired: {result}")
            return result

        except Exception as e:
            logger.error(f"[Outcome] fetch_market_context failed: {e}")
            return "(Market data unavailable)"
