import datetime
import sys
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.modules.setdefault("yfinance", MagicMock())

from src.infra.market_data import MarketDataFetcher, is_market_closed

_JST = datetime.timezone(datetime.timedelta(hours=9))


def _now(h, m, date="2026-05-28"):
    dt = datetime.datetime.strptime(f"{date} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=_JST)


class TestIsMarketClosed:
    def _run(self, asset_class, symbol, target_date, now_jst, *, market_state=None):
        mock_info = MagicMock()
        mock_info.market_state = market_state
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info
        with patch("src.infra.market_data.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            return is_market_closed(asset_class, symbol, target_date=target_date, now_jst=now_jst)

    # --- past date ---
    def test_past_date_always_closed(self):
        # target_date before today → always True regardless of time or market_state
        result = self._run("JP_STOCK", "408A.T", "2026-04-20", _now(10, 0), market_state=None)
        assert result is True

    # --- yfinance marketState ---
    def test_market_state_closed_returns_true(self):
        result = self._run("JP_STOCK", "408A.T", "2026-05-28", _now(14, 0), market_state="CLOSED")
        assert result is True

    def test_market_state_post_returns_true(self):
        result = self._run("US_STOCK", "TSM", "2026-05-28", _now(7, 0), market_state="POST")
        assert result is True

    def test_market_state_regular_returns_false(self):
        result = self._run("JP_STOCK", "408A.T", "2026-05-28", _now(14, 0), market_state="REGULAR")
        assert result is False

    # --- JP fallback ---
    def test_jp_stock_before_close_is_open(self):
        result = self._run("JP_STOCK", "408A.T", "2026-05-28", _now(10, 0), market_state=None)
        assert result is False

    def test_jp_stock_after_close_is_closed(self):
        result = self._run("JP_STOCK", "408A.T", "2026-05-28", _now(15, 40), market_state=None)
        assert result is True

    # --- US fallback ---
    def test_us_stock_in_closed_window_is_closed(self):
        result = self._run("US_STOCK", "TSM", "2026-05-28", _now(7, 0), market_state=None)
        assert result is True

    def test_us_stock_before_close_window_is_open(self):
        # 05:00 JST — US session not yet closed
        result = self._run("US_STOCK", "TSM", "2026-05-28", _now(5, 0), market_state=None)
        assert result is False

    def test_us_stock_after_reopen_is_open(self):
        # 23:45 JST — US market has reopened
        result = self._run("US_STOCK", "TSM", "2026-05-28", _now(23, 45), market_state=None)
        assert result is False

    # --- fast_info exception fallback ---
    def test_fast_info_exception_falls_back_to_time_rule(self):
        with patch("src.infra.market_data.yf") as mock_yf:
            mock_yf.Ticker.side_effect = RuntimeError("network error")
            result = is_market_closed("JP_STOCK", "408A.T", target_date="2026-05-28", now_jst=_now(15, 40))
        assert result is True

_TICKERS = ["^GSPC", "^NDX", "^SOX", "^TNX", "JPY=X", "^VIX"]
_DATES   = pd.to_datetime(["2025-01-14", "2025-01-15"])


def _make_raw(prev: list, curr: list) -> pd.DataFrame:
    cols = pd.MultiIndex.from_tuples([("Close", t) for t in _TICKERS])
    return pd.DataFrame([prev, curr], index=_DATES, columns=cols)


def _run(mock_raw, date_str: str = "2025-01-15") -> str:
    with patch("src.infra.market_data.yf") as mock_yf:
        mock_yf.download.return_value = mock_raw
        return MarketDataFetcher().fetch_market_context(date_str)


class TestFetchMarketContextNormal:
    def test_positive_returns_formatted(self):
        prev = [5000.0, 20000.0, 4500.0, 4.50, 155.00, 18.00]
        curr = [5100.0, 20400.0, 4545.0, 4.55, 154.50, 16.50]
        result = _run(_make_raw(prev, curr))
        assert "S&P500: +2.00%" in result
        assert "NASDAQ100: +2.00%" in result
        assert "SOX: +1.00%" in result
        assert "米10年債: 4.55% (+0.05)" in result
        assert "USD/JPY: 154.50 (-0.32%)" in result
        assert "VIX: 16.50 (-1.50)" in result

    def test_negative_returns_formatted(self):
        prev = [5000.0, 20000.0, 4500.0, 4.50, 155.00, 18.00]
        curr = [4900.0, 19600.0, 4455.0, 4.45, 156.00, 22.00]
        result = _run(_make_raw(prev, curr))
        assert "S&P500: -2.00%" in result
        assert "NASDAQ100: -2.00%" in result
        assert "SOX: -1.00%" in result
        assert "米10年債: 4.45% (-0.05)" in result
        assert "USD/JPY: 156.00 (+0.65%)" in result
        assert "VIX: 22.00 (+4.00)" in result

    def test_no_change_formatted(self):
        vals = [5000.0, 20000.0, 4500.0, 4.50, 155.00, 18.00]
        result = _run(_make_raw(vals, vals))
        assert "S&P500: +0.00%" in result
        assert "米10年債: 4.50% (+0.00)" in result
        assert "USD/JPY: 155.00 (+0.00%)" in result
        assert "VIX: 18.00 (+0.00)" in result

    def test_pipe_separator_count(self):
        vals = [5000.0, 20000.0, 4500.0, 4.50, 155.00, 18.00]
        result = _run(_make_raw(vals, vals))
        assert result.count("|") == 5

    def test_holiday_lookback_uses_last_two_rows(self):
        extra_dates = pd.to_datetime(["2025-01-13", "2025-01-14", "2025-01-15"])
        cols = pd.MultiIndex.from_tuples([("Close", t) for t in _TICKERS])
        data = [
            [4800.0, 19000.0, 4300.0, 4.40, 157.00, 20.00],
            [5000.0, 20000.0, 4500.0, 4.50, 155.00, 18.00],
            [5100.0, 20400.0, 4545.0, 4.55, 154.50, 16.50],
        ]
        raw = pd.DataFrame(data, index=extra_dates, columns=cols)
        result = _run(raw)
        assert "S&P500: +2.00%" in result


class TestFetchMarketContextFallback:
    def test_empty_dataframe_returns_fallback(self):
        result = _run(pd.DataFrame())
        assert result == "(Market data unavailable)"

    def test_single_row_returns_fallback(self):
        cols = pd.MultiIndex.from_tuples([("Close", t) for t in _TICKERS])
        raw = pd.DataFrame([[5000.0, 20000.0, 4500.0, 4.50, 155.00, 18.00]], index=_DATES[:1], columns=cols)
        result = _run(raw)
        assert result == "(Market data unavailable)"

    def test_yfinance_exception_returns_fallback(self):
        with patch("src.infra.market_data.yf") as mock_yf:
            mock_yf.download.side_effect = RuntimeError("network error")
            result = MarketDataFetcher().fetch_market_context("2025-01-15")
        assert result == "(Market data unavailable)"

    def test_all_nan_rows_dropped_returns_fallback(self):
        import numpy as np
        cols = pd.MultiIndex.from_tuples([("Close", t) for t in _TICKERS])
        raw = pd.DataFrame(
            [[float("nan")] * 6, [float("nan")] * 6],
            index=_DATES,
            columns=cols,
        )
        result = _run(raw)
        assert result == "(Market data unavailable)"
