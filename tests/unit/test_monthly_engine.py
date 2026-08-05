import pytest
from unittest.mock import MagicMock, patch

from src.lib.models import LedgerSummary
from src.app.renderer.view_models import SummaryViewModel

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
    "theme_title": "Test Chronicle",
    "chronicle_headline": "H",
    "chronicle_body": "B",
    "shield_review": "S",
}


def _daily_metrics_records(count: int):
    return [
        {
            "target_date": f"2026-01-{day:02d}",
            "total_value_jpy": 1_000_000 + day * 10_000,
            "market_units_value_jpy": 700_000 + day * 7_000,
            "absolute_amount_value_jpy": 300_000 + day * 3_000,
        }
        for day in range(1, count + 1)
    ]


@pytest.fixture
def harness():
    with patch("src.app.monthly_engine.Notifier")           as MockNotifier,    \
         patch("src.app.monthly_engine.LedgerRepository")   as MockRepo,        \
         patch("src.app.monthly_engine.KnowledgeManager")   as MockKnowledge,   \
         patch("src.app.monthly_engine.DailyMetricsRepository") as MockDailyMetricsRepo, \
         patch("src.app.monthly_engine.MarketSnapshotRepository") as MockMarketSnapshotRepo, \
         patch("src.app.monthly_engine.TimelineController") as MockTimeline,    \
         patch("src.app.monthly_engine.MonthlyCurator")     as MockCurator,     \
         patch("src.app.monthly_engine.MonthlyGuardRail")   as MockGuard,       \
         patch("src.app.monthly_engine.ChronicleRepository") as MockChronicle,  \
         patch("src.app.monthly_engine.SystemUtils")        as MockUtils:

        notifier   = MockNotifier.return_value
        repo       = MockRepo.return_value
        knowledge  = MockKnowledge.return_value
        daily_metrics_repo = MockDailyMetricsRepo.return_value
        market_snapshot_repo = MockMarketSnapshotRepo.return_value
        timeline   = MockTimeline.return_value
        curator    = MockCurator.return_value
        guard      = MockGuard.return_value
        chronicle  = MockChronicle.return_value

        MockUtils.check_env_vars.return_value = True
        MockUtils.set_flag = MagicMock()
        timeline.get_target_date.return_value = "2026-02-28"
        timeline.get_previous_month_last_business_day.return_value = "2026-01-31"
        guard.should_proceed.return_value = True
        repo.load.return_value = _SAMPLE_LEDGER_DICT
        knowledge.extract_monthly_insights.return_value = []
        daily_metrics_repo.load_month.return_value = []
        market_snapshot_repo.load_month.return_value = []
        curator.generate_monthly_chronicle.return_value = _SAMPLE_NARRATIVE
        curator.generate_v4_chronicle.return_value = {
            "schema_version": "v4.1-monthly-chronicle",
            "chronicle": {
                "title": "Test Chronicle",
                "monthly_summary": "B",
                "market_causality": "H",
                "phase_analysis": [],
                "asset_contribution": [],
                "shield_evaluation": "S",
                "portfolio_audit": "",
                "next_month_watch": [],
            },
            "meta": {"year_month": "2026-01"},
        }
        chronicle.exists.return_value = False
        chronicle.load.return_value = _SAMPLE_NARRATIVE
        notifier.monthly_report.return_value = True

        from src.app.monthly_engine import MonthlyEngine
        engine = MonthlyEngine()

        yield engine, {
            "notifier":  notifier,
            "repo":      repo,
            "knowledge": knowledge,
            "daily_metrics_repo": daily_metrics_repo,
            "market_snapshot_repo": market_snapshot_repo,
            "timeline":  timeline,
            "curator":   curator,
            "guard":     guard,
            "chronicle": chronicle,
            "utils":     MockUtils,
        }


