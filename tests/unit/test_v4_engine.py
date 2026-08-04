import json
from unittest.mock import MagicMock, patch

import pytest

from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.universal_ingester import CanonicalLedgerInputError
from src.lib.models import Ledger, LedgerMeta, LedgerSummary, Position


def _shadow(pricing_status="PRICED", total_value=1000, diff_val_jpy=10, diff_pct=0.1, total_return_jpy=None):
    value = 1000 if pricing_status != "MISSING" else 0
    return ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=total_value if pricing_status != "MISSING" else 0,
        total_return_jpy=total_return_jpy,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="FundA",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                current_value_jpy=total_value if pricing_status != "MISSING" else 0,
                diff_val_jpy=diff_val_jpy if pricing_status != "MISSING" else None,
                diff_pct=diff_pct if pricing_status != "MISSING" else None,
                pricing_status=pricing_status,
            )
        ],
    )


def _shadow_us_asset(pricing_status="STALE"):
    return ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=1000,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="UsStockA",
                asset_class="US_STOCK",
                category="US_STOCK",
                currency="USD",
                current_value_jpy=1000,
                diff_val_jpy=10,
                diff_pct=0.1,
                pricing_status=pricing_status,
            )
        ],
    )


def _positive_shadow_with_missing_asset():
    return ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=1000,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="MissingFund",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                current_value_jpy=0,
                pricing_status="MISSING",
            ),
            ShadowAssetRecord(
                source="ABSOLUTE_AMOUNT",
                name="Cash",
                asset_class="CASH",
                category="CASH",
                current_value_jpy=1000,
                pricing_status="STATIC",
            ),
        ],
    )


def _ledger(total_return_jpy=100, diff_jpy=10, diff_pct=0.1):
    return Ledger(
        meta=LedgerMeta(
            generated_at="2026-04-25T00:00:00",
            target_date="2026-04-25",
            version="3.5-v4",
            integrity_status="VERIFIED",
        ),
        summary=LedgerSummary(
            total_assets_jpy=1000,
            total_profit_loss_jpy=total_return_jpy,
            cash_position_jpy=0,
            total_diff_jpy=diff_jpy,
            total_diff_pct=diff_pct,
            total_profit_loss_pct=10.0 if total_return_jpy else 0.0,
            invested_capital_jpy=1000,
            capital_gain_jpy=total_return_jpy,
            class_totals={"MUTUAL_FUNDS": 1000},
            exposure_jpy=1000,
            total_wtd="+1.00%",
            total_mtd="+2.00%",
            total_ytd="+3.00%",
        ),
        assets=[
            Position(
                id="FundA",
                name="FundA",
                raw_name="FundA",
                asset_class="MUTUAL_FUNDS",
                category="INVESTMENT",
                quantity=1,
                unit_price=1000,
                current_price=1000,
                currency="JPY",
                value_jpy=1000,
                acquisition_price=900,
                profit_loss=100,
                profit_loss_pct=11.11,
                prev_day_diff_jpy=diff_jpy,
                prev_day_diff_pct=diff_pct,
                is_nisa=False,
                is_specific=False,
                share=100.0,
                wtd="+1.00%",
                mtd="+2.00%",
                ytd="+3.00%",
            )
        ],
    )


def _canonical_document(integrity_status="VERIFIED"):
    return {
        "meta": {
            "generated_at": "2026-04-25T00:00:00",
            "target_date": "2026-04-25",
            "version": "4.3-v4",
            "integrity_status": integrity_status,
            "has_next_day_record": False,
        },
        "summary": {"total_assets_jpy": 1000, "total_diff_pct": 0.1},
        "assets": [
            {"id": "FundA", "name": "FundA", "price": 1000.0, "pricing_status": "PRICED"},
        ],
    }


