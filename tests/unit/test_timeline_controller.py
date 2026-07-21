from unittest.mock import MagicMock, patch

import pandas as pd

from src.lib.timeline_controller import TimelineController


def _timeline_with_jpx_sessions(*session_dates: str) -> tuple[TimelineController, MagicMock]:
    timeline = TimelineController()
    jpx = MagicMock()
    jpx.schedule.return_value = pd.DataFrame(index=pd.to_datetime(list(session_dates)))
    timeline._TimelineController__jpx = jpx
    return timeline, jpx


def test_determine_jp_market_date_keeps_jpx_session() -> None:
    timeline, _ = _timeline_with_jpx_sessions("2026-07-21")

    assert timeline.determine_jp_market_date("2026-07-21") == "2026-07-21"


def test_determine_jp_market_date_uses_previous_jpx_session_on_national_holiday() -> None:
    timeline, _ = _timeline_with_jpx_sessions("2026-07-17")

    assert timeline.determine_jp_market_date("2026-07-20") == "2026-07-17"


def test_determine_jp_market_date_uses_previous_jpx_session_on_exchange_holiday() -> None:
    timeline, _ = _timeline_with_jpx_sessions("2026-12-30")

    assert timeline.determine_jp_market_date("2026-12-31") == "2026-12-30"


def test_determine_jp_market_date_crosses_exchange_new_year_closure() -> None:
    timeline, _ = _timeline_with_jpx_sessions("2026-12-30")

    assert timeline.determine_jp_market_date("2027-01-01") == "2026-12-30"


def test_jp_market_date_fallback_includes_exchange_new_year_closure() -> None:
    timeline = TimelineController()
    timeline._TimelineController__jpx = None

    with patch("src.lib.timeline_controller.jpholiday.is_holiday", return_value=False):
        assert timeline.determine_jp_market_date("2026-12-31") == "2026-12-30"
        assert timeline.determine_jp_market_date("2027-01-03") == "2026-12-30"