class TestMonthlyEngineGuardPath:

    def test_format_test_skips_env_check(self, harness):
        engine, mocks = harness
        with patch.object(engine, "_MonthlyEngine__run_format_test") as mock_ft:
            engine.run(format_test=True)
        mock_ft.assert_called_once()
        mocks["utils"].check_env_vars.assert_not_called()

    def test_env_vars_missing_sends_operational_limit_alert(self, harness):
        engine, mocks = harness
        mocks["utils"].check_env_vars.return_value = False

        engine.run()

        mocks["notifier"].system_alert.assert_called_once()
        assert "OPERATIONAL_LIMIT_MONTHLY" in mocks["notifier"].system_alert.call_args[0]

    def test_guard_blocks_execution(self, harness):
        engine, mocks = harness
        mocks["guard"].should_proceed.return_value = False

        engine.run()

        mocks["notifier"].monthly_report.assert_not_called()

    def test_missing_ledger_terminates_when_daily_metrics_below_v4_threshold(self, harness):
        engine, mocks = harness
        mocks["repo"].load.return_value = None
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(14)

        engine.run()

        mocks["notifier"].monthly_report.assert_not_called()

    def test_missing_ledger_dispatches_v4_when_daily_metrics_reach_threshold(self, harness, tmp_path):
        engine, mocks = harness
        mocks["repo"].load.return_value = None
        mocks["daily_metrics_repo"].load_month.return_value = list(reversed(_daily_metrics_records(15)))
        basis_file = tmp_path / "portfolio_basis.json"
        basis_file.write_text('{"2026-01": {"total_acquisition_cost_jpy": 700000}}', encoding="utf-8")

        with patch("src.app.monthly_engine._PORTFOLIO_BASIS_FILE", str(basis_file)):
            engine.run()

        mocks["curator"].generate_v4_chronicle.assert_called_once()
        mocks["curator"].generate_monthly_chronicle.assert_not_called()
        mocks["notifier"].monthly_report.assert_called_once()
        summary_vm = mocks["notifier"].monthly_report.call_args.args[1]
        assert isinstance(summary_vm, SummaryViewModel)
        assert summary_vm.fmt_safe_ratio == "30.0%"
        assert summary_vm.fmt_iron_bank == "345,000"
        assert summary_vm.fmt_exposure == "805,000"
        assert summary_vm.fmt_total_diff == "+140,000"
        assert summary_vm.fmt_total_diff_pct == "+13.86%"
        assert summary_vm.fmt_total_pl == "+105,000"
        assert summary_vm.total_pl_color == "#c5a059"

    def test_missing_ledger_prefers_daily_metrics_total_return_over_basis(self, harness, tmp_path):
        engine, mocks = harness
        records = _daily_metrics_records(15)
        records[-1]["total_return_jpy"] = 123_456
        records[-1]["total_return_pct"] = 12.34
        records[-1]["total_acquisition_cost_jpy"] = 681_544
        mocks["repo"].load.return_value = None
        mocks["daily_metrics_repo"].load_month.return_value = list(reversed(records))
        basis_file = tmp_path / "portfolio_basis.json"
        basis_file.write_text('{"2026-01": {"total_acquisition_cost_jpy": 1}}', encoding="utf-8")

        with patch("src.app.monthly_engine._PORTFOLIO_BASIS_FILE", str(basis_file)):
            engine.run()

        summary_vm = mocks["notifier"].monthly_report.call_args.args[1]
        assert summary_vm.fmt_total_pl == "+123,456"
        assert summary_vm.fmt_total_diff == "+140,000"
        assert summary_vm.fmt_total_diff_pct == "+13.86%"
        assert summary_vm.total_pl_color == "#c5a059"

    def test_existing_ledger_passes_summary_vm_for_v4_report(self, harness):
        engine, mocks = harness
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(15)

        engine.run()

        mocks["curator"].generate_v4_chronicle.assert_called_once()
        summary_vm = mocks["notifier"].monthly_report.call_args.args[1]
        assert isinstance(summary_vm, SummaryViewModel)
        assert summary_vm.fmt_safe_ratio == "0.0%"
        assert summary_vm.fmt_iron_bank == "0"
        assert summary_vm.fmt_exposure == "9,000,000"
        assert summary_vm.fmt_total_pl == "+500,000"


class TestMarketSnapshotRepository:

    def test_load_month_reads_only_target_month_snapshots_in_date_order(self, tmp_path):
        from src.infra.market_snapshot_repository import MarketSnapshotRepository

        (tmp_path / "market_snapshot_20260115.json").write_text(
            '{"target_date":"2026-01-15","market_summary":"mid"}',
            encoding="utf-8",
        )
        (tmp_path / "market_snapshot_20260102.json").write_text(
            '{"target_date":"2026-01-02","market_summary":"start"}',
            encoding="utf-8",
        )
        (tmp_path / "market_snapshot_20260201.json").write_text(
            '{"target_date":"2026-02-01","market_summary":"other"}',
            encoding="utf-8",
        )

        with patch("src.infra.market_snapshot_repository.DIR_CURRENT", str(tmp_path)):
            records = MarketSnapshotRepository().load_month("2026-01")

        assert [record["target_date"] for record in records] == ["2026-01-02", "2026-01-15"]
        assert [record["market_summary"] for record in records] == ["start", "mid"]


