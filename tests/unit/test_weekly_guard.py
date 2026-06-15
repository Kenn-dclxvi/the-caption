from unittest.mock import MagicMock, patch

from src.domain.weekly_guard import WeeklyGuardRail


def _build_guard():
    timeline = MagicMock()
    repo = MagicMock()
    timeline.get_previous_week_last_business_day.return_value = "2026-03-06"
    repo.load.return_value = {"meta": {"integrity_status": "VERIFIED"}}
    return WeeklyGuardRail(timeline, repo), timeline, repo


class TestWeeklyGuardRail:

    def test_force_send_bypasses_guard_checks(self):
        guard, timeline, repo = _build_guard()

        assert guard.should_proceed("2026-03-09", True) is True
        timeline.get_previous_week_last_business_day.assert_not_called()
        repo.load.assert_not_called()

    def test_blocks_when_week_already_sent(self):
        guard, _, repo = _build_guard()

        with patch("src.domain.weekly_guard.SystemUtils.get_flag", return_value="2026-W10"):
            assert guard.should_proceed("2026-03-09", False) is False

        repo.load.assert_not_called()

    def test_blocks_when_ledger_missing(self):
        guard, _, repo = _build_guard()
        repo.load.return_value = None

        with patch("src.domain.weekly_guard.SystemUtils.get_flag", return_value=""):
            assert guard.should_proceed("2026-03-09", False) is False

    def test_blocks_when_ledger_not_verified(self):
        guard, _, repo = _build_guard()
        repo.load.return_value = {"meta": {"integrity_status": "PENDING"}}

        with patch("src.domain.weekly_guard.SystemUtils.get_flag", return_value=""):
            assert guard.should_proceed("2026-03-09", False) is False

    def test_proceeds_when_not_sent_and_ledger_verified(self):
        guard, _, _ = _build_guard()

        with patch("src.domain.weekly_guard.SystemUtils.get_flag", return_value=""):
            assert guard.should_proceed("2026-03-09", False) is True
