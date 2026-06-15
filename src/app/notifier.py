from typing import List, Dict, Any, Final, Optional
from src.lib.logger import setup_logger
from src.app.renderer import ContentRenderer
from src.infra.mail_sender import MailSender
from src.app.renderer.view_models import (
    SummaryViewModel,
    PositionViewModel,
    CollectionSummaryViewModel,
    CollectionSectionViewModel,
)

logger = setup_logger(__name__)

class Notifier:
    __REV: Final[str] = "Rev. 40"

    def __init__(self) -> None:
        logger.info(f"[{self.__REV}] Initializing Notifier")
        self.__renderer = ContentRenderer()
        self.__sender = MailSender()

    def portfolio_report_fortress(self, summary_vm: SummaryViewModel, asset_vms: List[PositionViewModel], display_date: str, is_provisional: bool = False) -> bool:
        logger.info(f"[Parsing] Preparing Fortress report for {display_date} (provisional={is_provisional})")
        try:
            html_content = self.__renderer.render_fortress(summary_vm, asset_vms)
            subject = f"INDEX [{display_date}]"
            if is_provisional:
                subject = f"{subject}○"
            result = self.__sender.send(subject, html_content)
            if not result:
                logger.warning(f"[Outcome] Fortress report delivery failed for {display_date}")
            return result
        except Exception as e:
            logger.error(f"[Outcome] Fortress report failed: {e}")
            return False

    def context_report(self, data: Dict[str, Any], display_date: str, is_provisional: bool = False) -> bool:
        logger.info(f"[Parsing] Preparing Context report for {display_date} (provisional={is_provisional})")
        try:
            html_content = self.__renderer.render_context(data)
            subject = f"CONTEXT [{display_date}]"
            if is_provisional:
                subject = f"{subject}○"
            result = self.__sender.send(subject, html_content)
            if not result:
                logger.warning(f"[Outcome] Context report delivery failed for {display_date}")
            return result
        except Exception as e:
            logger.error(f"[Outcome] Context report failed: {e}")
            return False

    def monthly_report(self, data: Dict[str, Any], summary_vm: Optional[SummaryViewModel], year_month: str) -> bool:
        logger.info(f"[Parsing] Preparing Monthly report for {year_month}")
        try:
            html_content = self.__renderer.render_monthly(data, summary_vm)
            subject = f"CHRONICLE [{year_month}]"
            result = self.__sender.send(subject, html_content)
            if not result:
                logger.warning(f"[Outcome] Monthly report delivery failed for {year_month}")
            return result
        except Exception as e:
            logger.error(f"[Outcome] Monthly report failed: {e}")
            return False

    def weekly_report(self, data: Dict[str, Any], summary_vm: SummaryViewModel, year_week: str) -> bool:
        logger.info(f"[Parsing] Preparing Weekly report for {year_week}")
        try:
            # NOTE: 週次レポートは月次テンプレートを共用する（render_weekly が未実装）
            html_content = self.__renderer.render_monthly(data, summary_vm)
            subject = f"WEEKLY CHRONICLE [{year_week}]"
            return self.__sender.send(subject, html_content)
        except Exception as e:
            logger.error(f"[Outcome] Weekly report failed: {e}")
            return False

    def collection_report(self, summary_vm: CollectionSummaryViewModel, section_vms: List[CollectionSectionViewModel], display_date: str, is_provisional: bool = False) -> bool:
        logger.info(f"[Parsing] Preparing Collection report for {display_date} (provisional={is_provisional})")
        try:
            html_content = self.__renderer.render_collection(summary_vm, section_vms)
            subject = f"COLLECTION [{display_date}]"
            if is_provisional:
                subject = f"{subject}○"
            return self.__sender.send(subject, html_content)
        except Exception as e:
            logger.error(f"[Outcome] Collection report failed: {e}")
            return False

    def system_alert(self, message: str, stage: str, is_test: bool = False) -> bool:
        try:
            html_content = self.__renderer.render_alert(message, stage, is_test)
            subject = f"ALERT [{stage}]"
            return self.__sender.send(subject, html_content)
        except Exception:
            return False
