import os
import json
from datetime import date, datetime
from typing import Any, Final

from src.app.notifier import Notifier
from src.app.renderer.v4_content_renderer import V4ContentRenderer
from src.app.renderer.v4_view_models import V4MonolithicViewModel
from src.app.renderer.view_models import PositionViewModel, SummaryViewModel
from src.config.settings import DATA_DIR, LAST_SENT_FILE_CURRENT, LLM_PRIORITY_ORDER, SMTP_TO, VERSION
from src.domain.daily_metrics import build_daily_metrics, build_deterministic_daily_context
from src.domain.collection_history_updater import CollectionHistoryUpdater
from src.domain.guard_rail import GuardRail
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.domain.v4_ledger_finalizer import V4LedgerFinalizer
from src.domain.universal_ingester import UniversalIngester
from src.infra.context_repository import ContextRepository
from src.infra.daily_metrics_repository import DailyMetricsRepository
from src.infra.knowledge_manager import KnowledgeManager
from src.infra.mail_sender import MailSender
from src.infra.market_data import MarketDataFetcher
from src.infra.market_snapshot_repository import MarketSnapshotRepository
from src.lib.logger import setup_logger
from src.lib.timeline_controller import TimelineController
from src.lib.utils import SystemUtils

logger = setup_logger(__name__)


def _mask_smtp_to(addr: str | None) -> str:
    if not addr or "@" not in addr:
        return "unset"
    local, domain = addr.split("@", 1)
    return f"{local[:1]}***@{domain}"


