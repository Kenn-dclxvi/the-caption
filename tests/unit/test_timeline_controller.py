import datetime
from unittest.mock import patch

from src.lib.timeline_controller import TimelineController


def test_determine_jp_market_date_keeps_business_day() -> None:
    with patch("src.lib.timeline_controller.jpholiday.is_holiday", return_value=False):
        timeline = TimelineController()

        assert timeline.determine_jp_market_date("2026-07-21") == "2026-07-21"


def test_determine_jp_market_date_rolls_holiday_and_weekend_back() -> None:
    marine_day = datetime.date(2026, 7, 20)

    with patch(
        "src.lib.timeline_controller.jpholiday.is_holiday",
        side_effect=lambda value: value.date() == marine_day,
    ):
        timeline = TimelineController()

        assert timeline.determine_jp_market_date("2026-07-20") == "2026-07-17"