@pytest.fixture
def harness(tmp_path):
    with patch("src.app.v4_engine.Notifier") as MockNotifier, \
         patch("src.app.v4_engine.TimelineController") as MockTimeline, \
         patch("src.app.v4_engine.GuardRail") as MockGuard, \
         patch("src.app.v4_engine.CollectionHistoryUpdater") as MockHistoryUpdater, \
         patch("src.app.v4_engine.UniversalIngester") as MockIngester, \
         patch("src.app.v4_engine.ShadowLedgerAdapter") as MockAdapter, \
         patch("src.app.v4_engine.ContextRepository") as MockContextRepo, \
         patch("src.app.v4_engine.DailyMetricsRepository") as MockDailyMetricsRepo, \
         patch("src.app.v4_engine.LedgerRepository") as MockLedgerRepo, \
         patch("src.app.v4_engine.KnowledgeManager") as MockKnowledge, \
         patch("src.app.v4_engine.V4ContentRenderer") as MockRenderer, \
         patch("src.app.v4_engine.MailSender") as MockSender, \
         patch("src.app.v4_engine.MarketDataFetcher") as MockMarketFetcher, \
         patch("src.app.v4_engine.MarketSnapshotRepository") as MockMarketSnapshotRepo, \
         patch("src.app.v4_engine.ensure_units_snapshot") as MockEnsureUnitsSnapshot, \
         patch("src.app.v4_engine.SystemUtils") as MockUtils:

        timeline = MockTimeline.return_value
        guard = MockGuard.return_value
        history_updater = MockHistoryUpdater.return_value
        ingester = MockIngester.return_value
        adapter = MockAdapter.return_value
        context_repo = MockContextRepo.return_value
        daily_metrics_repo = MockDailyMetricsRepo.return_value
        ledger_repo = MockLedgerRepo.return_value
        knowledge = MockKnowledge.return_value
        renderer = MockRenderer.return_value
        sender = MockSender.return_value
        market_fetcher = MockMarketFetcher.return_value
        market_snapshot_repo = MockMarketSnapshotRepo.return_value

        MockUtils.check_env_vars.return_value = True
        MockUtils.set_flag = MagicMock(return_value=True)
        timeline.get_target_date.return_value = "2026-04-25"
        timeline.is_holiday.return_value = False
        timeline.determine_jp_market_date.return_value = "2026-04-25"
        timeline.get_us_market_context.return_value = {
            "trading_date": "2026-04-24",
            "calendar_date": "2026-04-24",
            "is_holiday": False,
        }
        market_fetcher.fetch_market_context.return_value = "S&P500: +0.10% | VIX: 18.00 (+0.10)"
        guard.should_proceed.return_value = True
        guard.should_dispatch_shadow_ledger.return_value = True
        ingester.run.return_value = _shadow()
        adapter.to_legacy_ledger.return_value = _ledger()
        adapter.to_canonical_document.return_value = _canonical_document()
        context_repo.exists.return_value = False
        daily_metrics_repo.save.return_value = True
        ledger_repo.save_document.return_value = None
        ledger_repo.load.return_value = None
        market_snapshot_repo.save.return_value = True
        knowledge.record_insight.return_value = True
        renderer.render.return_value = "<html>v4</html>"
        sender.send.return_value = True
        history_updater.fx_asset_names.return_value = {"USDJPY"}

        from src.app.v4_engine import V4PortfolioEngine

        assert V4PortfolioEngine._V4PortfolioEngine__SHADOW_OUTPUT == "data/v4_shadow_ledger.json"
        assert V4PortfolioEngine._V4PortfolioEngine__APPRAISAL_STATE_PATH == "data/runtime/v4_appraisal_state.json"

        isolated_shadow_path = tmp_path / "data" / "v4_shadow_ledger.json"
        isolated_appraisal_path = tmp_path / "data" / "runtime" / "v4_appraisal_state.json"
        isolated_shadow_path.parent.mkdir(parents=True, exist_ok=True)

        with patch.object(
            V4PortfolioEngine,
            "_V4PortfolioEngine__SHADOW_OUTPUT",
            str(isolated_shadow_path),
        ), patch.object(
            V4PortfolioEngine,
            "_V4PortfolioEngine__APPRAISAL_STATE_PATH",
            str(isolated_appraisal_path),
        ):
            engine = V4PortfolioEngine()
            yield engine, {
                "notifier": MockNotifier.return_value,
                "timeline": timeline,
                "guard": guard,
                "history_updater": history_updater,
                "ingester": ingester,
                "adapter": adapter,
                "context_repo": context_repo,
                "daily_metrics_repo": daily_metrics_repo,
                "ledger_repo": ledger_repo,
                "knowledge": knowledge,
                "renderer": renderer,
                "sender": sender,
                "market_fetcher": market_fetcher,
                "market_snapshot_repo": market_snapshot_repo,
                "ensure_units_snapshot": MockEnsureUnitsSnapshot,
                "utils": MockUtils,
                "shadow_output": isolated_shadow_path,
                "appraisal_state": isolated_appraisal_path,
            }


