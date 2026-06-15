from datetime import datetime
from typing import Final
from src.lib.utils import SystemUtils
from src.lib.timeline_controller import TimelineController
from src.config.settings import LAST_ACCESS_FILE
from src.lib.logger import setup_logger
from src.domain.ledger_schema import ShadowLedger

class GuardRail:
    __REV: Final[str] = "Rev. 8"
    __logger = setup_logger(__name__)

    def __init__(self, timeline: TimelineController) -> None:
        self.__logger.info(f"[{self.__REV}] Initializing GuardRail")
        self.__timeline = timeline

    def should_proceed(self,
                       target_date_str: str,
                       lock_file: str,
                       force_send: bool,
                       scope: str,
                       format_test: bool) -> bool:
        if force_send or format_test:
            self.__logger.info("[Guard] Force/Test flag detected. Proceeding.")
            return True

        if scope == "context":
            self.__logger.info("[Guard] Context-only scope detected. Proceeding.")
            return True

        if SystemUtils.get_flag(lock_file) == target_date_str:
            self.__logger.info(f"[Guard] Report for {target_date_str} already sent. Stopping.")
            return False

        if self.__timeline.is_holiday(target_date_str):
            today_str = datetime.now().strftime("%Y-%m-%d")
            if SystemUtils.get_flag(LAST_ACCESS_FILE) == today_str:
                self.__logger.info(f"[Guard] Holiday access already attempted today ({today_str}). Stopping.")
                return False

            self.__logger.info(f"[Guard] Holiday detected ({target_date_str}), but first attempt today. Proceeding.")
            SystemUtils.set_flag(LAST_ACCESS_FILE, today_str)

        self.__logger.info(f"[Guard] All checks passed for {target_date_str}. Proceeding.")
        return True

    def should_dispatch_shadow_ledger(self, shadow_ledger: ShadowLedger, allow_missing: bool = True) -> bool:
        missing = [asset.name for asset in shadow_ledger.assets if asset.pricing_status == "MISSING"]
        if not missing:
            self.__logger.info(f"[Guard] V4 ShadowLedger priced: {len(shadow_ledger.assets)} assets. Proceeding.")
            return True
        if allow_missing:
            self.__logger.warning(
                f"[Guard] V4 ShadowLedger has missing prices ({len(missing)}): {missing}. Proceeding in degraded mode."
            )
            return True
        self.__logger.warning(f"[Guard] V4 ShadowLedger missing prices block dispatch: {missing}")
        return False
