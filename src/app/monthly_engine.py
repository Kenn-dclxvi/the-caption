import json
import os
from datetime import datetime
from typing import Final, Any, Optional

from src.config.settings import DATA_DIR, LAST_SENT_FILE_MONTHLY, VERSION, LLM_PRIORITY_ORDER, SMTP_TO
from src.lib.logger import setup_logger
from src.app.notifier import Notifier
from src.infra.ledger_repository import LedgerRepository
from src.infra.knowledge_manager import KnowledgeManager
from src.infra.daily_metrics_repository import DailyMetricsRepository
from src.infra.market_snapshot_repository import MarketSnapshotRepository
from src.lib.timeline_controller import TimelineController
from src.domain.monthly_curator import (
    MonthlyCurator,
    V4ChronicleBannedWordsViolation,
    V4ChronicleSchemaViolation,
)
from src.domain.monthly_guard import MonthlyGuardRail
from src.infra.chronicle_repository import ChronicleRepository
from src.app.renderer.view_models import SummaryViewModel
from src.app.renderer.report_monthly import MonthlyRenderer
from src.lib.models import LedgerSummary
from src.lib.utils import SystemUtils

logger = setup_logger(__name__)
_PORTFOLIO_BASIS_FILE: Final[str] = os.path.join(DATA_DIR, "portfolio_basis.json")