def test_v4_engine_dispatches_from_universal_ingester(harness):
    engine, mocks = harness

    assert engine.run(target_date="2026-04-25") is True

    mocks["history_updater"].refresh.assert_called_once_with(
        target_date="2026-04-25",
        us_market_date="2026-04-24",
    )
    mocks["ensure_units_snapshot"].assert_called_once_with("2026-04-25", allow_create=False)
    mocks["ingester"].run.assert_called_once_with("2026-04-25", units_mode="strict", previous_records={})
    mocks["daily_metrics_repo"].save.assert_called_once()
    saved_metrics = mocks["daily_metrics_repo"].save.call_args[0][0]
    assert saved_metrics["schema_version"] == "v4.1-daily-metrics"
    assert saved_metrics["target_date"] == "2026-04-25"
    assert saved_metrics["market_units_value_jpy"] == 1000
    assert saved_metrics["absolute_amount_value_jpy"] == 0
    assert mocks["daily_metrics_repo"].save.call_args[0][1] == "2026-04-25"
    mocks["market_snapshot_repo"].save.assert_called_once()
    mocks["adapter"].to_legacy_ledger.assert_called_once()
    mocks["market_fetcher"].fetch_market_context.assert_called_once_with("2026-04-24")
    mocks["renderer"].render.assert_called_once()
    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()
    mocks["sender"].send.assert_called_once_with("CAPTION [2026-04-25]", "<html>v4</html>")
    mocks["utils"].set_flag.assert_called_once()
    assert mocks["shadow_output"].is_file()
    persisted_shadow = json.loads(mocks["shadow_output"].read_text(encoding="utf-8"))
    assert persisted_shadow["target_date"] == "2026-04-25"
    assert persisted_shadow["total_value_jpy"] == 1000
    assert persisted_shadow["assets"][0]["name"] == "FundA"