class V4PortfolioEngine:
    __REV: Final[str] = "Rev. 1"
    __SHADOW_OUTPUT: Final[str] = os.path.join(DATA_DIR, "v4_shadow_ledger.json")
    __APPRAISAL_STATE_PATH: Final[str] = os.path.join(DATA_DIR, "runtime", "v4_appraisal_state.json")

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing V4PortfolioEngine")
        self.__notifier = Notifier()
        self.__timeline = TimelineController()
        self.__guard = GuardRail(self.__timeline)
        self.__history_updater = CollectionHistoryUpdater()
        self.__ingester = UniversalIngester()
        self.__adapter = ShadowLedgerAdapter()
        self.__finalizer = V4LedgerFinalizer(self.__timeline)
        self.__context_repo = ContextRepository()
        self.__daily_metrics_repo = DailyMetricsRepository()
        self.__market_snapshot_repo = MarketSnapshotRepository()
        self.__knowledge_mgr = KnowledgeManager()
        self.__renderer = V4ContentRenderer()
        self.__sender = MailSender()
        self.__market_fetcher = MarketDataFetcher()

    def run(self, **kwargs: Any) -> None:
        try:
            logger.info("[Guard] V4 Pre-flight Check: Verifying environment and resources")
            _smtp = _mask_smtp_to(SMTP_TO)
            logger.info(f"[Config] v{VERSION} | LLM={LLM_PRIORITY_ORDER} | SMTP_TO={_smtp}")
            if not SystemUtils.check_env_vars():
                raise RuntimeError("Critical environment variables missing. Pipeline terminated.")

            if kwargs.get("test_error"):
                self.__notifier.system_alert("Test alert triggered.", "SYSTEM_CRASH_V4", is_test=True)
                return

            manual_date = kwargs.get("target_date")
            scope = kwargs.get("scope", "all")
            force_send = kwargs.get("force_send", False)
            format_test = kwargs.get("format_test", False)
            reuse_context = kwargs.get("reuse_context", False)
            if manual_date:
                target_date_str = self.__timeline.get_target_date(manual_date)
            else:
                target_date_str = datetime.now().strftime("%Y-%m-%d")
            logger.info(f"[Guard] Launching V4 Engine v{VERSION} | Target: {target_date_str} | Scope: {scope}")

            if not self.__guard.should_proceed(
                target_date_str=target_date_str,
                lock_file=LAST_SENT_FILE_CURRENT,
                force_send=force_send,
                scope=scope,
                format_test=format_test,
            ):
                logger.info("[Outcome] V4 execution inhibited by GuardRail")
                return

            us_context = self.__timeline.get_us_market_context(target_date_str)
            trading_date = us_context.get("trading_date") or target_date_str
            self.__history_updater.refresh(
                target_date=target_date_str,
                us_market_date=trading_date,
            )
            shadow_ledger = self.__ingester.run(target_date_str, output_path=self.__SHADOW_OUTPUT)
            finalized_ledger = self.__finalizer.finalize(shadow_ledger)
            finalized_ledger = self.__retry_incomplete_market_pricing(
                target_date=target_date_str,
                us_market_date=trading_date,
                current_ledger=finalized_ledger,
            )
            self.__persist_finalized_shadow_ledger(finalized_ledger)
            if not self.__guard.should_dispatch_shadow_ledger(finalized_ledger, allow_missing=True):
                logger.info("[Outcome] V4 execution inhibited by ShadowLedger GuardRail")
                return
            daily_metrics = build_daily_metrics(finalized_ledger)
            if not self.__daily_metrics_repo.save(daily_metrics, target_date_str):
                logger.warning(f"[AUDIT] V4 daily metrics save failed: {target_date_str}")
            market_context = self.__build_v4_market_context(target_date_str)
            if not self.__market_snapshot_repo.save(market_context, target_date_str):
                logger.warning(f"[AUDIT] V4 market snapshot save failed: {target_date_str}")

            canonical_ledger = self.__adapter.to_legacy_ledger(finalized_ledger)
            is_provisional = any(asset.pricing_status in ("MISSING", "STALE") for asset in finalized_ledger.assets)
            summary_vm = SummaryViewModel(canonical_ledger.summary)
            raw_asset_vms = [PositionViewModel(position) for position in canonical_ledger.assets]
            context_data = self.__resolve_context_data(
                target_date=target_date_str,
                shadow_ledger=finalized_ledger,
                summary_vm=summary_vm,
                asset_vms=raw_asset_vms,
                reuse_context=reuse_context,
                daily_metrics=daily_metrics,
                market_context=market_context,
                format_test=format_test,
            )
            show_appraisal = self.__should_show_appraisal(target_date_str, finalized_ledger.total_return_jpy)
            subject, html = self.__build_dispatch_artifacts(
                target_date=target_date_str,
                shadow_ledger=finalized_ledger,
                context_data=context_data,
                summary_vm=summary_vm,
                asset_vms=raw_asset_vms,
                is_provisional=is_provisional,
                show_appraisal=show_appraisal,
            )
            dispatched = self.__dispatch_monolithic_report(subject, html, format_test)

            if dispatched and not format_test and not is_provisional:
                self.__record_successful_dispatch(target_date_str, show_appraisal)

            final_status = "DISPATCHED" if dispatched else "SKIPPED"
            logger.info(f"[Outcome] V4 pipeline cycle finished: {final_status}")
        except RuntimeError as re_err:
            logger.warning(f"[Guard] V4 operational limit: {re_err}")
            self.__notifier.system_alert(str(re_err), "OPERATIONAL_LIMIT_V4")
        except Exception as exc:
            logger.error(f"[Outcome] V4 FATAL CRASH: {exc}", exc_info=True)
            self.__notifier.system_alert(str(exc), "SYSTEM_CRASH_V4")

    def __retry_incomplete_market_pricing(
        self,
        target_date: str,
        us_market_date: str,
        current_ledger: Any,
    ) -> Any:
        incomplete_assets = [
            asset
            for asset in current_ledger.assets
            if asset.source == "MARKET_UNITS" and asset.pricing_status in ("MISSING", "STALE")
        ]
        if not incomplete_assets:
            return current_ledger

        target_names = {asset.name for asset in incomplete_assets}
        needs_fx_refresh = any(
            (asset.currency == "USD" or asset.asset_class == "COMMODITIES")
            for asset in incomplete_assets
        )
        if needs_fx_refresh:
            target_names |= self.__history_updater.fx_asset_names()
        logger.info(
            f"[Acquisition] Incomplete pricing detected ({len(target_names)} assets). Retrying selective refresh."
        )
        self.__history_updater.refresh(
            target_date=target_date,
            us_market_date=us_market_date,
            only_assets=target_names,
        )
        retried_ledger = self.__ingester.run(target_date, output_path=self.__SHADOW_OUTPUT)
        return self.__finalizer.finalize(retried_ledger)

    def __persist_finalized_shadow_ledger(self, shadow_ledger: Any) -> None:
        try:
            with open(self.__SHADOW_OUTPUT, "w", encoding="utf-8") as fh:
                json.dump(shadow_ledger.model_dump(), fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except Exception as exc:
            logger.warning(f"[AUDIT] Failed to persist finalized ShadowLedger: {exc}")

    def __resolve_context_data(
        self,
        target_date: str,
        shadow_ledger: Any,
        summary_vm: SummaryViewModel,
        asset_vms: list[PositionViewModel],
        reuse_context: bool,
        daily_metrics: dict[str, Any],
        market_context: dict[str, Any],
        format_test: bool,
    ) -> dict[str, Any]:
        if format_test:
            return self.__format_test_context()
        return self.__load_or_generate_context(
            target_date=target_date,
            shadow_ledger=shadow_ledger,
            summary_vm=summary_vm,
            asset_vms=asset_vms,
            reuse_context=reuse_context,
            daily_metrics=daily_metrics,
            market_context=market_context,
        )

    def __build_dispatch_artifacts(
        self,
        target_date: str,
        shadow_ledger: Any,
        context_data: dict[str, Any],
        summary_vm: SummaryViewModel,
        asset_vms: list[PositionViewModel],
        is_provisional: bool,
        show_appraisal: bool,
    ) -> tuple[str, str]:
        enriched_context = dict(context_data)
        enriched_context["appraisal_visibility"] = {"show": show_appraisal}
        html = self.__render_monolithic_html(shadow_ledger, enriched_context, summary_vm, asset_vms)
        return self.__build_subject(target_date, is_provisional), html

    def __render_monolithic_html(
        self,
        shadow_ledger: Any,
        context_data: dict[str, Any],
        summary_vm: SummaryViewModel,
        asset_vms: list[PositionViewModel],
    ) -> str:
        return self.__renderer.render(
            V4MonolithicViewModel(
                shadow_ledger,
                context_data,
                summary_vm=summary_vm,
                asset_vms=asset_vms,
            )
        )

    def __build_subject(self, target_date: str, is_provisional: bool) -> str:
        subject = f"CAPTION [{target_date}]"
        if is_provisional:
            subject = f"{subject}○"
        return subject

    def __dispatch_monolithic_report(self, subject: str, html: str, format_test: bool) -> bool:
        if format_test:
            return True
        return self.__sender.send(subject, html)

    def __record_successful_dispatch(self, target_date: str, show_appraisal: bool) -> None:
        if show_appraisal:
            self.__record_appraisal_display(target_date)
        SystemUtils.set_flag(LAST_SENT_FILE_CURRENT, target_date)

    def __load_or_generate_context(
        self,
        target_date: str,
        shadow_ledger: Any,
        summary_vm: SummaryViewModel,
        asset_vms: list[PositionViewModel],
        reuse_context: bool,
        daily_metrics: dict[str, Any],
        market_context: dict[str, Any],
    ) -> dict[str, Any]:
        if reuse_context and self.__context_repo.exists(target_date):
            logger.info(f"[Acquisition] Reusing existing V4 context for {target_date}")
            return self.__context_repo.load(target_date) or {}

        logger.info("[V4] Daily AI skipped; using deterministic daily context.")
        context_data = build_deterministic_daily_context(shadow_ledger, daily_metrics, market_context)
        return self.__attach_context_layers(context_data, shadow_ledger, summary_vm, asset_vms)

    def __attach_context_layers(
        self,
        context_data: dict[str, Any],
        shadow_ledger: Any,
        summary_vm: SummaryViewModel,
        asset_vms: list[PositionViewModel],
    ) -> dict[str, Any]:
        vm = V4MonolithicViewModel(
            shadow_ledger,
            context_data,
            summary_vm=summary_vm,
            asset_vms=asset_vms,
        )
        enriched = dict(context_data)
        enriched.setdefault("display_context", vm.display_context)
        enriched.setdefault("archive_context", vm.archive_context)
        return enriched

    def __build_v4_market_context(self, target_date: str) -> dict[str, Any]:
        us_context = self.__timeline.get_us_market_context(target_date)
        us_trade_date = us_context.get("trading_date") or target_date
        market_summary = self.__market_fetcher.fetch_market_context(us_trade_date)
        return {
            "target_date": target_date,
            "us_market": us_context,
            "market_summary": market_summary,
        }

    def __format_test_context(self) -> dict[str, Any]:
        return {
            "theme": "V4 Monolithic Format Test",
            "overview": "Format test rendering path. Intelligence generation is intentionally skipped.",
            "shield_evaluation": "Shield panel reserved for final causal evaluation.",
            "portfolio_audit": {
                "core_thesis": "WATCH",
                "cash_buffer": "UNKNOWN",
                "stagnation_readiness": "UNKNOWN",
                "summary": "Template structure only.",
            },
            "meta": {"theme_code": "FORMAT", "total_return": "+0"},
        }

    def __should_show_appraisal(self, target_date: str, total_return_jpy: float | None) -> bool:
        if total_return_jpy is None or total_return_jpy >= 0:
            return False
        last_shown_date = self.__load_last_appraisal_date()
        if not last_shown_date:
            return True
        try:
            current = date.fromisoformat(target_date)
            previous = date.fromisoformat(last_shown_date)
        except ValueError:
            return True
        return (current - previous).days >= 7

    def __load_last_appraisal_date(self) -> str:
        path = self.__APPRAISAL_STATE_PATH
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            value = payload.get("last_displayed_date")
            return str(value) if value else ""
        except Exception:
            return ""

    def __record_appraisal_display(self, target_date: str) -> None:
        path = self.__APPRAISAL_STATE_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {"last_displayed_date": target_date}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
