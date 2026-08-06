from datetime import datetime
from typing import Final
from src.lib.utils import SystemUtils
from src.lib.timeline_controller import TimelineController
from src.domain.ports import LedgerReader
from src.config.settings import LAST_SENT_FILE_WEEKLY
from src.lib.logger import setup_logger

class WeeklyGuardRail:
    __REV: Final[str] = "Rev. 1"
    __logger = setup_logger(__name__)

    def __init__(self, timeline: TimelineController, repo: LedgerReader) -> None:
        self.__logger.info(f"[{self.__REV}] Initializing WeeklyGuardRail")
        self.__timeline = timeline
        self.__repo = repo

    def should_proceed(self, target_date_str: str, force_send: bool) -> bool:
        if force_send:
            self.__logger.info("[Guard] Force flag detected. Proceeding.")
            return True

        last_biz_day = self.__timeline.get_previous_week_last_business_day(target_date_str)
        target_dt = datetime.strptime(last_biz_day, "%Y-%m-%d")
        iso_year, iso_week, _ = target_dt.isocalendar()
        year_week = f"{iso_year}-W{iso_week:02d}"

        if SystemUtils.get_flag(LAST_SENT_FILE_WEEKLY) == year_week:
            self.__logger.info(f"[Guard] Weekly report for {year_week} already sent. Stopping.")
            return False

        ledger_data = self.__repo.load(last_biz_day)
        if not ledger_data:
            self.__logger.info(f"[Guard] Lazy Polling: Ledger for {last_biz_day} not found. Deferring execution.")
            return False

        meta = ledger_data.get("meta", {})
        if meta.get("integrity_status") != "VERIFIED":
            self.__logger.info(f"[Guard] Lazy Polling: Ledger for {last_biz_day} is not VERIFIED. Deferring execution.")
            return False

        self.__logger.info(f"[Guard] Ledger for {last_biz_day} is VERIFIED. Proceeding with Weekly Chronicle.")
        return True
