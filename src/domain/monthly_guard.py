from datetime import datetime
from typing import Final
from src.lib.utils import SystemUtils
from src.lib.timeline_controller import TimelineController
from src.infra.ledger_repository import LedgerRepository
from src.config.settings import LAST_SENT_FILE_MONTHLY
from src.lib.logger import setup_logger

class MonthlyGuardRail:
    __REV: Final[str] = "Rev. 3"
    __logger = setup_logger(__name__)

    def __init__(self, timeline: TimelineController, repo: LedgerRepository) -> None:
        self.__logger.info(f"[{self.__REV}] Initializing MonthlyGuardRail")
        self.__timeline = timeline
        self.__repo = repo

    def should_proceed(self, target_date_str: str, force_send: bool) -> bool:
        if force_send:
            self.__logger.info("[Guard] Force flag detected. Proceeding.")
            return True

        last_biz_day = self.__timeline.get_previous_month_last_business_day(target_date_str)
        target_dt = datetime.strptime(last_biz_day, "%Y-%m-%d")
        year_month = target_dt.strftime("%Y-%m")

        if SystemUtils.get_flag(LAST_SENT_FILE_MONTHLY) == year_month:
            self.__logger.info(f"[Guard] Monthly report for {year_month} already sent. Stopping.")
            return False

        self.__logger.info(f"[Guard] Monthly report for {year_month} not sent. Proceeding with Monthly Chronicle.")
        return True
