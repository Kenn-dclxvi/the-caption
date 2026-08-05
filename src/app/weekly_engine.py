import os
from datetime import datetime
from typing import Final, Any

from src.config.settings import LAST_SENT_FILE_WEEKLY, VERSION, LLM_PRIORITY_ORDER, SMTP_TO
from src.lib.logger import setup_logger
from src.app.notifier import Notifier
from src.infra.ledger_repository import LedgerRepository
from src.infra.knowledge_manager import KnowledgeManager
from src.lib.timeline_controller import TimelineController
from src.domain.weekly_curator import WeeklyCurator
from src.domain.weekly_guard import WeeklyGuardRail
from src.infra.chronicle_repository import ChronicleRepository
from src.app.renderer.view_models import SummaryViewModel
from src.app.renderer.report_monthly import MonthlyRenderer
from src.lib.models import LedgerSummary
from src.lib.utils import SystemUtils

logger = setup_logger(__name__)

class WeeklyEngine:
    __REV: Final[str] = "Rev. 1"
    __FORMAT_TEST_OUTPUT: Final[str] = os.path.join("reports", "weekly_format_test.html")

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing WeeklyEngine")
        self.__notifier = Notifier()
        self.__repo = LedgerRepository()
        self.__knowledge = KnowledgeManager()
        self.__timeline = TimelineController()
        self.__curator = WeeklyCurator()
        self.__guard = WeeklyGuardRail(self.__timeline, self.__repo)
        self.__chronicle_repo = ChronicleRepository()

    def run(self, **kwargs: Any) -> None:
        try:
            format_test = kwargs.get("format_test", False)

            if format_test:
                self.__run_format_test()
                return

            logger.info("[Guard] Pre-flight Check: Verifying environment and resources for Weekly Engine")
            _smtp = (SMTP_TO[:1] + "***@" + SMTP_TO.split("@")[1]) if (SMTP_TO and "@" in SMTP_TO) else "unset"
            logger.info(f"[Config] v{VERSION} | LLM={LLM_PRIORITY_ORDER} | SMTP_TO={_smtp}")
            if not SystemUtils.check_env_vars():
                raise RuntimeError("Critical environment variables missing. Pipeline terminated.")

            manual_date = kwargs.get("target_date")
            force_send = kwargs.get("force_send", False)
            reuse_context = kwargs.get("reuse_context", False)

            target_date_str = self.__timeline.get_target_date(manual_date)
            logger.info(f"[Guard] Launching Weekly Engine v{VERSION} | Target Date: {target_date_str}")

            if not self.__guard.should_proceed(target_date_str, force_send):
                logger.info("[Outcome] Weekly Execution inhibited by GuardRail")
                return

            last_biz_day = self.__timeline.get_previous_week_last_business_day(target_date_str)
            ledger_dict = self.__repo.load(last_biz_day)

            if not ledger_dict:
                logger.error(f"[Outcome] Ledger missing for {last_biz_day} despite GuardRail check.")
                return

            summary_dict = ledger_dict.get("summary", {})
            summary = LedgerSummary(**summary_dict)
            summary_vm = SummaryViewModel(summary)

            target_dt = datetime.strptime(last_biz_day, "%Y-%m-%d")
            iso_year, iso_week, _ = target_dt.isocalendar()
            year_week = f"{iso_year}-W{iso_week:02d}"

            narrative_data = None
            if reuse_context:
                if self.__chronicle_repo.exists(year_week):
                    logger.info(f"[Acquisition] Reusing existing chronicle for {year_week}")
                    narrative_data = self.__chronicle_repo.load(year_week)
                else:
                    logger.warning(f"[Guard] Cache missing for {year_week}")

            if not narrative_data:
                insights = self.__knowledge.extract_weekly_insights(year_week)
                narrative_data = self.__curator.generate_weekly_chronicle(year_week, summary, insights)
                if narrative_data:
                    self.__chronicle_repo.save(narrative_data, year_week)

            dispatched = self.__notifier.weekly_report(narrative_data if narrative_data else {}, summary_vm, year_week)

            if dispatched:
                SystemUtils.set_flag(LAST_SENT_FILE_WEEKLY, year_week)
                logger.info(f"[Outcome] Weekly Chronicle Pipeline finished: DISPATCHED for {year_week}")
            else:
                logger.warning("[Outcome] Weekly Chronicle Pipeline finished: DISPATCH FAILED")

        except RuntimeError as re_err:
            logger.warning(f"[Guard] Operational limit: {re_err}")
            logger.info("[Recovery] Action: Verify env vars — ANTHROPIC_API_KEY, SMTP_USER, SMTP_PASS, SMTP_TO")
            self.__notifier.system_alert(str(re_err), "OPERATIONAL_LIMIT_WEEKLY")

        except Exception as e:
            logger.error(f"[Outcome] FATAL CRASH: {e}", exc_info=True)
            logger.info("[Recovery] Action: Inspect traceback above. Data integrity check recommended before re-run.")
            self.__notifier.system_alert(str(e), "SYSTEM_CRASH_WEEKLY")

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
            "theme_title": "WEEKLY FORMAT TEST — 検証の断章",
            "chronicle_headline": "週次フォーマット検証用ヘッドライン。文字間隔と行間の同期を確認する。",
            "chronicle_body": "本文の段落テキスト。週次レポートでも既存の可読性規律が維持されることを確認する一行目。\n二行目の段落。視覚リズムと余白設計が保持されることを確認する。",
            "shield_review": "SHIELD REVIEW パネルの検証。週次でも構造と余白ルールが維持されていることを確認する。",
        }
        renderer = MonthlyRenderer()
        html = renderer.render(stub_data, stub_vm)
        os.makedirs("reports", exist_ok=True)
        with open(self.__FORMAT_TEST_OUTPUT, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"[Outcome] Format test HTML saved: {self.__FORMAT_TEST_OUTPUT}")