class TestMonthlyEngineNarrativePath:

    def test_generates_chronicle_when_no_cache(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = False
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(15)

        engine.run()

        mocks["daily_metrics_repo"].load_month.assert_called_once_with("2026-01")
        mocks["curator"].generate_v4_chronicle.assert_called_once()
        mocks["market_snapshot_repo"].load_month.assert_called_once_with("2026-01")
        mocks["curator"].generate_monthly_chronicle.assert_not_called()
        mocks["chronicle"].save.assert_called_once()

    def test_v4_chronicle_receives_market_snapshots(self, harness):
        engine, mocks = harness
        daily_metrics = _daily_metrics_records(15)
        market_snapshots = [
            {
                "target_date": "2026-01-15",
                "us_market": {"trading_date": "2026-01-14", "is_holiday": False},
                "market_summary": "S&P500: +0.10% | VIX: 18.00",
            }
        ]
        mocks["daily_metrics_repo"].load_month.return_value = daily_metrics
        mocks["market_snapshot_repo"].load_month.return_value = market_snapshots

        engine.run()

        _, kwargs = mocks["curator"].generate_v4_chronicle.call_args
        assert kwargs["daily_metrics"] == daily_metrics
        assert kwargs["market_snapshots"] == market_snapshots

    def test_falls_back_to_legacy_chronicle_below_daily_metrics_threshold(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = False
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(14)

        engine.run()

        mocks["curator"].generate_v4_chronicle.assert_not_called()
        mocks["curator"].generate_monthly_chronicle.assert_called_once()
        mocks["chronicle"].save.assert_called_once()

    def test_reuses_existing_chronicle_cache(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = True

        engine.run(reuse_context=True)

        mocks["curator"].generate_v4_chronicle.assert_not_called()
        mocks["curator"].generate_monthly_chronicle.assert_not_called()
        mocks["chronicle"].load.assert_called_once()

    def test_reuse_context_false_regenerates_even_if_cache_exists(self, harness):
        engine, mocks = harness
        mocks["chronicle"].exists.return_value = True
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(15)

        engine.run(reuse_context=False)

        mocks["curator"].generate_v4_chronicle.assert_called_once()

    def test_dispatch_success_writes_lock(self, harness):
        engine, mocks = harness
        mocks["notifier"].monthly_report.return_value = True

        engine.run()

        mocks["utils"].set_flag.assert_called_once()

    def test_dispatch_failure_does_not_write_lock(self, harness):
        engine, mocks = harness
        mocks["notifier"].monthly_report.return_value = False

        engine.run()

        mocks["utils"].set_flag.assert_not_called()

    def test_unhandled_exception_triggers_crash_alert(self, harness):
        engine, mocks = harness
        mocks["repo"].load.side_effect = RuntimeError("boom")

        engine.run()

        mocks["notifier"].system_alert.assert_called_once()
        assert "OPERATIONAL_LIMIT_MONTHLY" in mocks["notifier"].system_alert.call_args[0]

    def test_v4_schema_violation_uses_schema_alert_code(self, harness):
        from src.domain.monthly_curator import V4ChronicleSchemaViolation

        engine, mocks = harness
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(15)
        mocks["curator"].generate_v4_chronicle.side_effect = V4ChronicleSchemaViolation(
            "V4 Chronicle schema violation: chronicle.phase_analysis type mismatch"
        )

        engine.run()

        mocks["notifier"].system_alert.assert_called_once()
        assert "V4_SCHEMA_VIOLATION_MONTHLY" in mocks["notifier"].system_alert.call_args[0]
        assert "OPERATIONAL_LIMIT_MONTHLY" not in mocks["notifier"].system_alert.call_args[0]

    def test_v4_banned_words_violation_uses_banned_word_alert_code(self, harness):
        from src.domain.monthly_curator import V4ChronicleBannedWordsViolation

        engine, mocks = harness
        mocks["daily_metrics_repo"].load_month.return_value = _daily_metrics_records(15)
        mocks["curator"].generate_v4_chronicle.side_effect = V4ChronicleBannedWordsViolation(
            "V4 Chronicle banned words violation: Action Ban Violation: ['様子見']"
        )

        engine.run()

        mocks["notifier"].system_alert.assert_called_once()
        assert "V4_BANNED_WORD_MONTHLY" in mocks["notifier"].system_alert.call_args[0]
        assert "OPERATIONAL_LIMIT_MONTHLY" not in mocks["notifier"].system_alert.call_args[0]


class TestMonthlyGuardRail:

    def test_allows_execution_without_legacy_ledger_when_monthly_lock_is_open(self):
        from src.domain.monthly_guard import MonthlyGuardRail

        timeline = MagicMock()
        timeline.get_previous_month_last_business_day.return_value = "2026-01-31"

        # MonthlyGuardRail は台帳を読まない。LedgerReader を受け取らないため、
        # 読み出しが起きないことは signature で保証される。
        with patch("src.domain.monthly_guard.SystemUtils.get_flag", return_value="2025-12"):
            guard = MonthlyGuardRail(timeline)

            assert guard.should_proceed("2026-02-28", force_send=False) is True

    def test_monthly_lock_still_blocks_same_month(self):
        from src.domain.monthly_guard import MonthlyGuardRail

        timeline = MagicMock()
        timeline.get_previous_month_last_business_day.return_value = "2026-01-31"

        with patch("src.domain.monthly_guard.SystemUtils.get_flag", return_value="2026-01"):
            guard = MonthlyGuardRail(timeline)

            assert guard.should_proceed("2026-02-28", force_send=False) is False