def test_v4_engine_always_uses_deterministic_context_for_large_top_mover_value(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow(diff_val_jpy=60000, diff_pct=0.5)

    engine.run(target_date="2026-04-25")

    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()
    rendered_vm = mocks["renderer"].render.call_args[0][0]
    assert rendered_vm.theme_subtitle == "日次記録"


def test_v4_engine_always_uses_deterministic_context_for_large_top_mover_pct(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow(diff_val_jpy=10, diff_pct=1.25)

    engine.run(target_date="2026-04-25")

    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()
    rendered_vm = mocks["renderer"].render.call_args[0][0]
    assert rendered_vm.theme_subtitle == "日次記録"


def test_v4_engine_skips_daily_ai_for_missing_pricing(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow("MISSING")
    mocks["adapter"].to_legacy_ledger.return_value = _ledger()

    engine.run(target_date="2026-04-25")

    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()


def test_v4_engine_skips_daily_ai_when_market_summary_missing(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow(diff_val_jpy=60000, diff_pct=1.25)
    mocks["market_fetcher"].fetch_market_context.return_value = "(Market data unavailable)"

    engine.run(target_date="2026-04-25")

    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()


def test_v4_engine_skips_daily_ai_for_negative_return_without_anomaly(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow(diff_val_jpy=10, diff_pct=0.1, total_return_jpy=-100)
    mocks["adapter"].to_legacy_ledger.return_value = _ledger(total_return_jpy=-100, diff_jpy=10, diff_pct=0.1)

    engine.run(target_date="2026-04-25")

    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()
    assert mocks["appraisal_state"].is_file()
    persisted_appraisal = json.loads(mocks["appraisal_state"].read_text(encoding="utf-8"))
    assert persisted_appraisal == {"last_displayed_date": "2026-04-25"}


def test_v4_engine_reuses_cached_context_without_regenerating(harness):
    engine, mocks = harness
    cached_context = {
        "theme": "Cached Thesis",
        "overview": "Cached overview",
        "insight": {"theme": "Cached Thesis", "analysis": "Cached analysis"},
        "portfolio_audit": {"core_thesis": "方針維持", "commentary": "Cached audit"},
        "shield_evaluation": {"status": "中立", "commentary": "Cached shield"},
    }
    mocks["context_repo"].exists.return_value = True
    mocks["context_repo"].load.return_value = cached_context
    mocks["ingester"].run.return_value = _shadow(diff_val_jpy=60000, diff_pct=1.25)

    engine.run(target_date="2026-04-25", reuse_context=True)

    mocks["context_repo"].load.assert_called_once_with("2026-04-25")
    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()
    assert mocks["renderer"].render.call_count == 1
    rendered_vm = mocks["renderer"].render.call_args[0][0]
    assert rendered_vm.target_date == "2026-04-25"
    assert rendered_vm.theme_subtitle == "Cached Thesis"
    assert rendered_vm.portfolio_audit_status == "方針維持"
    assert rendered_vm.shield_status == "中立"


def test_v4_engine_uses_today_when_target_date_is_omitted(harness):
    engine, mocks = harness

    with patch("src.app.v4_engine.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "2026-04-27"
        engine.run()

    mocks["guard"].should_proceed.assert_called_once()
    assert mocks["guard"].should_proceed.call_args.kwargs["target_date_str"] == "2026-04-27"
    mocks["timeline"].get_target_date.assert_not_called()
    mocks["history_updater"].refresh.assert_called_once_with(
        target_date="2026-04-27",
        us_market_date="2026-04-24",
    )
    mocks["ensure_units_snapshot"].assert_called_once_with("2026-04-27", allow_create=True)
    mocks["ingester"].run.assert_called_once_with("2026-04-27", units_mode="strict", previous_records={})
    mocks["sender"].send.assert_called_once_with("CAPTION [2026-04-27]", "<html>v4</html>")


def test_v4_engine_missing_prices_dispatch_as_provisional(harness):
    engine, mocks = harness
    missing_shadow = _positive_shadow_with_missing_asset()
    mocks["ingester"].run.return_value = missing_shadow

    engine.run(target_date="2026-04-25")

    assert mocks["sender"].send.call_args[0][0] == "CAPTION [2026-04-25]○"
    assert mocks["ingester"].run.call_count == 2
    assert mocks["history_updater"].refresh.call_count == 2
    assert mocks["history_updater"].refresh.call_args_list[1].kwargs["only_assets"] == {"MissingFund"}
    mocks["utils"].set_flag.assert_not_called()
    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()


def test_v4_engine_stale_prices_dispatch_as_provisional(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow("STALE")

    engine.run(target_date="2026-04-25")

    assert mocks["sender"].send.call_args[0][0] == "CAPTION [2026-04-25]○"
    assert mocks["ingester"].run.call_count == 2
    assert mocks["history_updater"].refresh.call_count == 2
    assert mocks["history_updater"].refresh.call_args_list[1].kwargs["only_assets"] == {"FundA"}
    mocks["utils"].set_flag.assert_not_called()
    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()


def test_provisional_dispatch_retries_then_records_completion_and_stops(harness):
    engine, mocks = harness
    from src.domain.guard_rail import GuardRail

    target_date = "2026-04-25"
    lock_state = {"value": "2026-04-24"}
    stale = _shadow("STALE")
    priced = _shadow("PRICED")
    mocks["ingester"].run.side_effect = [stale, stale, priced]

    def record_lock(_path, value):
        lock_state["value"] = value
        return True

    mocks["utils"].set_flag.side_effect = record_lock
    engine._V4PortfolioEngine__guard = GuardRail(mocks["timeline"])

    with patch(
        "src.domain.guard_rail.SystemUtils.get_flag",
        side_effect=lambda _path: lock_state["value"],
    ):
        assert engine.run(target_date=target_date) is True
        assert lock_state["value"] == "2026-04-24"

        assert engine.run(target_date=target_date) is True
        assert lock_state["value"] == target_date

        assert engine.run(target_date=target_date) is False

    assert [call.args[0] for call in mocks["sender"].send.call_args_list] == [
        "CAPTION [2026-04-25]○",
        "CAPTION [2026-04-25]",
    ]
    assert mocks["ingester"].run.call_count == 3
    mocks["utils"].set_flag.assert_called_once()


def test_v4_engine_retry_includes_fx_dependency_for_us_assets(harness):
    engine, mocks = harness
    stale_us = _shadow_us_asset("STALE")
    mocks["ingester"].run.side_effect = [stale_us, stale_us]

    engine.run(target_date="2026-04-25")

    assert mocks["history_updater"].refresh.call_count == 2
    assert mocks["history_updater"].refresh.call_args_list[1].kwargs["only_assets"] == {"UsStockA", "USDJPY"}


def test_v4_engine_uses_deterministic_context_always(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow(diff_val_jpy=60000, diff_pct=1.25)

    engine.run(target_date="2026-04-25")

    mocks["context_repo"].save.assert_not_called()
    mocks["knowledge"].record_insight.assert_not_called()
    rendered_vm = mocks["renderer"].render.call_args[0][0]
    assert rendered_vm.theme_subtitle == "日次記録"


def test_ingester_failure_prevents_dispatch_and_completion_lock(harness):
    engine, mocks = harness
    mocks["ingester"].run.side_effect = CanonicalLedgerInputError("required SSOT invalid")

    assert engine.run(target_date="2026-04-25") is False

    mocks["sender"].send.assert_not_called()
    mocks["utils"].set_flag.assert_not_called()


def test_snapshot_persistence_failure_stops_all_final_outputs_and_dispatch(harness):
    engine, mocks = harness
    mocks["ensure_units_snapshot"].side_effect = OSError("disk full")

    assert engine.run(target_date="2026-04-25") is False

    mocks["history_updater"].refresh.assert_not_called()
    mocks["ingester"].run.assert_not_called()
    mocks["daily_metrics_repo"].save.assert_not_called()
    mocks["market_snapshot_repo"].save.assert_not_called()
    mocks["sender"].send.assert_not_called()
    mocks["utils"].set_flag.assert_not_called()


def test_finalized_ledger_persistence_failure_prevents_dispatch_and_lock(harness):
    engine, mocks = harness
    mocks["shadow_output"].write_text('{"previous":"valid"}\n', encoding="utf-8")

    with patch("src.app.v4_engine.atomic_write_json", side_effect=OSError("disk full")):
        result = engine.run(target_date="2026-04-25")

    assert result is False
    assert mocks["shadow_output"].read_text(encoding="utf-8") == '{"previous":"valid"}\n'
    mocks["daily_metrics_repo"].save.assert_not_called()
    mocks["sender"].send.assert_not_called()
    mocks["utils"].set_flag.assert_not_called()


def test_daily_metrics_persistence_failure_prevents_dispatch_and_lock(harness):
    engine, mocks = harness
    mocks["daily_metrics_repo"].save.return_value = False

    assert engine.run(target_date="2026-04-25") is False

    mocks["market_snapshot_repo"].save.assert_not_called()
    mocks["sender"].send.assert_not_called()
    mocks["utils"].set_flag.assert_not_called()


def test_market_snapshot_persistence_failure_prevents_dispatch_and_lock(harness):
    engine, mocks = harness
    mocks["market_snapshot_repo"].save.return_value = False

    assert engine.run(target_date="2026-04-25") is False

    mocks["sender"].send.assert_not_called()
    mocks["utils"].set_flag.assert_not_called()


def test_canonical_ledger_is_persisted_for_target_date(harness):
    engine, mocks = harness

    assert engine.run(target_date="2026-04-25") is True

    mocks["ledger_repo"].save_document.assert_called_once()
    saved_document, saved_date = mocks["ledger_repo"].save_document.call_args[0]
    assert saved_date == "2026-04-25"
    assert saved_document is mocks["adapter"].to_canonical_document.return_value


def test_stale_pricing_still_persists_canonical_ledger(harness):
    engine, mocks = harness
    mocks["ingester"].run.return_value = _shadow(pricing_status="STALE")

    assert engine.run(target_date="2026-04-25") is True

    mocks["ledger_repo"].save_document.assert_called_once()
    assert mocks["ledger_repo"].save_document.call_args[0][1] == "2026-04-25"


def test_previous_ledger_records_are_passed_to_ingester(harness):
    engine, mocks = harness
    mocks["ledger_repo"].load.side_effect = lambda d: (
        {
            "meta": {"target_date": "2026-04-24", "integrity_status": "VERIFIED"},
            "assets": [
                {"id": "GC=F", "price": 4049.10009765625, "pricing_status": "PRICED", "source_date": "2026-04-23"},
                {"id": "NYFANG", "current_price": 90492.0},
                {"id": "Cash", "price": 0.0},
            ],
        }
        if d == "2026-04-24"
        else None
    )

    assert engine.run(target_date="2026-04-25") is True

    records = mocks["ingester"].run.call_args.kwargs["previous_records"]
    assert records["GC=F"] == {
        "price": 4049.10009765625,
        "pricing_status": "PRICED",
        "source_date": "2026-04-23",
        "target_date": "2026-04-24",
    }
    # v3.5 以前の台帳は資産別の鮮度を持たないため pricing_status は None のまま渡す。
    assert records["NYFANG"]["price"] == 90492.0
    assert records["NYFANG"]["pricing_status"] is None
    assert "Cash" not in records


def test_missing_previous_ledger_falls_back_to_history(harness):
    engine, mocks = harness
    mocks["ledger_repo"].load.return_value = None

    assert engine.run(target_date="2026-04-25") is True

    assert mocks["ingester"].run.call_args.kwargs["previous_records"] == {}


def test_verified_canonical_ledger_is_never_overwritten(harness):
    engine, mocks = harness
    mocks["ledger_repo"].load.return_value = {
        "meta": {"target_date": "2026-04-25", "integrity_status": "VERIFIED"}
    }

    assert engine.run(target_date="2026-04-25") is True

    mocks["ledger_repo"].save_document.assert_not_called()
    mocks["sender"].send.assert_called_once()


def test_stagnant_canonical_ledger_is_updated_by_later_run(harness):
    engine, mocks = harness
    mocks["ledger_repo"].load.return_value = {
        "meta": {"target_date": "2026-04-25", "integrity_status": "STAGNANT"}
    }

    assert engine.run(target_date="2026-04-25") is True

    mocks["ledger_repo"].save_document.assert_called_once()


def test_unreadable_existing_ledger_does_not_block_persistence(harness):
    engine, mocks = harness
    mocks["ledger_repo"].load.return_value = None

    assert engine.run(target_date="2026-04-25") is True

    mocks["ledger_repo"].save_document.assert_called_once()


def test_canonical_ledger_persistence_failure_prevents_dispatch_and_lock(harness):
    engine, mocks = harness
    mocks["ledger_repo"].save_document.side_effect = RuntimeError("disk full")

    assert engine.run(target_date="2026-04-25") is False

    mocks["sender"].send.assert_not_called()
    mocks["utils"].set_flag.assert_not_called()


def test_completion_lock_failure_is_returned_as_incomplete_run(harness):
    engine, mocks = harness
    mocks["utils"].set_flag.return_value = False

    assert engine.run(target_date="2026-04-25") is False

    mocks["sender"].send.assert_called_once()
    mocks["utils"].set_flag.assert_called_once()
    mocks["notifier"].system_alert.assert_called_once()
