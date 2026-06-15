import pytest
from unittest.mock import MagicMock, patch

from src.lib.models import LedgerSummary

_SAMPLE_SUMMARY_DICT = {
    "total_assets_jpy": 10_000_000,
    "total_profit_loss_jpy": 500_000,
    "cash_position_jpy": 1_000_000,
    "total_diff_jpy": -50_000,
    "total_diff_pct": -0.5,
    "total_profit_loss_pct": 5.0,
    "invested_capital_jpy": 9_500_000,
    "capital_gain_jpy": 500_000,
    "class_totals": {},
    "total_wtd": "---",
    "total_mtd": "---",
    "total_ytd": "---",
    "exposure_jpy": 9_000_000,
    "iron_bank_jpy": 0,
    "safe_ratio_pct": 0.0,
    "damper_coef": 0.0,
    "weekly_high": 0,
    "weekly_low": 0,
}

_SAMPLE_LEDGER_DICT = {"summary": _SAMPLE_SUMMARY_DICT, "assets": []}

_SAMPLE_NARRATIVE = {
    "theme_title": "Test Weekly Chronicle",
    "chronicle_headline": "H",
    "chronicle_body": "B",
    "shield_review": "S",
}


@pytest.fixture
def harness():
    with patch("src.app.weekly_engine.Notifier")           as MockNotifier,    \
         patch("src.app.weekly_engine.LedgerRepository")   as MockRepo,        \
         patch("src.app.weekly_engine.KnowledgeManager")   as MockKnowledge,   \
         patch("src.app.weekly_engine.TimelineController") as MockTimeline,    \
         patch("src.app.weekly_engine.WeeklyCurator")      as MockCurator,     \
         patch("src.app.weekly_engine.WeeklyGuardRail")    as MockGuard,       \
         patch("src.app.weekly_engine.ChronicleRepository") as MockChronicle,  \
         patch("src.app.weekly_engine.SystemUtils")        as MockUtils:

        notifier   = MockNotifier.return_value
        repo       = MockRepo.return_value
        knowledge  = MockKnowledge.return_value
        timeline   = MockTimeline.return_value
        curator    = MockCurator.return_value
        guard      = MockGuard.return_value
        chronicle  = MockChronicle.return_value

        MockUtils.check_env_vars.return_value = True
        MockUtils.set_flag = MagicMock()
        timeline.get_target_date.return_value = "2026-03-09"
        timeline.get_previous_week_last_business_day.return_value = "2026-03-06"
        guard.should_proceed.return_value = True
        repo.load.return_value = _SAMPLE_LEDGER_DICT
        knowledge.extract_weekly_insights.return_value = []
        curator.generate_weekly_chronicle.return_value = _SAMPLE_NARRATIVE
        chronicle.exists.return_value = False
        chronicle.load.return_value = _SAMPLE_NARRATIVE
        notifier.weekly_report.return_value = True

        from src.app.weekly_engine import WeeklyEngine
        engine = WeeklyEngine()

        yield engine, {
            "notifier":  notifier,
            "repo":      repo,
            "knowledge": knowledge,
            "timeline":  timeline,
            "curator":   curator,
            "guard":     guard,
            "chronicle": chronicle,
            "utils":     MockUtils,
        }


class TestWeeklyEngineGuardPath:

    def test_format_test_skips_env_check(self, harness):
        engine, mocks = harness
        with patch.object(engine, "_WeeklyEngine__run_format_test") as mock_ft:
            engine.run(format_test=True)
        mock_ft.assert_called_once()
        mocks["utils"].check_env_vars.assert_not_called()

    def test_env_vars_missing_sends_operational_limit_alert(self, harness):
        engine, mocks = harness
        mocks["utils"].check_env_vars.return_value = False

        engine.run()

        mocks["notifier"].system_alert.assert_called_once()
        assert "OPERATIONAL_LIMIT_WEEKLY" in mocks["notifier"].system_alert.call_args[0]

    def test_guard_blocks_execution(self, harness):
        engine, mocks = harness
        mocks["guard"].should_proceed.return_value = False

        engine.run()

        mocks["notifier"].weekly_report.assert_not_called()

    def test_missing_ledger_terminates_silently(self, harness):
        engine, mocks = harness
        mocks["repo"].load.return_value = None

        engine.run()

        mocks["notifier"].weekly_report.assert_not_called()


class TestWeeklyEngineNarrativePath:

    def test_generates_chronicle_when_no_cache(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = False

        engine.run()

        mocks["curator"].generate_weekly_chronicle.assert_called_once()
        mocks["chronicle"].save.assert_called_once()

    def test_reuses_existing_chronicle_cache(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = True

        engine.run(reuse_context=True)

        mocks["curator"].generate_weekly_chronicle.assert_not_called()
        mocks["chronicle"].load.assert_called_once()

    def test_reuse_context_false_regenerates_even_if_cache_exists(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = True

        engine.run(reuse_context=False)

        mocks["curator"].generate_weekly_chronicle.assert_called_once()

    def test_dispatch_success_writes_lock(self, harness):
        engine, mocks = harness
        mocks["notifier"].weekly_report.return_value = True

        engine.run()

        mocks["utils"].set_flag.assert_called_once()

    def test_dispatch_failure_does_not_write_lock(self, harness):
        engine, mocks = harness
        mocks["notifier"].weekly_report.return_value = False

        engine.run()

        mocks["utils"].set_flag.assert_not_called()

    def test_unhandled_exception_triggers_crash_alert(self, harness):
        engine, mocks = harness
        mocks["repo"].load.side_effect = RuntimeError("boom")

        engine.run()

        mocks["notifier"].system_alert.assert_called_once()
        assert "OPERATIONAL_LIMIT_WEEKLY" in mocks["notifier"].system_alert.call_args[0]
