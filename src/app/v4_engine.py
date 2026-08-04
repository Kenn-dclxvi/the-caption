import os
import json
from datetime import date, datetime, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

from src.app.notifier import Notifier
from src.app.renderer.v4_content_renderer import V4ContentRenderer
from src.app.renderer.v4_view_models import V4MonolithicViewModel
from src.app.renderer.view_models import PositionViewModel, SummaryViewModel
from src.config.settings import DATA_DIR, LAST_SENT_FILE_CURRENT, LLM_PRIORITY_ORDER, SMTP_TO, VERSION
from src.domain.daily_metrics import build_daily_metrics, build_deterministic_daily_context
from src.domain.collection_history_updater import CollectionHistoryUpdater
from src.domain.guard_rail import GuardRail
from src.domain.market_units_snapshot import ensure_units_snapshot
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.domain.v4_ledger_finalizer import V4LedgerFinalizer
from src.domain.universal_ingester import UniversalIngester
from src.infra.context_repository import ContextRepository
from src.infra.daily_metrics_repository import DailyMetricsRepository
from src.infra.knowledge_manager import KnowledgeManager
from src.infra.ledger_repository import LedgerRepository
from src.infra.mail_sender import MailSender
from src.infra.market_data import MarketDataFetcher
from src.infra.market_snapshot_repository import MarketSnapshotRepository
from src.lib.logger import setup_logger
from src.lib.atomic_write import atomic_write_json
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
    # 前営業日の正本へ届く遡り範囲。年末年始やGWの連休は最長で1週間を超えるため、
    # 暦日ではなく営業日換算で十分な余裕を取る。無制限に遡らないのは、正本が長期に
    # 欠落している区間で数か月前の台帳を「前営業日」として採用する事故を防ぐため。
    # これを超えた場合は history ベースの前日終値へフォールバックする。
    __PREVIOUS_LEDGER_LOOKBACK_DAYS: Final[int] = 12
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
        self.__ledger_repo = LedgerRepository()
        self.__market_snapshot_repo = MarketSnapshotRepository()
        self.__knowledge_mgr = KnowledgeManager()
        self.__renderer = V4ContentRenderer()
        self.__sender = MailSender()
        self.__market_fetcher = MarketDataFetcher()

    def run(self, **kwargs: Any) -> bool:
        try:
            logger.info("[Guard] V4 Pre-flight Check: Verifying environment and resources")
            _smtp = _mask_smtp_to(SMTP_TO)
            logger.info(f"[Config] v{VERSION} | LLM={LLM_PRIORITY_ORDER} | SMTP_TO={_smtp}")
            if not SystemUtils.check_env_vars():
                raise RuntimeError("Critical environment variables missing. Pipeline terminated.")

            if kwargs.get("test_error"):
                self.__notifier.system_alert("Test alert triggered.", "SYSTEM_CRASH_V4", is_test=True)
                return False

            manual_date = kwargs.get("target_date")
            scope = kwargs.get("scope", "all")
            force_send = kwargs.get("force_send", False)
            format_test = kwargs.get("format_test", False)
            reuse_context = kwargs.get("reuse_context", False)
            if manual_date:
                target_date_str = self.__timeline.get_target_date(manual_date)
            else:
                target_date_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
            logger.info(f"[Guard] Launching V4 Engine v{VERSION} | Target: {target_date_str} | Scope: {scope}")

            if not self.__guard.should_proceed(
                target_date_str=target_date_str,
                lock_file=LAST_SENT_FILE_CURRENT,
                force_send=force_send,
                scope=scope,
                format_test=format_test,
            ):
                logger.info("[Outcome] V4 execution inhibited by GuardRail")
                return False

            today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
            ensure_units_snapshot(
                target_date_str,
                allow_create=target_date_str == today_jst,
            )

            us_context = self.__timeline.get_us_market_context(target_date_str)
            trading_date = us_context.get("trading_date") or target_date_str
            self.__history_updater.refresh(
                target_date=target_date_str,
                us_market_date=trading_date,
            )
            previous_records = self.__load_previous_ledger_records(target_date_str)
            shadow_ledger = self.__ingester.run(
                target_date_str,
                units_mode="strict",
                previous_records=previous_records,
            )
            finalized_ledger = self.__finalizer.finalize(shadow_ledger)
            finalized_ledger = self.__retry_incomplete_market_pricing(
                target_date=target_date_str,
                us_market_date=trading_date,
                current_ledger=finalized_ledger,
            )
            if not self.__guard.should_dispatch_shadow_ledger(finalized_ledger, allow_missing=True):
                logger.info("[Outcome] V4 execution inhibited by ShadowLedger GuardRail")
                return False
            if not self.__persist_finalized_shadow_ledger(finalized_ledger):
                logger.error("[Outcome] V4 finalized ShadowLedger persistence failed. Dispatch blocked.")
                return False
            # 正本を最初に確定させる。daily_metrics / market_snapshot を先に保存すると、
            # 正本の保存が失敗した日でもそれらが残り、月次が対応する正本のない記録を
            # 入力として数えてしまう。
            canonical_ledger = self.__adapter.to_legacy_ledger(finalized_ledger)
            if format_test:
                # レンダリング確認のみの実行。ここで正本を確定させると、後続の本番実行が
                # VERIFIED を尊重して上書きを拒否し、実データが正本へ入らなくなる。
                logger.info(
                    f"[Guard] Format test run; skipping canonical ledger persistence for {target_date_str}."
                )
            else:
                canonical_document = self.__adapter.to_canonical_document(finalized_ledger)
                if not self.__persist_canonical_ledger(canonical_document, target_date_str):
                    logger.error(
                        f"[Outcome] V4 canonical ledger persistence failed: {target_date_str}. Dispatch blocked."
                    )
                    return False

            daily_metrics = build_daily_metrics(finalized_ledger)
            if not self.__daily_metrics_repo.save(daily_metrics, target_date_str):
                logger.error(f"[Outcome] V4 daily metrics persistence failed: {target_date_str}. Dispatch blocked.")
                return False
            market_context = self.__build_v4_market_context(target_date_str)
            if not self.__market_snapshot_repo.save(market_context, target_date_str):
                logger.error(f"[Outcome] V4 market snapshot persistence failed: {target_date_str}. Dispatch blocked.")
                return False
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
                if not self.__record_successful_dispatch(target_date_str, show_appraisal):
                    message = (
                        f"CompletionLock update failed after mail dispatch for {target_date_str}; "
                        "the run is incomplete and a retry may redeliver the message."
                    )
                    logger.error(f"[Outcome] V4 {message}")
                    self.__notifier.system_alert(message, "COMPLETION_LOCK_WRITE_FAILED_V4")
                    return False

            final_status = "DISPATCHED" if dispatched else "SKIPPED"
            logger.info(f"[Outcome] V4 pipeline cycle finished: {final_status}")
            return dispatched
        except RuntimeError as re_err:
            logger.warning(f"[Guard] V4 operational limit: {re_err}")
            self.__notifier.system_alert(str(re_err), "OPERATIONAL_LIMIT_V4")
            return False
        except Exception as exc:
            logger.error(f"[Outcome] V4 FATAL CRASH: {exc}", exc_info=True)
            self.__notifier.system_alert(str(exc), "SYSTEM_CRASH_V4")
            return False

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
        retried_ledger = self.__ingester.run(
            target_date,
            units_mode="strict",
            previous_records=self.__load_previous_ledger_records(target_date),
        )
        return self.__finalizer.finalize(retried_ledger)

    def __load_previous_ledger_records(self, target_date: str) -> dict[str, dict[str, Any]]:
        # 台帳が存在する日はパイプラインが確定した営業日そのものなので、
        # 市場カレンダーではなく正本の存在を辿って前営業日を決める。
        try:
            base = date.fromisoformat(target_date)
        except ValueError:
            return {}
        for offset in range(1, self.__PREVIOUS_LEDGER_LOOKBACK_DAYS + 1):
            previous_date = (base - timedelta(days=offset)).isoformat()
            ledger = self.__ledger_repo.load(previous_date)
            if not isinstance(ledger, dict):
                continue
            confirmed_date = (ledger.get("meta") or {}).get("target_date") or previous_date
            records: dict[str, dict[str, Any]] = {}
            for asset in ledger.get("assets") or []:
                if not isinstance(asset, dict):
                    continue
                asset_id = asset.get("id")
                # v4 の正本は `price`、v3.5 以前の台帳は `current_price` を持つ。
                price = asset.get("price")
                if not isinstance(price, (int, float)):
                    price = asset.get("current_price")
                if not isinstance(asset_id, str) or not isinstance(price, (int, float)) or price <= 0:
                    continue
                records[asset_id] = {
                    "price": float(price),
                    # v3.5 以前の台帳は資産別の鮮度を持たないため継承対象にしない。
                    "fx_rate": asset.get("fx_rate"),
                    "pricing_status": asset.get("pricing_status"),
                    "source_date": asset.get("source_date"),
                    "target_date": confirmed_date,
                }
            logger.info(
                f"[Parsing] Previous canonical ledger resolved: {confirmed_date} ({len(records)} priced assets)"
            )
            return records
        logger.info(
            f"[Guard] No canonical ledger within {self.__PREVIOUS_LEDGER_LOOKBACK_DAYS} days before "
            f"{target_date}. Falling back to history-based previous close."
        )
        return {}

    def __verified_canonical_ledger(self, target_date: str) -> dict[str, Any] | None:
        existing = self.__ledger_repo.load(target_date)
        if not isinstance(existing, dict):
            return None
        meta = existing.get("meta")
        if not isinstance(meta, dict):
            return None
        return existing if meta.get("integrity_status") == "VERIFIED" else None

    def __warn_if_diverged_from_confirmed(
        self,
        existing: dict[str, Any],
        document: dict[str, Any],
        target_date: str,
    ) -> None:
        # 確定済みの正本は保持するが、-F/--force の再送では再計算値から配信物が
        # 生成される。両者が食い違うとメールと正本が別の内容になるため検出して残す。
        confirmed = (existing.get("summary") or {}).get("total_assets_jpy")
        recomputed = (document.get("summary") or {}).get("total_diff_pct")
        recomputed_total = (document.get("summary") or {}).get("total_assets_jpy")
        if not isinstance(confirmed, (int, float)) or not isinstance(recomputed_total, (int, float)):
            return
        if int(confirmed) == int(recomputed_total):
            return
        logger.warning(
            f"[AUDIT] Recomputed total for {target_date} diverges from the confirmed canonical ledger "
            f"(confirmed={int(confirmed):,}, recomputed={int(recomputed_total):,}, "
            f"day={recomputed}). The confirmed ledger is preserved; dispatched content is recomputed."
        )

    def __persist_canonical_ledger(self, document: dict[str, Any], target_date: str) -> bool:
        # 日次台帳は週次/月次が LedgerRepository.load で参照する正本。
        # STALE を含む日は STAGNANT として保存し日次連続性を欠落させないが、
        # VERIFIED へ到達した正本は確定とみなし後続実行で書き換えない。
        try:
            existing = self.__verified_canonical_ledger(target_date)
            if existing is not None:
                logger.info(
                    f"[Guard] Canonical ledger already VERIFIED for {target_date}; preserving confirmed record."
                )
                self.__warn_if_diverged_from_confirmed(existing, document, target_date)
                return True
            self.__ledger_repo.save_document(document, target_date)
            status = (document.get("meta") or {}).get("integrity_status")
            logger.info(f"[Outcome] V4 canonical ledger persisted: {target_date} ({status})")
            return True
        except Exception as exc:
            logger.error(f"[AUDIT] Failed to persist canonical ledger for {target_date}: {exc}")
            return False

    def __persist_finalized_shadow_ledger(self, shadow_ledger: Any) -> bool:
        try:
            atomic_write_json(self.__SHADOW_OUTPUT, shadow_ledger.model_dump())
            return True
        except Exception as exc:
            logger.warning(f"[AUDIT] Failed to persist finalized ShadowLedger: {exc}")
            return False

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

    def __record_successful_dispatch(self, target_date: str, show_appraisal: bool) -> bool:
        if show_appraisal:
            self.__record_appraisal_display(target_date)
        return SystemUtils.set_flag(LAST_SENT_FILE_CURRENT, target_date)

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
