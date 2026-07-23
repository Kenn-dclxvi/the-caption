from src.lib.timeline_controller import TimelineController


def test_real_jpx_calendar_resolves_exchange_new_year_closure() -> None:
    timeline = TimelineController()
    jpx = timeline._TimelineController__jpx

    assert jpx is not None
    assert jpx.name == "JPX"

    sessions = jpx.schedule(
        start_date="2026-12-30",
        end_date="2027-01-04",
    ).index.strftime("%Y-%m-%d").tolist()
    assert sessions == ["2026-12-30", "2027-01-04"]

    assert timeline.determine_jp_market_date("2026-12-31") == "2026-12-30"
    assert timeline.determine_jp_market_date("2027-01-01") == "2026-12-30"