class MonthlyEngine:
    __REV: Final[str] = "Rev. 5"
    __FORMAT_TEST_OUTPUT: Final[str] = os.path.join("reports", "monthly_format_test.html")
    __V4_DAILY_METRICS_MIN_DAYS: Final[int] = 15

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing MonthlyEngine")
        self.__notifier = Notifier()
        self.__repo = LedgerRepository()
        self.__knowledge = KnowledgeManager()
        self.__daily_metrics_repo = DailyMetricsRepository()
        self.__market_snapshot_repo = MarketSnapshotRepository()
        self.__timeline = TimelineController()
        self.__curator = MonthlyCurator()
        self.__guard = MonthlyGuardRail(self.__timeline, self.__repo)
        self.__chronicle_repo = ChronicleRepository()

    def run(self, **kwargs: Any) -> None:
        try:
            format_test = kwargs.get("format_test", False)

            if format_test:
                self.__run_format_test()
                return

            logger.info("[Guard] Pre-flight Check: Verifying environment and resources for Monthly Engine")
            _smtp = (SMTP_TO[:1] + "***@" + SMTP_TO.split("@")[1]) if (SMTP_TO and "@" in SMTP_TO) else "unset"
            logger.info(f"[Config] v{VERSION} | LLM={LLM_PRIORITY_ORDER} | SMTP_TO={_smtp}")
            if not SystemUtils.check_env_vars():
                raise RuntimeError("Critical environment variables missing. Pipeline terminated.")

            manual_date = kwargs.get("target_date")
            force_send = kwargs.get("force_send", False)
            reuse_context = kwargs.get("reuse_context", False)

            target_date_str = self.__timeline.get_target_date(manual_date)
            logger.info(f"[Guard] Launching Monthly Engine v{VERSION} | Target Date: {target_date_str}")

            if not self.__guard.should_proceed(target_date_str, force_send):
                logger.info("[Outcome] Monthly Execution inhibited by GuardRail")
                return

            last_biz_day = self.__timeline.get_previous_month_last_business_day(target_date_str)
            target_dt = datetime.strptime(last_biz_day, "%Y-%m-%d")
            year_month = target_dt.strftime("%Y-%m")
            ledger_dict = self.__repo.load(last_biz_day)
            daily_metrics = self.__daily_metrics_repo.load_month(year_month)
            market_snapshots = self.__market_snapshot_repo.load_month(year_month)

            summary_vm: Optional[SummaryViewModel]
            if ledger_dict:
                summary_dict = ledger_dict.get("summary", {})
                summary = LedgerSummary(**summary_dict)
                summary_vm = SummaryViewModel(summary)
            else:
                if len(daily_metrics) < self.__V4_DAILY_METRICS_MIN_DAYS:
                    logger.error(
                        f"[Outcome] Ledger missing for {last_biz_day} and daily_metrics below threshold "
                        f"({len(daily_metrics)}/{self.__V4_DAILY_METRICS_MIN_DAYS})."
                    )
                    return
                summary_vm = self.__build_summary_vm_from_daily_metrics(daily_metrics)

            narrative_data = None
            if reuse_context:
                if self.__chronicle_repo.exists(year_month):
                    logger.info(f"[Acquisition] Reusing existing chronicle for {year_month}")
                    narrative_data = self.__chronicle_repo.load(year_month)
                else:
                    logger.warning(f"[Guard] Cache missing for {year_month}")

            if not narrative_data:
                insights = self.__knowledge.extract_monthly_insights(year_month)
                if len(daily_metrics) >= self.__V4_DAILY_METRICS_MIN_DAYS:
                    narrative_data = self.__curator.generate_v4_chronicle(
                        year_month,
                        insights=insights,
                        daily_metrics=daily_metrics,
                        market_snapshots=market_snapshots,
                        knowledge_manager=self.__knowledge,
                    )
                else:
                    logger.info(
                        "[V4] daily_metrics below threshold "
                        f"({len(daily_metrics)}/{self.__V4_DAILY_METRICS_MIN_DAYS}); "
                        "falling back to legacy monthly chronicle."
                    )
                    narrative_data = self.__curator.generate_monthly_chronicle(year_month, summary_vm, insights)
                if narrative_data:
                    self.__chronicle_repo.save(narrative_data, year_month)

            dispatched = self.__notifier.monthly_report(narrative_data if narrative_data else {}, summary_vm, year_month)

            if dispatched:
                SystemUtils.set_flag(LAST_SENT_FILE_MONTHLY, year_month)
                logger.info(f"[Outcome] Monthly Chronicle Pipeline finished: DISPATCHED for {year_month}")
            else:
                logger.warning("[Outcome] Monthly Chronicle Pipeline finished: DISPATCH FAILED")

        except V4ChronicleSchemaViolation as v4_schema_err:
            logger.warning(f"[V4] Schema violation: {v4_schema_err}")
            logger.info("[Recovery] Action: Regenerate monthly V4 after correcting the chronicle JSON contract.")
            self.__notifier.system_alert(str(v4_schema_err), "V4_SCHEMA_VIOLATION_MONTHLY")

        except V4ChronicleBannedWordsViolation as v4_banned_err:
            logger.warning(f"[V4] Banned words violation: {v4_banned_err}")
            logger.info("[Recovery] Action: Regenerate monthly V4 with the banned-word guard satisfied.")
            self.__notifier.system_alert(str(v4_banned_err), "V4_BANNED_WORD_MONTHLY")

        except RuntimeError as re_err:
            logger.warning(f"[Guard] Operational limit: {re_err}")
            logger.info("[Recovery] Action: Verify env vars — ANTHROPIC_API_KEY, SMTP_USER, SMTP_PASS, SMTP_TO")
            self.__notifier.system_alert(str(re_err), "OPERATIONAL_LIMIT_MONTHLY")

        except Exception as e:
            logger.error(f"[Outcome] FATAL CRASH: {e}", exc_info=True)
            logger.info("[Recovery] Action: Inspect traceback above. Data integrity check recommended before re-run.")
            self.__notifier.system_alert(str(e), "SYSTEM_CRASH_MONTHLY")

    def __build_summary_vm_from_daily_metrics(self, daily_metrics: list[dict[str, Any]]) -> SummaryViewModel:
        sorted_metrics = sorted(daily_metrics, key=lambda row: str(row.get("target_date", "")))
        start_metrics = sorted_metrics[0]
        end_metrics = sorted_metrics[-1]
        year_month = str(end_metrics.get("target_date", ""))[:7]
        start_total = float(start_metrics.get("total_value_jpy") or 0)
        end_total = float(end_metrics.get("total_value_jpy") or 0)
        total_assets = int(end_total)
        exposure = int(float(end_metrics.get("market_units_value_jpy") or 0))
        iron_bank = int(float(end_metrics.get("absolute_amount_value_jpy") or 0))
        safe_ratio_pct = (iron_bank / total_assets * 100) if total_assets else 0.0
        damper_coef = (exposure / total_assets) if total_assets else 0.0
        total_diff = int(end_total - start_total)
        total_diff_pct = (total_diff / start_total * 100) if start_total else 0.0
        total_acquisition_cost = self.__coerce_float(end_metrics.get("total_acquisition_cost_jpy"))
        if total_acquisition_cost is None:
            total_acquisition_cost = self.__load_total_acquisition_cost(year_month)

        raw_total_return = self.__coerce_float(end_metrics.get("total_return_jpy"))
        if raw_total_return is None and total_acquisition_cost is not None:
            raw_total_return = float(exposure) - total_acquisition_cost

        total_return = int(round(raw_total_return or 0))
        raw_total_return_pct = self.__coerce_float(end_metrics.get("total_return_pct"))
        if raw_total_return_pct is None and raw_total_return is not None and total_acquisition_cost:
            raw_total_return_pct = raw_total_return / total_acquisition_cost * 100.0
        total_return_pct = float(raw_total_return_pct or 0.0)
        invested_capital = int(round(total_acquisition_cost or 0))

        summary = LedgerSummary(
            total_assets_jpy=total_assets,
            total_profit_loss_jpy=total_return,
            cash_position_jpy=0,
            total_diff_jpy=total_diff,
            total_diff_pct=total_diff_pct,
            total_profit_loss_pct=total_return_pct,
            invested_capital_jpy=invested_capital,
            capital_gain_jpy=total_return,
            exposure_jpy=exposure,
            iron_bank_jpy=iron_bank,
            safe_ratio_pct=safe_ratio_pct,
            damper_coef=damper_coef,
        )
        return SummaryViewModel(summary)

    def __load_total_acquisition_cost(self, year_month: str) -> float | None:
        if not year_month:
            return None
        try:
            with open(_PORTFOLIO_BASIS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning(f"[V4] Failed to read portfolio basis for monthly summary: {exc}")
            return None

        if not isinstance(payload, dict):
            return None
        entry = payload.get(year_month)
        if not isinstance(entry, dict):
            return None
        return self.__coerce_float(entry.get("total_acquisition_cost_jpy"))

    def __coerce_float(self, value: Any) -> float | None:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        return amount

    def __run_format_test(self) -> None:
        stub_summary = LedgerSummary(
            total_assets_jpy=12_345_678,
            total_profit_loss_jpy=234_567,
            cash_position_jpy=1_000_000,
            total_diff_jpy=12_345,
            total_diff_pct=0.10,
            total_profit_loss_pct=1.94,
            invested_capital_jpy=12_111_111,
            capital_gain_jpy=234_567,
            exposure_jpy=11_345_678,
            iron_bank_jpy=1_000_000,
            safe_ratio_pct=8.10,
        )
        stub_vm = SummaryViewModel(stub_summary)
        stub_data = {
            "theme_title": "FORMAT TEST — 歴史の断章",
            "chronicle_headline": "フォーマット検証用のヘッドライン。言語主権の規律（letter-spacing: 0.1em）が適用されていることを確認する。",
            "chronicle_body": "本文の段落テキスト。読解のための静寂（line-height: 2.0 / letter-spacing: 0.1em）を体現する一行目。\n二行目の段落。余白と文字間隔がCONTEXTのナラティブ部分と完全同期していることを視覚的に確認する。",
            "shield_review": "SHIELD REVIEW パネルの検証。border-top 規律（border-top: 1px solid c_silver / padding-top: 16px）が正しく適用されていることを確認する。",
        }
        renderer = MonthlyRenderer()
        html = renderer.render(stub_data, stub_vm)
        os.makedirs("reports", exist_ok=True)
        with open(self.__FORMAT_TEST_OUTPUT, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"[Outcome] Format test HTML saved: {self.__FORMAT_TEST_OUTPUT}")
